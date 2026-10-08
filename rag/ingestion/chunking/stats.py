"""Measure a set of chunks without running any retrieval.

These numbers show what a chunker did to the text. They do not say whether retrieval will work,
but they explain failures: chunks that cut code in half, start mid-sentence, or split the sentence
that holds the answer.
"""

from typing import Any, Dict, List, Sequence

import numpy as np

from rag.observe.golden import GoldQuestion
from rag.observe.retrieval_quality.metrics import norm_text
from rag.common.types import Chunk

_ENDINGS = tuple('.?!:;)"”’]`')


_norm = norm_text


def chunk_stats(chunks: Sequence[Chunk]) -> Dict[str, Any]:
    words = np.array([len(c.text.split()) for c in chunks])
    pages = np.array([c.page_end - c.page_start + 1 for c in chunks])
    return {
        "n": len(chunks),
        "words_p10": int(np.percentile(words, 10)),
        "words_median": int(np.median(words)),
        "words_p90": int(np.percentile(words, 90)),
        "words_max": int(words.max()),
        "mean_pages": round(float(pages.mean()), 2),
        "multi_page_pct": round(100 * float((pages > 1).mean()), 1),
        "mid_sentence_start_pct": round(
            100 * sum(1 for c in chunks if c.text[0].islower()) / len(chunks), 1
        ),
        "mid_sentence_end_pct": round(
            100 * sum(1 for c in chunks if not c.text.endswith(_ENDINGS)) / len(chunks), 1
        ),
        "broken_code_fences": sum(1 for c in chunks if c.text.count("```") % 2 == 1),
    }


def evidence_intact(
    chunks: Sequence[Chunk],
    questions: Sequence[GoldQuestion],
    page_texts: Dict[int, str],
) -> Dict[str, Any]:
    """How often a single chunk still contains the evidence for a gold range.

    For each gold range, the evidence terms that sit on that range's pages must all appear
    together in one chunk that overlaps the range. A question counts as intact only if every one
    of its ranges passes. Large chunks pass easily, so read this next to the size numbers.
    """
    normalised_pages = {n: _norm(t) for n, t in page_texts.items()}
    normalised_chunks = [(c.page_start, c.page_end, _norm(c.text)) for c in chunks]
    checked, failed = 0, []
    for q in questions:
        if not q.answerable or not q.evidence_terms:
            continue
        question_ok, counted = True, False
        for start, end in q.gold_pages:
            terms = [
                _norm(t)
                for t in q.evidence_terms
                if any(_norm(t) in normalised_pages.get(p, "") for p in range(start, end + 1))
            ]
            if not terms:
                continue
            counted = True
            holds = any(
                c_start <= end and c_end >= start and all(t in text for t in terms)
                for c_start, c_end, text in normalised_chunks
            )
            question_ok = question_ok and holds
        if counted:
            checked += 1
            if not question_ok:
                failed.append(q.id)
    return {
        "checked": checked,
        "intact": checked - len(failed),
        "rate": round((checked - len(failed)) / checked, 3) if checked else 0.0,
        "failed": failed,
    }


def format_table(rows: List[Dict[str, Any]]) -> str:
    columns = [
        ("strategy", "strategy", 22),
        ("n", "chunks", 7),
        ("words_p10", "w.p10", 6),
        ("words_median", "w.med", 6),
        ("words_p90", "w.p90", 6),
        ("words_max", "w.max", 6),
        ("multi_page_pct", "%2pg", 6),
        ("mid_sentence_start_pct", "%midS", 6),
        ("mid_sentence_end_pct", "%midE", 6),
        ("broken_code_fences", "badcode", 8),
        ("intact", "intact", 8),
    ]
    lines = ["".join(f"{title:<{w}}" for _, title, w in columns)]
    for row in rows:
        lines.append("".join(f"{str(row.get(key, '')):<{w}}" for key, _, w in columns))
    return "\n".join(lines)
