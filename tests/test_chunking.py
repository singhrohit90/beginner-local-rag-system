import re

import pytest

from rag.ingestion.chunking import (
    FixedChunker,
    HeadingChunker,
    ParentChildChunker,
    RecursiveChunker,
    SemanticChunker,
)
from rag.ingestion.chunking.document import Document, body_range
from rag.ingestion.chunking.heading import sections
from rag.ingestion.chunking.stats import chunk_stats, evidence_intact
from rag.ingestion.chunking.units import atomic_units, blocks, pack, sentences, words_of
from rag.common.embed import HashingEmbedder
from rag.observe.golden import GoldQuestion
from rag.common.types import Page


def para(topic: str, sentences_count: int) -> str:
    return " ".join(
        f"This sentence number {i} explains {topic} in some detail." for i in range(sentences_count)
    )


CODE = "```\nSELECT *\n  FROM tweets\n  WHERE id = 1\n```"

PAGES = [
    Page(10, "CHAPTER 1 Basics\n\n" + para("basics", 4) + "\n\nStorage\n\n" + para("storage", 12)),
    Page(11, para("storage", 6) + "\n\nIndexes\n\n" + para("indexes", 3) + "\n\n" + CODE),
    Page(12, para("indexes", 5) + "\n\nTiny\n\nOne short line.\n\nReplication\n\n" + para("replicas", 20)),
]
TOC = [
    {"level": 2, "title": "Chapter 1. Basics", "page": 10},
    {"level": 3, "title": "Storage", "page": 10},
    {"level": 3, "title": "Indexes", "page": 11},
    {"level": 3, "title": "Tiny", "page": 12},
    {"level": 3, "title": "Replication", "page": 12},
]


@pytest.fixture
def doc():
    return Document.from_pages(PAGES, TOC)


def covered_words(doc, chunks):
    mask = bytearray(len(doc.text))
    for c in chunks:
        start, end = c.meta["span"]
        mask[start:end] = b"\x01" * (end - start)
    return sum(1 for m in re.finditer(r"\S+", doc.text) if not mask[m.start()])


def test_document_maps_offsets_to_pages(doc):
    assert doc.page_of(0) == 10
    marker = doc.text.index("Indexes")
    assert doc.page_of(marker) == 11
    assert doc.page_span(0, len(doc.text)) == (10, 12)
    assert body_range([{"title": "Part I. X", "page": 23}, {"title": "Glossary", "page": 575}]) == (23, 574)


def test_blocks_keep_code_whole_and_split_paragraphs(doc):
    kinds = [b.kind for b in blocks(doc)]
    assert kinds.count("code") == 1
    code = next(b for b in blocks(doc) if b.kind == "code")
    assert doc.text[code.start : code.end] == CODE
    assert all(b.words > 0 for b in blocks(doc))


def test_sentences_split_on_sentence_ends(doc):
    para_unit = blocks(doc)[1]
    parts = sentences(doc, para_unit)
    assert len(parts) > 1
    assert all(doc.text[p.start : p.end].endswith(".") for p in parts)


def test_pack_respects_size_and_overlap():
    doc = Document.from_pages([Page(1, " ".join(f"w{i}" for i in range(100)))])
    spans = pack(words_of(doc), size=10, overlap=3)
    texts = [doc.text[s:e].split() for s, e in spans]
    assert all(len(t) <= 10 for t in texts)
    assert texts[0][-3:] == texts[1][:3]
    assert texts[1][0] == "w7"  # window advances by size - overlap


def test_fixed_chunker_covers_everything_and_cuts_code(doc):
    result = FixedChunker(size=7, overlap=2).chunk(doc)  # the listing has 10 words, so it must break
    assert covered_words(doc, result.chunks) == 0
    assert all(len(c.text.split()) <= 7 for c in result.chunks)
    assert len({c.chunk_id for c in result.chunks}) == len(result.chunks)
    assert any(c.text.count("```") % 2 == 1 for c in result.chunks)  # the baseline breaks code


def test_recursive_chunker_keeps_code_whole_and_ends_on_sentences(doc):
    result = RecursiveChunker(size=40, overlap=10).chunk(doc)
    assert covered_words(doc, result.chunks) == 0
    assert all(c.text.count("```") % 2 == 0 for c in result.chunks)
    assert any(CODE in c.text for c in result.chunks)
    prose = [c for c in result.chunks if "```" not in c.text]
    assert all(len(c.text.split()) <= 40 for c in prose)
    assert sum(c.text.endswith(".") for c in prose) / len(prose) > 0.8


def test_oversize_code_is_split_by_lines_not_words():
    big = "```\n" + "\n".join(f"line_{i} = {i}" for i in range(50)) + "\n```"
    doc = Document.from_pages([Page(1, "Intro sentence here.\n\n" + big)])
    units = atomic_units(doc, 0, len(doc.text), size=30, code_max=40)
    assert any(u.kind == "line" for u in units)


