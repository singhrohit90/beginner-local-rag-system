"""Check that a model backend is reachable and answers, before starting a long evaluation.

    python -m rag.llm_check                       # the on-prem vLLM server from REMOTE_URL
    python -m rag.llm_check vllm:/models/gpt-oss-20b
    python -m rag.llm_check ollama:qwen2.5:7b

Exit code 0 means the model replied, 1 means it did not. For the vLLM server it also lists the
model ids the server offers, because the id must match exactly (it is a path).
"""

import sys
import time

from rag.llm import OpenAICompatLLM, get_llm
from rag.log import setup_logging


def main() -> int:
    setup_logging()
    spec = sys.argv[1] if len(sys.argv) > 1 else "vllm"
    try:
        llm = get_llm(spec, cache_dir=None)  # no cache, so the call is real
        if isinstance(llm, OpenAICompatLLM):
            models = llm.list_models()
            print(f"server offers: {models}")
            if llm._model not in models:
                print(f"FAIL  model {llm._model!r} is not offered. Use one of the ids above.")
                return 1
        start = time.perf_counter()
        result = llm.generate("Answer in one short sentence.", "What does BM25 stand for?", 60)
        elapsed = time.perf_counter() - start
    except Exception as err:  # report any failure plainly, this is a diagnostic
        print(f"FAIL  {err}")
        return 1
    print(f"OK    {llm.name}  {elapsed:.1f}s  tokens in/out {result.prompt_tokens}/{result.output_tokens}"
          f"  finish={result.finish_reason}")
    print(f"reply: {result.text[:200]!r}")
    if result.reasoning:
        print(f"reasoning tokens are included in the output count; thinking was {len(result.reasoning)} characters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
