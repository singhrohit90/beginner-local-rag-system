from rag.ingest.export_text import render
from rag.types import Page


def test_render_marks_pages_and_skips_empty_and_index():
    pages = [Page(1, "front"), Page(30, "body text"), Page(31, ""), Page(600, "index entry")]
    text = render(pages, max_page=580, offset=22)
    assert "=== PDF PAGE 1 (front matter) ===" in text
    assert "=== PDF PAGE 30 (printed 8) ===\nbody text" in text
    assert "PAGE 31" not in text and "index entry" not in text
