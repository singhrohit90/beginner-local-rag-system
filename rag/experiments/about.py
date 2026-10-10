"""Score the "about the documents" path (DocumentService.ask_about) on data/golden/about_questions.jsonl.

    python -m rag.experiments.about --doc-ids bc84d6809b4f bbbd81348fba --uploads <path to data/uploads>
    python -m rag.experiments.about --doc-ids ... --llm ollama:qwen2.5:7b --judge none   # answers only

Each question is asked over all the given documents together. The answer is scored with the per-question
fact checklist judge (rag.observe.generation_quality.judge.judge_facts): correct only if every key fact is
stated. There is no retrieval, so no hit or faithfulness numbers. A question with a handful of answers is a
smoke test: with 6 questions one question is 16.7 points.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from rag.api.service import LOCAL_OWNER, DocumentService
from rag.common.config import DATA_DIR, GOLDEN_DIR, RUNS_DIR
from rag.common.embed import HashingEmbedder
from rag.common.log import setup_logging
from rag.common.secrets import setting
from rag.observe.generation_quality.judge import judge_facts
from rag.observe.golden import GoldQuestion, load_golden


def run_questions(service: DocumentService, owner: str, doc_ids: Sequence[str],
                  questions: Sequence[GoldQuestion], judge: Optional[Any]) -> List[Dict[str, Any]]:
    """One row per question: the answer, whether it was blocked, and the facts it stated."""
    rows: List[Dict[str, Any]] = []
    for q in questions:
        row: Dict[str, Any] = {"id": q.id, "type": q.type, "question": q.question, "n_facts": len(q.key_facts)}
        try:
            result = service.ask_about(owner, list(doc_ids), q.question)
        except Exception as err:  # keep going, the row records the error
            row.update(answer="", error=f"{type(err).__name__}: {err}", correct=None, stated=[], missing=[],
                       outcome="error")
            rows.append(row)
            continue
        row.update(answer=result["answer"], blocked=result["blocked"], citations=result["citations"], error="")
        if judge is None or not q.key_facts:
            row.update(correct=None, stated=[], missing=[], outcome="unjudged")
        else:
            verdict = judge_facts(judge, result["answer"], q.key_facts)
            row.update(correct=verdict.correct, stated=verdict.stated, missing=verdict.missing,
                       outcome="unjudged" if verdict.correct is None else ("ok" if verdict.correct else "fail"))
        rows.append(row)
    return rows


def summarise(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    judged = [r for r in rows if r["correct"] is not None]
    stated = sum(sum(1 for s in r["stated"] if s) for r in judged)
    facts = sum(len(r["stated"]) for r in judged)
    return {"n": len(rows), "judged": len(judged), "correct": sum(1 for r in judged if r["correct"]),
            "errors": sum(1 for r in rows if r["outcome"] == "error"),
            "facts_stated": stated, "facts_total": facts,
            "correct_rate": round(sum(1 for r in judged if r["correct"]) / len(judged), 3) if judged else None}


def print_table(rows: Sequence[Dict[str, Any]], summary: Dict[str, Any]) -> None:
    print(f"\n{'id':<6}{'type':<13}{'facts':<8}{'outcome':<10}missing / error")
    for r in rows:
        facts = f"{sum(1 for s in r['stated'] if s)}/{r['n_facts']}" if r["stated"] else f"-/{r['n_facts']}"
        note = r["error"] or "; ".join(r["missing"])
        print(f"{r['id']:<6}{r['type']:<13}{facts:<8}{r['outcome']:<10}{note[:100]}")
    rate = "n/a" if summary["correct_rate"] is None else summary["correct_rate"]
    print(f"\ncorrect {summary['correct']}/{summary['judged']} judged ({rate}); facts stated "
          f"{summary['facts_stated']}/{summary['facts_total']}; errors {summary['errors']}; questions {summary['n']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--doc-ids", nargs="+", required=True, help="uploaded documents to ask about, together")
    parser.add_argument("--uploads", type=Path, default=DATA_DIR / "uploads", help="the uploads folder")
    parser.add_argument("--owner", default=LOCAL_OWNER)
    parser.add_argument("--llm", default=setting("RAG_LLM", "vllm:/models/gpt-oss-20b"),
                        help="generator; default is the on-prem vLLM server, override with RAG_LLM")
    parser.add_argument("--judge", default=setting("RAG_JUDGE", "ollama:qwen2.5:7b"),
                        help="fact checklist judge; 'none' prints the answers without scoring")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "about_questions.jsonl")
    parser.add_argument("--name", default="about")
    args = parser.parse_args()
    setup_logging()

    from rag.common.llm import get_llm  # imported here so the pure functions above load without a backend

    # cache_dir=None: the cache would keep the profile text of the documents after a delete.
    generator = get_llm(args.llm, cache_dir=None)
    judge = None if args.judge == "none" else get_llm(args.judge, cache_dir=None)
    service = DocumentService(root=args.uploads, embedder=HashingEmbedder(), embedder_spec="hash", llm=generator,
                              keep_traces=False)
    questions = load_golden(args.golden)
    rows = run_questions(service, args.owner, args.doc_ids, questions, judge)
    summary = summarise(rows)
    summary.update(generator=generator.name, judge=judge.name if judge else "none", doc_ids=list(args.doc_ids))

    out_dir = RUNS_DIR / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "about_answers.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (out_dir / "about_report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print_table(rows, summary)
    print(f"generator {summary['generator']}   judge {summary['judge']}\nwritten to {out_dir}")


if __name__ == "__main__":
    main()
