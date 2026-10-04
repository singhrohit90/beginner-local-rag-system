"""The LLM behind one small interface, so the pipeline never knows which provider answers.

    get_llm("gemini:gemini-2.5-flash")    Google Gemini API, key from GEMINI_API_KEY
    get_llm("fake")                       canned replies, for tests

To add another provider (a local Ollama model, Claude), write a class with a `generate` method and
register it in get_llm. Retrieval, prompts and evaluation do not change.
"""

import hashlib
import json
import logging
import time
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

    def generate(self, system: str, user: str, max_output_tokens: int = 1024) -> LLMResult: ...


class GeminiLLM:
    """Gemini through the google-genai SDK. Temperature is 0 so a rerun gives (nearly) the same
    answer, which keeps evaluation runs comparable. Rate-limit and server errors are retried."""

    def __init__(self, model: str, retries: int = 6):
        from google import genai  # kept lazy so tests do not need the SDK or a key

        self.name = f"gemini:{model}"
        self._model = model
        self._retries = retries
        self._client = genai.Client(api_key=require("GEMINI_API_KEY"))

    def generate(self, system: str, user: str, max_output_tokens: int = 1024) -> LLMResult:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.0,
            max_output_tokens=max_output_tokens,
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


class FakeLLM:
    """Returns replies from a function, so tests can script the model."""

    def __init__(self, reply: Callable[[str, str], str] = lambda system, user: "fake answer"):
        self.name = "fake"
        self._reply = reply
        self.calls: List[tuple] = []

    def generate(self, system: str, user: str, max_output_tokens: int = 1024) -> LLMResult:
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

    def generate(self, system: str, user: str, max_output_tokens: int = 1024) -> LLMResult:
        key = hashlib.sha256(
            json.dumps([self.name, system, user, max_output_tokens]).encode()
        ).hexdigest()
        path = self._dir / f"{key}.json"
        if path.exists():
            return LLMResult(**json.loads(path.read_text(encoding="utf-8")))
        result = self._inner.generate(system, user, max_output_tokens)
        path.write_text(json.dumps(asdict(result)), encoding="utf-8")
        return result


def get_llm(spec: str, cache_dir: Optional[Path] = PROCESSED_DIR / "llm_cache") -> LLM:
    if spec == "fake":
        return FakeLLM()
    if spec.startswith("gemini:"):
        llm: LLM = GeminiLLM(spec.split(":", 1)[1])
        return CachedLLM(llm, cache_dir) if cache_dir else llm
    raise ValueError(f"unknown llm {spec!r}; use 'gemini:<model>' or 'fake'")
