import io
import json
import urllib.error

import pytest

from rag.llm import CachedLLM, FakeLLM, OllamaLLM, get_llm


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_ollama_builds_request_and_maps_response(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["payload"] = json.loads(request.data)
        body = {"message": {"content": " hello "}, "prompt_eval_count": 12, "eval_count": 3, "done_reason": "stop"}
        return FakeResponse(json.dumps(body).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    llm = OllamaLLM("qwen2.5:7b")
    result = llm.generate("be brief", "hi", max_output_tokens=50, json_mode=True)
    assert result.text == "hello" and result.prompt_tokens == 12 and result.output_tokens == 3
    assert seen["url"] == "http://localhost:11434/api/chat"
    payload = seen["payload"]
    assert payload["model"] == "qwen2.5:7b" and payload["stream"] is False
    assert payload["messages"][0] == {"role": "system", "content": "be brief"}
    assert payload["options"]["temperature"] == 0.0 and payload["options"]["num_predict"] == 50
    assert payload["format"] == "json"
    llm.generate("s", "u")
    assert "format" not in seen["payload"]


def test_ollama_unreachable_gives_a_helpful_error(monkeypatch):
    def refuse(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", refuse)
    with pytest.raises(RuntimeError, match="ollama serve"):
        OllamaLLM("x").generate("s", "u")


def test_get_llm_routes_by_prefix(tmp_path):
    llm = get_llm("ollama:qwen2.5:7b", cache_dir=tmp_path)
    assert llm.name == "ollama:qwen2.5:7b"  # the model name keeps its own colon
    assert isinstance(get_llm("fake"), FakeLLM)
    with pytest.raises(ValueError):
        get_llm("openai:gpt")


def test_cache_key_separates_json_mode_but_keeps_old_entries(tmp_path):
    inner = FakeLLM(lambda s, u: "x")
    cached = CachedLLM(inner, tmp_path)
    cached.generate("s", "u")
    cached.generate("s", "u", json_mode=True)
    assert len(inner.calls) == 2 and len(list(tmp_path.glob("*.json"))) == 2
    cached.generate("s", "u")
    assert len(inner.calls) == 2
