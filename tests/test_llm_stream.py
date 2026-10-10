"""The streaming call of the model client, against a small local server that speaks the same
server-sent-events format as vLLM (OpenAI chat completions with "stream": true)."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from rag.common.llm import FakeLLM, OpenAICompatLLM, StreamPiece, stream_answer


class _Server:
    """Plays a script: each request gets the next list of SSE lines. A line may be bytes, or
    ("pause", seconds), or "DROP" to close the connection without ending the stream."""

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.payloads = []
        self.connection_lost = threading.Event()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.payloads.append(body)
                script = outer.scripts.pop(0)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                try:
                    for step in script:
                        if step == "DROP":
                            self.connection.close()
                            return
                        if isinstance(step, tuple):
                            time.sleep(step[1])
                            continue
                        self.wfile.write(step if isinstance(step, bytes) else step.encode())
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    outer.connection_lost.set()

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def event(**delta_and_more):
    return f"data: {json.dumps(delta_and_more)}\n\n"


def chunk(content=None, reasoning=None, finish=None):
    delta = {}
    if content is not None:
        delta["content"] = content
    if reasoning is not None:
        delta["reasoning"] = reasoning
    return event(choices=[{"delta": delta, "finish_reason": finish}])


USAGE = event(choices=[], usage={"prompt_tokens": 11, "completion_tokens": 7})
DONE = "data: [DONE]\n\n"


@pytest.fixture
def served():
    servers = []

    def make(*scripts):
        server = _Server(scripts)
        servers.append(server)
        return server, OpenAICompatLLM("m", base_url=server.url, reasoning_budget=100, retries=0, timeout=5)

    yield make
    for server in servers:
        server.close()


def collect(llm, **kwargs):
    pieces = list(llm.generate_stream("system", "user", 50, **kwargs))
    texts = [p.text for p in pieces if p.text]
    return texts, pieces[-1].result


def test_the_answer_arrives_in_pieces_and_the_thinking_never_does(served):
    server, llm = served([
        chunk(reasoning="The user wants "), chunk(reasoning="a short answer."),
        chunk(content="Copies "), chunk(content="live on "), chunk(content="several nodes [S1]."),
        chunk(finish="stop"), USAGE, DONE,
    ])
    texts, result = collect(llm)
    assert texts == ["Copies ", "live on ", "several nodes [S1]."]
    assert result.text == "Copies live on several nodes [S1]." and result.finish_reason == "stop"
    assert result.reasoning == "The user wants a short answer."  # kept for debugging, never yielded
    assert (result.prompt_tokens, result.output_tokens) == (11, 7)
    assert server.payloads[0]["stream"] is True and server.payloads[0]["max_tokens"] == 150  # answer budget + thinking budget


def test_an_answer_cut_off_during_thinking_is_retried_with_a_larger_budget(served):
    server, llm = served(
        [chunk(reasoning="thinking and thinking"), chunk(finish="length"), DONE],
        [chunk(content="Done."), chunk(finish="stop"), DONE],
    )
    texts, result = collect(llm)
    assert texts == ["Done."] and result.text == "Done."
    assert [p["max_tokens"] for p in server.payloads] == [150, 250]


def test_a_stream_that_ends_without_a_finish_is_an_error_not_a_short_answer(served):
    _, llm = served([chunk(content="The beginning of an ans")])  # the server just stops
    with pytest.raises(RuntimeError, match="stopped answering"):
        collect(llm)


def test_a_dropped_connection_is_an_error(served):
    _, llm = served([chunk(content="Part"), "DROP"])
    with pytest.raises(RuntimeError, match="stopped answering"):
        collect(llm)


def test_stopping_early_closes_the_connection_so_the_server_stops_generating(served):
    pieces = [chunk(content="word ") for _ in range(200)]
    server, llm = served([pieces[0], ("pause", 0.2)] + pieces[1:] + [chunk(finish="stop"), DONE])
    stream = llm.generate_stream("system", "user", 50)
    first = next(stream)
    assert first.text == "word "
    stream.close()  # what happens when the browser disconnects
    assert server.connection_lost.wait(timeout=5), "the server was never told the client went away"


def test_an_unreachable_server_gives_the_usual_message():
    llm = OpenAICompatLLM("m", base_url="http://127.0.0.1:9/v1", retries=0, timeout=2)
    with pytest.raises(RuntimeError, match="cannot reach the model server"):
        list(llm.generate_stream("s", "u"))


def test_a_client_without_streaming_gives_the_whole_answer_as_one_piece():
    class Plain:
        name = "plain"

        def generate(self, system, user, max_output_tokens=1024, json_mode=False):
            from rag.common.llm import LLMResult

            return LLMResult(text="all at once", output_tokens=3)

    pieces = list(stream_answer(Plain(), "s", "u"))
    assert [p.text for p in pieces] == ["all at once", ""] and pieces[-1].result.output_tokens == 3


def test_the_fake_model_streams_in_four_character_pieces():
    pieces = list(FakeLLM(lambda s, u: "abcdefghij").generate_stream("s", "u"))
    assert [p.text for p in pieces[:-1]] == ["abcd", "efgh", "ij"] and pieces[-1].result.text == "abcdefghij"
    assert isinstance(pieces[0], StreamPiece)
