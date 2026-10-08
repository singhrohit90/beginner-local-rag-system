"""Indirect prompt injection and document poisoning tests.

    python -m rag.security.indirect
    python -m rag.security.indirect --llm ollama:qwen2.5:7b --defenses none,spotlight
    python -m rag.security.indirect --defenses none,scan,spotlight,output_filter,all

For each poisoned document, a copy of the corpus is built with that one document added, a normal
question on the document's topic is asked, and the answer is checked for the document's payload.
That isolates each attack. The poisoned document is only a distractor if retrieval misses it, so
"exposed" counts how often it actually reached the model.

Outcomes per attack: obeyed (the model acted on the document), reported (the payload appears but
the model said it was ignoring an instruction, which is a good result), none (no sign of it),
blocked (the output filter withheld the answer).

The run also audits the cost of the defences on legitimate content: how many real book chunks the
scanner flags, and how many correct golden-set answers the output filter would have blocked.
"""

import argparse
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from rag.ingestion.chunking.base import ChunkSet, load_chunkset
from rag.common.config import PROCESSED_DIR, RUNS_DIR
from rag.common.embed import Embedder, get_embedder
from rag.experiments.retrieval import CONFIGS, get_index
from rag.query.generate import answer_from_context, looks_like_abstention
from rag.common.llm import get_llm
from rag.common.log import setup_logging
from rag.common.secrets import setting
from rag.common.bm25 import BM25Index
from rag.query.pipeline import RetrievalPipeline
from rag.common.store import VectorIndex
from rag.security.defenses import classify, filter_output
from rag.security.fixtures import POISONED_DOCS, PoisonedDoc
from rag.security.scan import scan_chunks, scan_text
from rag.common.types import Chunk

logger = logging.getLogger("rag.security")

DEFENSES: Dict[str, tuple] = {
    "naive": ("naive",),  # first-draft prompt, no injection rules: the unprotected baseline
    "naive_filter": ("naive", "filter"),  # the baseline plus only the output filter
    "none": (),  # the production prompt, whose rules already tell the model to ignore passages
    "scan": ("scan",),
    "spotlight": ("spotlight",),
    "output_filter": ("filter",),
    "scan_filter": ("scan", "filter"),  # no prompt change: for a model that spotlighting makes cautious
    "cap": ("cap",),  # at most 2 passages per source, exact copies dropped
    "default": ("scan", "cap", "filter"),  # the pipeline's own defaults with the production prompt
    "all": ("scan", "spotlight", "filter"),
}


def poison_chunk(doc: PoisonedDoc, number: int, copy: int = 0) -> Chunk:
    start = 10**9 + number * 10**5 + copy * 10**3  # far outside the book, so spans never overlap
    suffix = f"-c{copy}" if copy else ""
    return Chunk(
        chunk_id=f"poison-{doc.id}{suffix}",
        text=doc.text,
        page_start=9000 + number,
        page_end=9000 + number,
        strategy="poison",
        section="poisoned test document",
        meta={"span": [start, start + len(doc.text)], "poison": doc.id, "source": doc.id},
    )


def pipeline_with(base: RetrievalPipeline, extra: List[Chunk], embedder: Embedder) -> RetrievalPipeline:
    """The base pipeline's corpus plus extra chunks. Base vectors are reused; only the new
    chunks are embedded."""
    if not extra:
        return base
    chunkset = ChunkSet(base.chunkset.strategy, base.chunkset.params,
                        base.chunkset.chunks + extra, base.chunkset.parents)
    vectors = np.vstack([base.vector_index.vectors, embedder.embed_documents([c.text for c in extra])])
    index = VectorIndex(base.vector_index.chunk_ids + [c.chunk_id for c in extra], vectors,
                        base.vector_index.embedder_name, dict(base.vector_index.meta))
    return RetrievalPipeline(chunkset, index, BM25Index(chunkset.chunks), embedder, None)


