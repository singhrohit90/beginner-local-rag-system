"""Locate where gold evidence was lost, using only the trace and the gold pages.

This covers the retrieval half of the debugging checklist. Generation faithfulness and
correctness need an answer judge, which is added with the generation step.
"""

from typing import Dict, Optional, Sequence

from rag.eval.metrics import PageRange, first_relevant_rank
from rag.trace import Trace


def stage_ranks(trace: Trace, gold_pages: Sequence[PageRange]) -> Dict[str, Optional[int]]:
    """Rank of the first gold-relevant hit at every stage, in pipeline order. None = absent."""
    return {s.name: first_relevant_rank(s.hits, gold_pages) for s in trace.stages}


def locate_failure(trace: Trace, gold_pages: Sequence[PageRange]) -> str:
    """One label naming the first point where gold evidence went missing.

    retrieval_miss  : no retrieve stage surfaced it. Check extraction, chunking, k, query text.
    lost_at_<stage> : it was present earlier and this stage dropped it. Fix that stage.
    retrieval_ok    : still present in the final stage. Any wrong answer is a prompt or
                      generation problem (or the gold label is wrong).
    no_stages       : the pipeline recorded nothing, which is itself a bug.
    """
    if not trace.stages:
        return "no_stages"
    ranks = stage_ranks(trace, gold_pages)
    retrieve_present = any(
        ranks[s.name] is not None for s in trace.stages if s.kind == "retrieve"
    )
    if not retrieve_present:
        return "retrieval_miss"
    previous_present = True
    for stage in trace.stages:
        present = ranks[stage.name] is not None
        if stage.kind == "transform" and previous_present and not present:
            return f"lost_at_{stage.name}"
        if stage.kind == "transform":
            previous_present = present
    return "retrieval_ok"
