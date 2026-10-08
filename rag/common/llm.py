"""The LLM behind one small interface, so the pipeline never knows which provider answers.

    get_llm("vllm:/models/gpt-oss-20b")        the on-prem vLLM server (OpenAI-compatible API),
                                               over an SSH tunnel, no key
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
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, List, Optional, Protocol

from rag.common.config import PROCESSED_DIR
from rag.common.secrets import load_env, require

logger = logging.getLogger(__name__)


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = ""
    # A reasoning model's thinking, kept for debugging only. It can quote the system prompt, so it
    # must never be shown to a user or counted as part of the answer.
    reasoning: str = ""


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


DEFAULT_REMOTE_URL = "http://127.22.10.1:30007/v1"
DEFAULT_REMOTE_MODEL = "/models/gpt-oss-20b"


class OpenAICompatLLM:
    """Any server that speaks the OpenAI chat-completions API: vLLM, llama.cpp server, LM Studio,
    or a hosted OpenAI-style endpoint. Built for the on-prem vLLM server running a reasoning model
    (gpt-oss-20b) reached through an SSH tunnel.

    Reasoning models spend tokens thinking before they answer, and those tokens count against
    max_tokens. So the limit sent is the caller's answer budget plus `reasoning_budget`, and an
    answer cut off by the limit is retried once with a larger budget and then raised as an error,
    never returned empty as if it were a refusal.

    Settings come from the environment or .env: REMOTE_URL, REMOTE_API_KEY (optional),
    REMOTE_REASONING_BUDGET, REMOTE_REASONING_EFFORT (low, medium or high; only sent if set).
    """

    def __init__(
        self,
        model: str = "",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        reasoning_budget: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        timeout: float = 300.0,
        retries: int = 3,
    ):
        load_env()
        self._model = model or os.environ.get("REMOTE_MODEL", DEFAULT_REMOTE_MODEL)
        self.name = f"vllm:{self._model}"
        self._base = (base_url or os.environ.get("REMOTE_URL", DEFAULT_REMOTE_URL)).rstrip("/")
        self._key = api_key if api_key is not None else os.environ.get("REMOTE_API_KEY", "")
        self._budget = int(reasoning_budget or os.environ.get("REMOTE_REASONING_BUDGET", 3000))
        self._effort = reasoning_effort or os.environ.get("REMOTE_REASONING_EFFORT") or None
        self._timeout = timeout
        self._retries = retries

    @property
    def cache_salt(self) -> str:
        """Settings that change the answer without changing the model name. Empty by default, so
        existing cache entries stay valid."""
        return f"effort={self._effort}" if self._effort else ""

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        return headers

    def _unreachable(self, url: str, reason: object) -> RuntimeError:
        return RuntimeError(
            f"cannot reach the model server at {url} ({reason}). This is usually the SSH tunnel "
            f"(PuTTY) not being connected. The tunnel must listen on the host in REMOTE_URL "
            f"({self._base}). Quick test: curl -s {self._base}/models"
        )

    def list_models(self) -> List[str]:
        url = f"{self._base}/models"
        request = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read())
        except urllib.error.URLError as err:
            raise self._unreachable(url, err.reason if hasattr(err, "reason") else err) from err
        return [m.get("id", "") for m in data.get("data", [])]

    def _post(self, payload: dict) -> dict:
        url = f"{self._base}/chat/completions"
        request = urllib.request.Request(url, json.dumps(payload).encode(), self._headers())
        delay = 2.0
        for attempt in range(self._retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    return json.loads(response.read())
            except urllib.error.HTTPError as err:
                retryable = err.code in (429, 500, 502, 503, 504)
                if not retryable or attempt == self._retries:
                    body = err.read().decode("utf-8", "replace")[:300]
                    raise RuntimeError(f"model server returned HTTP {err.code}: {body}") from err
            except urllib.error.URLError as err:
                reason = getattr(err, "reason", err)
                if isinstance(reason, ConnectionRefusedError) or "refused" in str(reason).lower():
                    raise self._unreachable(url, reason) from err  # a dead tunnel will not recover
                if attempt == self._retries:
                    raise self._unreachable(url, reason) from err
            except TimeoutError:
                if attempt == self._retries:
                    raise RuntimeError(f"model server did not answer within {self._timeout:.0f}s")
            logger.warning("model server error, retrying in %.0fs", delay)
            time.sleep(delay)
            delay = min(delay * 2, 30)
        raise RuntimeError("unreachable")

    def generate(
        self, system: str, user: str, max_output_tokens: int = 1024, json_mode: bool = False
    ) -> LLMResult:
        # json_mode is accepted for interface compatibility. Guided JSON can conflict with a
        # reasoning model's output format, so the judges parse JSON defensively instead.
        for budget in (self._budget, self._budget * 2):
            payload = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.0,
                "max_tokens": max_output_tokens + budget,
            }
            if self._effort:
                payload["reasoning_effort"] = self._effort
            body = self._post(payload)
            if not body.get("choices"):
                raise RuntimeError(f"unexpected reply from the model server: {str(body)[:300]}")
            choice = body["choices"][0]
            message = choice.get("message", {})
            text = (message.get("content") or "").strip()
            finish = str(choice.get("finish_reason", ""))
            if finish == "length" and not text:
                continue  # the thinking used up the whole budget, so retry with more room
            usage = body.get("usage") or {}
            return LLMResult(
                text=text,
                prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
                output_tokens=int(usage.get("completion_tokens", 0) or 0),  # includes reasoning
                finish_reason=finish,
                reasoning=(message.get("reasoning") or message.get("reasoning_content") or "").strip(),
            )
        raise RuntimeError(
            "the answer was cut off by max_tokens, even after doubling the reasoning budget. "
            "Raise REMOTE_REASONING_BUDGET or lower REMOTE_REASONING_EFFORT."
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
        salt = getattr(self._inner, "cache_salt", "")
        if salt:
            parts.append(salt)
        key = hashlib.sha256(json.dumps(parts).encode()).hexdigest()
        path = self._dir / f"{key}.json"
        if path.exists():
            try:
                return LLMResult(**json.loads(path.read_text(encoding="utf-8")))
            except (ValueError, TypeError, OSError):
                pass  # a half-written or damaged entry: ask the model again and overwrite it
        result = self._inner.generate(system, user, max_output_tokens, json_mode)
        temporary = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            temporary.write_text(json.dumps(asdict(result)), encoding="utf-8")
            for attempt in range(5):
                try:
                    os.replace(temporary, path)  # readers see the old file or the whole new one
                    break
                except PermissionError:  # Windows: another thread has the file open right now
                    if attempt == 4:
                        raise
                    time.sleep(0.02 * (attempt + 1))
        except OSError as err:  # the cache is an optimisation: a failed write must not fail the call
            logger.warning("could not write the LLM cache entry: %s", err)
            temporary.unlink(missing_ok=True)
        return result


def get_llm(spec: str, cache_dir: Optional[Path] = PROCESSED_DIR / "llm_cache") -> LLM:
    if spec == "fake":
        return FakeLLM()
    if spec.startswith("gemini:"):
        llm: LLM = GeminiLLM(spec.split(":", 1)[1])
    elif spec.startswith("ollama:"):
        llm = OllamaLLM(spec.split(":", 1)[1])
    elif spec == "vllm" or spec.startswith("vllm:"):
        llm = OpenAICompatLLM(spec.split(":", 1)[1] if ":" in spec else "")
    else:
        raise ValueError(
            f"unknown llm {spec!r}; use 'vllm:<model>', 'gemini:<model>', 'ollama:<model>' or 'fake'"
        )
    return CachedLLM(llm, cache_dir) if cache_dir else llm