@dataclass
class Result:
    doc: str
    attack: str
    defense: str
    exposed: bool
    in_corpus: bool
    outcome: str  # obeyed / reported / none / blocked
    raw_outcome: str
    blocked_reasons: List[str]
    answered: bool
    answer: str


def run_attack(doc: PoisonedDoc, number: int, defense: str, base: RetrievalPipeline, embedder: Embedder,
               llm, config, context_cache: Dict[str, Any], copies: int = 1) -> Result:
    """copies > 1 plants the same document several times, a flooding attack that tries to fill
    the model's context with the attacker's text."""
    steps = DEFENSES[defense]
    planted = [poison_chunk(doc, number, c) for c in range(copies)]
    in_corpus = not ("scan" in steps and scan_text(planted[0].text).flagged)
    capped = "cap" in steps
    key = f"{doc.id}:{in_corpus}:{copies}:{capped}"
    if key not in context_cache:
        pipeline = pipeline_with(base, planted if in_corpus else [], embedder)
        # scanning is modelled by leaving the document out of the corpus above, so select-time
        # scanning stays off here; otherwise the baselines would silently include it
        cfg = replace(config, scan=False, max_per_source=2 if capped else 0)
        context_cache[key] = pipeline.run(doc.id, doc.question, cfg).stage("context").hits
    context = context_cache[key]
    exposed = any(h.chunk_id.startswith(f"poison-{doc.id}") for h in context)

    style = "spotlight" if "spotlight" in steps else "naive" if "naive" in steps else "standard"
    answer, _ = answer_from_context(llm, doc.question, context, style=style)
    raw_outcome = classify(answer.text, doc.payloads)
    text, blocked, reasons = answer.text, False, []
    if "filter" in steps:
        result = filter_output(answer.text, " ".join(h.text for h in context))
        text, blocked, reasons = result.answer, result.blocked, result.reasons
    outcome = "blocked" if blocked else classify(text, doc.payloads)
    answered = not blocked and not looks_like_abstention(text) and len(text) > 40
    return Result(doc.id, doc.attack, defense, exposed, in_corpus, outcome, raw_outcome, reasons, answered, text)


def audit_scanner(chunkset: ChunkSet) -> Dict[str, Any]:
    results = scan_chunks(chunkset.chunks)
    flagged = {cid: r for cid, r in results.items() if r.flagged}
    by_rule = Counter(rule for r in flagged.values() for rule in r.rules)
    by_id = {c.chunk_id: c for c in chunkset.chunks}
    samples = [(cid, r.rules, by_id[cid].text[:140].replace("\n", " ")) for cid, r in list(flagged.items())[:4]]
    return {"chunks": len(results), "flagged": len(flagged), "by_rule": dict(by_rule), "samples": samples}


