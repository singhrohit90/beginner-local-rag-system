"""Run the full pipeline (retrieval, generation, judging) for one chunker and one retrieval config.

    python -m rag.experiments.answer --chunker recursive --config rrf
    python -m rag.experiments.answer --chunker heading --config rrf_rerank --workers 4
    python -m rag.experiments.answer --limit 10          # quick smoke run

Output in runs/<name>/: traces with prompt and answer, answers.jsonl (one scored row per question,
with the judge's reasons) and answer_report.json. LLM calls are cached on disk, so rerunning
unchanged costs nothing.
"""

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List

from rag.ingestion.chunking.base import load_chunkset
from rag.common.config import GOLDEN_DIR, PROCESSED_DIR, RUNS_DIR
from rag.common.embed import get_embedder
from rag.observe.generation_quality.answers import aggregate, score_answer
from rag.observe.golden import load_golden
from rag.ingestion.index import get_index
from rag.query.configs import CONFIGS
from rag.query.pipeline import RagPipeline
from rag.common.llm import get_llm
from rag.common.log import setup_logging
from rag.common.secrets import setting
from rag.query.pipeline import RetrievalPipeline
from rag.query.rerank import CrossEncoderReranker
from rag.common.trace import Trace

logger = logging.getLogger("rag.experiments.answer")


def print_report(report: Dict[str, Any]) -> None:
    a, u, t = report["answerable"], report["unanswerable"], report["attacks"]
    correct = "n/a (judge off)" if a["correct"] is None else a["correct"]
    faithful = "n/a (judge off)" if a["faithful"] is None else a["faithful"]
    print(f"\nAnswerable ({a['n']}, {a['unjudged']} unjudged): correct {correct}, faithful {faithful}, cites gold {a['cites_gold']}")
    print("  outcomes:", a["outcomes"])
    for kind, vals in a["by_type"].items():
        print(f"  {kind:<13} n={vals['n']:<3} correct {vals['correct']}  faithful {vals['faithful']}")
    print(f"Unanswerable ({u['n']}): abstained {u['abstained']}  {u['outcomes']}")
    print(f"Attacks ({t['n']}): passed {t['passed']}  {t['outcomes']}")
    print(f"Canary leaks: {report['canary_leaks']}   invalid citations: {report['invalid_citations']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--chunker", default="recursive")
    parser.add_argument("--config", default="rrf", choices=sorted(CONFIGS))
    parser.add_argument("--llm", default=setting("RAG_LLM", "vllm:/models/gpt-oss-20b"),
                        help="generator; default is the on-prem vLLM server, override with RAG_LLM")
    parser.add_argument("--judge", default=setting("RAG_JUDGE", "ollama:qwen2.5:7b"),
                        help="'none' skips correctness and faithfulness judging, so only abstention, "
                             "attack, canary and citation checks run")
    parser.add_argument("--embedder", default="st:sentence-transformers/all-mpnet-base-v2")
    parser.add_argument("--chunks-dir", type=Path, default=PROCESSED_DIR / "chunks")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "ddia_questions.jsonl")
    parser.add_argument("--style", default="standard", choices=["standard", "spotlight", "naive"],
                        help="prompt style; spotlight is the hardened prompt from rag.security.defenses")
    parser.add_argument("--no-output-filter", action="store_true",
                        help="do not withhold answers that look hijacked (for comparisons only)")
    parser.add_argument("--store", choices=["memory", "opensearch"], default="memory",
                        help="where the chunks live while searching; opensearch needs `docker compose up -d opensearch`")
    parser.add_argument("--opensearch-url", default="http://127.0.0.1:9200")
    parser.add_argument("--opensearch-prefix", default="ragbook", help="index prefix for the book, apart from uploads")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="only the first N questions")
    parser.add_argument("--name", default=None)
    args = parser.parse_args()
    setup_logging()

    questions = load_golden(args.golden)
    if args.limit:
        questions = questions[: args.limit]
    config = CONFIGS[args.config]
    name = args.name or f"ans__{args.chunker}__{args.config}"
    out_dir = RUNS_DIR / name

    embedder = get_embedder(args.embedder)
    chunkset = load_chunkset(args.chunks_dir, args.chunker)
    index = get_index(chunkset, embedder, "plain", rebuild=False)
    reranker = CrossEncoderReranker() if config.rerank else None
    if args.store == "opensearch":
        from rag.common.chunk_store import Scope
        from rag.common.opensearch_store import OpenSearchChunkStore
        from rag.ingestion.index import index_document

        database = OpenSearchChunkStore(embedder.name, embedder.dim, url=args.opensearch_url,
                                        prefix=args.opensearch_prefix)
        index_document(database, args.chunker, "local", chunkset, index)
        retrieval = RetrievalPipeline(database, embedder, Scope("local", (args.chunker,)), reranker)
    else:
        retrieval = RetrievalPipeline.from_chunkset(chunkset, index, embedder, reranker)
    generator = get_llm(args.llm)
    judge = None if args.judge == "none" else get_llm(args.judge)  # none: skip correctness judging
    pipeline = RagPipeline(retrieval, generator, style=args.style, output_filter=not args.no_output_filter)

    # Retrieval touches the GPU, so run it in order; the slow, network-bound LLM calls run in parallel.
    contexts = {q.id: retrieval.run(q.id, q.question, config) for q in questions}

    def generate(q) -> Trace:
        trace = contexts[q.id]
        try:
            return pipeline.answer(trace)
        except Exception as err:  # keep going, the row records the error
            trace.error = f"{type(err).__name__}: {err}"
            return trace

    with ThreadPoolExecutor(args.workers) as pool:
        traces = list(pool.map(generate, questions))
        rows: List[Dict[str, Any]] = list(
            pool.map(lambda pair: score_answer(pair[0], pair[1], judge), zip(questions, traces))
        )

    for trace in traces:
        trace.save(out_dir / "traces")
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "answers.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    report = aggregate(rows)
    report.update(name=name, generator=generator.name, judge=judge.name if judge else "none",
                  chunker=args.chunker, config=args.config)
    (out_dir / "answer_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print_report(report)
    print(f"\nwritten to {out_dir}")


if __name__ == "__main__":
    main()