def test_sections_find_headings_and_build_breadcrumbs(doc):
    secs = sections(doc)
    titles = [s.title for s in secs]
    assert titles[0] == "Chapter 1. Basics"
    assert "Chapter 1. Basics > Storage" in titles
    assert "Chapter 1. Basics > Indexes" in titles
    storage = next(s for s in secs if s.path[-1] == "Storage")
    assert doc.text[storage.start :].startswith("Storage")
    assert doc.page_of(storage.start) == 10
    indexes = next(s for s in secs if s.path[-1] == "Indexes")
    assert doc.page_of(indexes.start) == 11  # found mid-page, not at the page top


def test_heading_chunker_splits_at_headings_merges_tiny_and_splits_large(doc):
    result = HeadingChunker(min_words=30, max_words=60).chunk(doc)
    assert covered_words(doc, result.chunks) == 0
    sections_seen = {c.section for c in result.chunks}
    assert "Chapter 1. Basics > Storage" in sections_seen
    assert not any((s or "").endswith("Tiny") for s in sections_seen)  # stub absorbed by Replication
    replication = [c for c in result.chunks if (c.section or "").endswith("Replication")]
    assert any("One short line." in c.text for c in replication)  # and its text is still there
    assert len(replication) > 1  # 20 sentences do not fit one 60-word chunk
    assert all(len(c.text.split()) <= 60 for c in replication)
    # no chunk crosses into another section's heading (a merged stub is the one allowed exception)
    for c in result.chunks:
        for other in ("Storage", "Indexes"):
            body = c.text[len(other) + 1 :] if c.text.startswith(other) else c.text
            assert f"\n\n{other}\n\n" not in body


def test_parent_child_links_children_to_parents(doc):
    result = ParentChildChunker(parent_min=30, parent_max=120, child_size=25, child_overlap=5).chunk(doc)
    assert result.parents
    assert covered_words(doc, result.chunks) == 0
    for child in result.chunks:
        parent = result.parents[child.meta["parent_id"]]
        p_start, p_end = parent.meta["span"]
        c_start, c_end = child.meta["span"]
        assert p_start <= c_start and c_end <= p_end
        assert child.text.count("```") % 2 == 0
    assert max(len(p.text.split()) for p in result.parents.values()) <= 120
    assert sum(len(c.text.split()) for c in result.chunks) < sum(len(p.text.split()) for p in result.parents.values()) * 1.6


def test_semantic_chunker_cuts_at_topic_change_with_guards():
    cats = " ".join(f"The cat number {i} chased a small grey mouse across the garden." for i in range(12))
    dbs = " ".join(f"Database replica {i} applies the write ahead log entries in order." for i in range(12))
    doc = Document.from_pages([Page(1, cats + " " + dbs)])
    result = SemanticChunker(HashingEmbedder(), percentile=90, min_words=20, max_words=400).chunk(doc)
    assert covered_words(doc, result.chunks) == 0
    assert len(result.chunks) >= 2
    mixed = [c for c in result.chunks if "cat number" in c.text and "Database replica" in c.text]
    assert len(mixed) <= 1  # at most the chunk that straddles the single topic boundary
    capped = SemanticChunker(HashingEmbedder(), percentile=99.9, min_words=5, max_words=40).chunk(doc)
    assert all(len(c.text.split()) <= 40 + 12 for c in capped.chunks)  # max_words guard


def test_stats_and_evidence_intact(doc):
    result = FixedChunker(size=7, overlap=0).chunk(doc)
    stats = chunk_stats(result.chunks)
    assert stats["n"] == len(result.chunks) and stats["broken_code_fences"] >= 1
    page_texts = {p.page_no: p.text for p in doc.pages}
    q_ok = GoldQuestion("a", "?", "factual", True, "x", [(11, 11)], evidence_terms=["WHERE id = 1"])
    q_split = GoldQuestion("b", "?", "factual", True, "x", [(11, 11)],
                           evidence_terms=["SELECT *", "WHERE id = 1"])
    report = evidence_intact(RecursiveChunker(size=40, overlap=0).chunk(doc).chunks, [q_ok, q_split], page_texts)
    assert report["rate"] == 1.0
    tiny = evidence_intact(FixedChunker(size=3, overlap=0).chunk(doc).chunks, [q_split], page_texts)
    assert tiny["failed"] == ["b"]


def test_make_chunker_picks_a_strategy_by_name():
    from rag.ingestion.chunk import make_chunker

    assert type(make_chunker("fixed", size=50)).__name__ == "FixedChunker"
    assert type(make_chunker("heading", max_words=120)).__name__ == "HeadingChunker"
    with pytest.raises(ValueError, match="needs an embedder"):
        make_chunker("semantic")
    with pytest.raises(ValueError, match="unknown chunking strategy"):
        make_chunker("nope")