def audit_output_filter(run_dir: Path) -> Optional[Dict[str, Any]]:
    """How many answers from a normal golden-set run the output filter would have blocked."""
    answers = run_dir / "answers.jsonl"
    if not answers.exists():
        return None
    rows = [json.loads(line) for line in answers.read_text(encoding="utf-8").splitlines() if line.strip()]
    blocked = []
    for row in rows:
        if row.get("abstained") or not row.get("answer"):
            continue
        trace = json.loads((run_dir / "traces" / f"{row['id']}.json").read_text(encoding="utf-8"))
        context = next(s for s in trace["stages"] if s["name"] == "context")
        result = filter_output(row["answer"], " ".join(h["text"] for h in context["hits"]))
        if result.blocked:
            blocked.append((row["id"], result.reasons, row["answer"][:100].replace("\n", " ")))
    return {"answers_checked": sum(1 for r in rows if not r.get("abstained") and r.get("answer")),
            "blocked": blocked}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--chunker", default="semantic")
    parser.add_argument("--config", default="weighted", choices=sorted(CONFIGS))
    parser.add_argument("--llm", default=setting("RAG_LLM", "vllm:/models/gpt-oss-20b"))
    parser.add_argument("--defenses", default="naive,none,scan,spotlight,output_filter,all")
    parser.add_argument("--copies", type=int, default=1,
                        help="plant each poisoned document this many times (a flooding attack)")
    parser.add_argument("--embedder", default="st:sentence-transformers/all-mpnet-base-v2")
    parser.add_argument("--chunks-dir", type=Path, default=PROCESSED_DIR / "chunks")
    parser.add_argument("--golden-run", type=Path, default=RUNS_DIR / "ans__semantic__weighted")
    args = parser.parse_args()
    setup_logging()

    embedder = get_embedder(args.embedder)
    chunkset = load_chunkset(args.chunks_dir, args.chunker)
    base = RetrievalPipeline(chunkset, get_index(chunkset, embedder, "plain", False),
                             BM25Index(chunkset.chunks), embedder, None)
    llm = get_llm(args.llm)
    config = CONFIGS[args.config]
    defenses = [d.strip() for d in args.defenses.split(",")]

    cache: Dict[str, Any] = {}
    results: List[Result] = []
    for defense in defenses:
        for number, doc in enumerate(POISONED_DOCS):
            results.append(run_attack(doc, number, defense, base, embedder, llm, config, cache, args.copies))

    print(f"\ntarget: {llm.name}   corpus: {args.chunker} + {args.config}   copies planted: {args.copies}\n")
    print(f"{'attack':<16}" + "".join(f"{d:>15}" for d in defenses))
    for doc in POISONED_DOCS:
        row = {r.defense: r for r in results if r.doc == doc.id}
        cells = "".join(f"{row[d].outcome + ('*' if row[d].exposed else ''):>15}" for d in defenses)
        print(f"{doc.id + ' ' + doc.attack:<16}{cells}")
    print("\n* = the poisoned passage was in the model's context.  obeyed = attack worked, "
          "reported = model flagged it, none = no effect, blocked = output filter withheld it.\n")

    summary: Dict[str, Dict[str, Any]] = {}
    for defense in defenses:
        rs = [r for r in results if r.defense == defense]
        counts = Counter(r.outcome for r in rs)
        exposed = sum(r.exposed for r in rs)
        summary[defense] = {
            "attacks": len(rs), "exposed": exposed, "obeyed": counts["obeyed"],
            "reported": counts["reported"], "blocked": counts["blocked"], "none": counts["none"],
            "still_answered": sum(r.answered for r in rs),
        }
    print(f"{'defense':<15}{'exposed':>8}{'obeyed':>8}{'reported':>10}{'blocked':>9}{'no effect':>10}{'answered':>10}")
    for defense, s in summary.items():
        print(f"{defense:<15}{s['exposed']:>8}{s['obeyed']:>8}{s['reported']:>10}{s['blocked']:>9}{s['none']:>10}{s['still_answered']:>10}")

    scanner = audit_scanner(chunkset)
    caught = [d.id for d in POISONED_DOCS if scan_text(d.text).flagged]
    missed = [d.id for d in POISONED_DOCS if not scan_text(d.text).flagged]
    print(f"\nscanner on poisoned docs: caught {len(caught)}/{len(POISONED_DOCS)}, missed {missed}")
    print(f"scanner on real book chunks: flagged {scanner['flagged']} of {scanner['chunks']}  {scanner['by_rule']}")
    for sample in scanner["samples"]:
        print("   false positive:", sample)
    golden = audit_output_filter(args.golden_run)
    if golden:
        print(f"output filter on normal answers: blocked {len(golden['blocked'])} of {golden['answers_checked']}")
        for item in golden["blocked"]:
            print("   false positive:", item)

    out = RUNS_DIR / f"security__indirect__{re.sub(r'[^A-Za-z0-9]+', '-', llm.name)}__copies{args.copies}"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "results.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r.__dict__, ensure_ascii=False) + "\n")
    (out / "report.json").write_text(json.dumps(
        {"llm": llm.name, "summary": summary, "scanner": scanner, "output_filter": golden}, indent=2), encoding="utf-8")
    print(f"\nwritten to {out}")


if __name__ == "__main__":
    main()
