import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from rag.llm import CachedLLM, OpenAICompatLLM, get_llm


class FakeVllm(BaseHTTPRequestHandler):
    """Imitates the vLLM routes the client uses. Class attributes script its behaviour."""

    model_id = "/models/gpt-oss-20b"
    replies: list = []  # popped in order; each is a dict body or an int HTTP status
    seen: list = []
    auth: list = []

    def log_message(self, *args):
        pass

    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        FakeVllm.auth.append(self.headers.get("Authorization"))
        self._send(200, {"data": [{"id": self.model_id}]})

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeVllm.seen.append(payload)
        FakeVllm.auth.append(self.headers.get("Authorization"))
        reply = FakeVllm.replies.pop(0)
        if isinstance(reply, int):
            self._send(reply, {"error": "boom"})
        else:
            self._send(200, reply)


def body(content, reasoning="thinking about it", finish="stop", completion=120):
    return {"choices": [{"message": {"content": content, "reasoning": reasoning}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 50, "completion_tokens": completion}}


@pytest.fixture
def server():
    FakeVllm.replies, FakeVllm.seen, FakeVllm.auth = [], [], []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeVllm)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/v1"
    httpd.shutdown()


def llm_for(url, **kw):
    return OpenAICompatLLM("/models/gpt-oss-20b", base_url=url, retries=2, **kw)


def test_generate_maps_content_reasoning_and_usage(server):
    FakeVllm.replies = [body("The answer [S1].")]
    result = llm_for(server).generate("be brief", "hi", max_output_tokens=600)
    assert result.text == "The answer [S1]." and result.reasoning == "thinking about it"
    assert result.prompt_tokens == 50 and result.output_tokens == 120 and result.finish_reason == "stop"
    sent = FakeVllm.seen[0]
    assert sent["model"] == "/models/gpt-oss-20b" and sent["temperature"] == 0.0
    assert sent["messages"][0] == {"role": "system", "content": "be brief"}
    assert sent["max_tokens"] == 600 + 3000  # the answer budget plus room for thinking
    assert "reasoning_effort" not in sent


def test_reasoning_effort_and_api_key_are_sent_only_when_set(server):
    FakeVllm.replies = [body("ok text here")]
    llm_for(server, reasoning_effort="low", api_key="secret-token").generate("s", "u")
    assert FakeVllm.seen[0]["reasoning_effort"] == "low"
    assert FakeVllm.auth[-1] == "Bearer secret-token"
    FakeVllm.replies = [body("ok text here")]
    llm_for(server, api_key="").generate("s", "u")
    assert FakeVllm.auth[-1] is None


def test_truncated_empty_answer_is_retried_with_a_bigger_budget_then_raised(server):
    FakeVllm.replies = [body("", finish="length"), body("Finally answered.")]
    result = llm_for(server).generate("s", "u", max_output_tokens=100)
    assert result.text == "Finally answered."
    assert FakeVllm.seen[0]["max_tokens"] == 100 + 3000 and FakeVllm.seen[1]["max_tokens"] == 100 + 6000
    FakeVllm.replies = [body("", finish="length"), body("", finish="length")]
    with pytest.raises(RuntimeError, match="cut off by max_tokens"):
        llm_for(server).generate("s", "u")


def test_a_partial_but_nonempty_answer_that_hit_the_limit_is_returned_with_its_finish_reason(server):
    FakeVllm.replies = [body("Half an ans", finish="length")]
    result = llm_for(server).generate("s", "u")
    assert result.text == "Half an ans" and result.finish_reason == "length"


def test_server_errors_are_retried_but_client_errors_are_not(server, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    FakeVllm.replies = [503, body("recovered text here")]
    assert llm_for(server).generate("s", "u").text == "recovered text here"
    FakeVllm.replies = [400]
    with pytest.raises(RuntimeError, match="HTTP 400"):
        llm_for(server).generate("s", "u")
    assert FakeVllm.replies == []  # the 400 was consumed once, not retried


def test_list_models_and_dead_tunnel_message(server):
    assert llm_for(server).list_models() == ["/models/gpt-oss-20b"]
    dead = OpenAICompatLLM("/models/gpt-oss-20b", base_url="http://127.0.0.1:1/v1", retries=0)
    with pytest.raises(RuntimeError, match="SSH tunnel"):
        dead.generate("s", "u")


def test_get_llm_routes_vllm_and_keeps_the_path_style_model_id(tmp_path):
    llm = get_llm("vllm:/models/gpt-oss-20b", cache_dir=tmp_path)
    assert isinstance(llm, CachedLLM) and llm.name == "vllm:/models/gpt-oss-20b"
    assert get_llm("vllm", cache_dir=None).name == "vllm:/models/gpt-oss-20b"


def test_cache_round_trips_the_reasoning_field(server, tmp_path):
    FakeVllm.replies = [body("cached answer text")]
    cached = CachedLLM(llm_for(server), tmp_path)
    first = cached.generate("s", "u")
    second = cached.generate("s", "u")  # no second reply is queued, so this must be a cache hit
    assert second.text == first.text and second.reasoning == "thinking about it"
