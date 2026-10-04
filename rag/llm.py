"""The LLM behind one small interface, so the pipeline never knows which provider answers.

    get_llm("gemini:gemini-3.5-flash-lite")   Google Gemini API, key from GEMINI_API_KEY
    get_llm("ollama:qwen2.5:7b")               a local model served by Ollama, no key
    get_llm("fake")                            canned replies, for tests

To add another provider (Claude, OpenAI), write a class with a `generate` method that returns an
LLMResult and register it in get_llm. Retrieval, prompts and evaluation do not change, because
this file is the only place that knows how a provider's request and response look.
"""

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, List, Optional, Protocol

from rag.config import PROCESSED_DIR
from rag.secrets import require

logger = logging.getLogger(__name__)


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = ""


class LLM(Protocol):
    name: str

    def generate(
        self, system: str, user: str, max_output_tokens: int = 1024, json_mode: bool = False
    ) -> LLMResult:
        """json_mode asks the provider to return valid JSON only. Not every model honours it,
        so callers still parse defensively."""
        ...


class GeminiLLM:
    """Gemini through the google-genai SDK. Temperature is 0 so a rerun gives (nearly) the same
    answer, which keeps evaluation runs comparable. Rate-limit and server errors are retried."""

    def __init__(self, model: str, retries: int = 6):
        from google import genai  # kept lazy so tests do not need the SDK or a key

        self.name = f"gemini:{model}"
        self._model = model
        self._retries = retries
        self._client = genai.Client(api_key=require("GEMINI_API_KEY"))

    def generate(
        self, system: str, user: str, max_output_tokens: int = 1024, json_mode: bool = False
    ) -> LLMResult:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.0,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json" if json_mode else None,
        )
        delay = 2.0
        for attempt in range(self._retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model, contents=user, config=config
                )
                usage = response.usage_metadata
                candidate = response.candidates[0] if response.candidates else None
                return LLMResult(
                    text=(response.text or "").strip(),
                    prompt_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                    output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
                    finish_reason=str(getattr(candidate, "finish_reason", "")),
                )
            except errors.APIError as err:
                retryable = getattr(err, "code", 0) in (429, 500, 503, 504)
                if not retryable or attempt == self._retries:
                    raise
                logger.warning("Gemini %s, retrying in %.0fs", getattr(err, "code", "?"), delay)
                time.sleep(delay)
                delay = min(delay * 2, 60)
        raise RuntimeError("unreachable")


class OllamaLLM:
    """A model served by a local Ollama server (http://localhost:11434). No key, no quota, and
    nothing leaves the machine. Quality depends on the model: a 7B model grades and answers less
    reliably than a hosted one, so check its output before trusting it as a judge."""

    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        num_ctx: int = 8192,
        timeout: float = 600.0,
    ):
        self.name = f"ollama:{model}"
        self._model = model
        self._url = host.rstrip("/") + "/api/chat"
        self._num_ctx = num_ctx
        self._timeout = timeout

    def generate(
        self, system: str, user: str, max_output_tokens: int = 1024, json_mode: bool = False
    ) -> LLMResult:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_ctx": self._num_ctx,
                "num_predict": max_output_tokens,
            },
        }
        if json_mode:
            payload["format"] = "json"
        request = urllib.request.Request(
            self._url, json.dumps(payload).encode(), {"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = json.loads(response.read())
        except urllib.error.URLError as err:
            raise RuntimeError(
                f"cannot reach Ollama at {self._url} ({err.reason}). Is `ollama serve` running "
                f"and is the model pulled (`ollama pull {self._model}`)?"
            ) from err
        return LLMResult(
            text=(body.get("message", {}).get("content") or "").strip(),
            prompt_tokens=int(body.get("prompt_eval_count", 0) or 0),
            output_tokens=int(body.get("eval_count", 0) or 0),
            finish_reason=str(body.get("done_reason", "")),
        )


class FakeLLM:
    """Returns replies from a function, so tests can script the model."""

    def __init__(self, reply: Callable[[str, str], str] = lambda system, user: "fake answer"):
        self.name = "fake"
        self._reply = reply
        self.calls: List[tuple] = []

    def generate(
        self, system: str, user: str, max_output_tokens: int = 1024, json_mode: bool = False
    ) -> LLMResult:
        self.calls.append((system, user))
        return LLMResult(text=self._reply(system, user))


class CachedLLM:
    """Wraps any LLM with an on-disk cache keyed by model, prompts and token limit.

    Reruns of an evaluation then cost nothing and give identical answers, so a metric only moves
    when the pipeline changes. Delete the cache directory to force fresh calls."""

    def __init__(self, inner: LLM, directory: Path):
        self.name = inner.name
        self._inner = inner
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self, system: str, user: str, max_output_tokens: int = 1024, json_mode: bool = False
    ) -> LLMResult:
        parts = [self.name, system, user, max_output_tokens]
        if json_mode:
            parts.append("json")  # only added when set, so older cache entries stay valid
        key = hashlib.sha256(json.dumps(parts).encode()).hexdigest()
        path = self._dir / f"{key}.json"
        if path.exists():
            return LLMResult(**json.loads(path.read_text(encoding="utf-8")))
        result = self._inner.generate(system, user, max_output_tokens, json_mode)
        path.write_text(json.dumps(asdict(result)), encoding="utf-8")
        return result


def get_llm(spec: str, cache_dir: Optional[Path] = PROCESSED_DIR / "llm_cache") -> LLM:
    if spec == "fake":
        return FakeLLM()
    if spec.startswith("gemini:"):
        llm: LLM = GeminiLLM(spec.split(":", 1)[1])
    elif spec.startswith("ollama:"):
        llm = OllamaLLM(spec.split(":", 1)[1])
    else:
        raise ValueError(f"unknown llm {spec!r}; use 'gemini:<model>', 'ollama:<model>' or 'fake'")
    return CachedLLM(llm, cache_dir) if cache_dir else llm
