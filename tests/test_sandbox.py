"""The extraction sandbox: a child process with a time limit and a memory limit."""

import time

import pytest

from rag.api.service import DocumentService
from rag.common.embed import HashingEmbedder
from rag.ingestion.extract import extract_pages, load_pages
from rag.ingestion.sandbox import ExtractionLimit, extract_in_sandbox, run_limited
from rag.common.llm import FakeLLM
from tests.sandbox_targets import fail_quietly, sleep_forever, use_a_gigabyte
from tests.test_api import COMPACTION, REPLICATION, make_pdf


def test_a_child_that_runs_too_long_is_killed():
    started = time.monotonic()
    with pytest.raises(ExtractionLimit, match="longer than 2 seconds"):
        run_limited(sleep_forever, timeout=2, memory_mb=512)
    assert time.monotonic() - started < 30  # it did not wait for the 120 s sleep


def test_a_child_that_needs_too_much_memory_is_stopped():
    with pytest.raises(ExtractionLimit, match="failed"):
        run_limited(use_a_gigabyte, timeout=60, memory_mb=512)


def test_a_child_that_fails_is_reported_without_paths():
    with pytest.raises(ExtractionLimit) as error:
        run_limited(fail_quietly, timeout=60)
    assert "exit code 3" in str(error.value) and "/" not in str(error.value) and "\\" not in str(error.value)


def test_a_normal_pdf_gives_the_same_pages_as_extracting_in_this_process(tmp_path):
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(make_pdf(REPLICATION, COMPACTION))
    pages, toc = tmp_path / "book.pages.jsonl", tmp_path / "book.toc.json"
    extract_in_sandbox(pdf, pages, toc, timeout=120)
    assert [p.text for p in load_pages(pages)] == [p.text for p in extract_pages(pdf)]
    assert toc.exists() and not list(tmp_path.glob("*.tmp"))  # temporary names were renamed away


def test_one_huge_block_is_cut_to_the_page_limit(tmp_path):
    pdf = tmp_path / "big.pdf"
    pdf.write_bytes(make_pdf("word " * 1000))
    full = extract_pages(pdf)
    capped = extract_pages(pdf, max_page_chars=300)
    assert len(full[0].text) > 1000 and len(capped[0].text) <= 300


def test_a_slow_extraction_marks_the_document_failed_with_a_readable_reason(tmp_path):
    service = DocumentService(root=tmp_path / "uploads", embedder=HashingEmbedder(), embedder_spec="hash",
                              llm=FakeLLM(lambda system, user: "x"), extract_timeout=0.01)
    doc_id = service.create("book.pdf", make_pdf(REPLICATION), "local")["id"]
    service.run_ingestion(doc_id)  # starting a Python child takes longer than 0.01 s
    status = service.get(doc_id, "local")
    assert status["state"] == "failed" and "longer than" in status["error"]
    assert str(tmp_path) not in status["error"]


def test_no_memory_limit_means_the_file_is_not_run(monkeypatch):
    import sys

    from rag.ingestion import sandbox

    if sys.platform != "win32":
        pytest.skip("the Windows job object is the only limit set by the parent")
    monkeypatch.setattr(sandbox, "_limit_memory_windows", lambda pid, mb: False)
    with pytest.raises(ExtractionLimit, match="memory limit"):
        sandbox.run_limited(sleep_forever, timeout=30, memory_mb=512)


def test_the_child_cannot_start_more_processes_to_get_more_memory():
    import sys

    from tests.sandbox_targets import start_another_process

    if sys.platform != "win32":
        pytest.skip("the one-process limit is a Windows job object setting")
    with pytest.raises(ExtractionLimit, match="failed"):
        run_limited(start_another_process, timeout=60, memory_mb=512)


def test_pages_that_are_together_far_larger_than_a_book_are_refused(tmp_path, monkeypatch):
    from rag.ingestion import sandbox

    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(make_pdf(REPLICATION, COMPACTION))
    monkeypatch.setattr(sandbox, "DEFAULT_MAX_TOTAL_CHARS", 100)
    with pytest.raises(SystemExit) as stop:
        sandbox._extract_to_files(str(pdf), str(tmp_path / "p.jsonl"), str(tmp_path / "t.json"), 50_000)
    assert stop.value.code == 5 and not (tmp_path / "p.jsonl").exists()
