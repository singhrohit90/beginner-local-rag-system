import pymupdf

from rag.ingestion.clean import clean_block, is_noise, normalize_key
from rag.ingestion.extract import (
    _line_text,
    extract_pages,
    extract_toc,
    load_pages,
    save_pages,
)


def make_pdf(path, n_pages=6):
    doc = pymupdf.open()
    for i in range(1, n_pages + 1):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 30), "Chapter 3. Storage and Retrieval", fontsize=9)  # header
        page.insert_text((72, 120), f"Body paragraph for page {i} about SSTables.", fontsize=11)
        page.insert_text((72, 140), "A second paragraph on LSM-trees.", fontsize=11)
        page.insert_text((290, 815), str(i + 70), fontsize=9)  # printed page number
    doc.save(path)
    doc.close()


def test_clean_block():
    assert clean_block("exam‐\nple of a  soft\nbreak") == "example of a soft break"
    assert clean_block("multi-\nmachine setups") == "multi-machine setups"  # real hyphen kept
    assert clean_block("a read‐only copy") == "a read-only copy"
    assert clean_block("oﬃce ﬁle") == "office file"  # ligatures
    assert is_noise("  71 ") and is_noise("") and not is_noise("Chapter 3")
    assert normalize_key("Page 71 of 600") == normalize_key("page 72 of 600")


def test_extract_removes_running_header_and_page_numbers(tmp_path):
    pdf = tmp_path / "book.pdf"
    make_pdf(pdf)
    pages = extract_pages(pdf)
    assert [p.page_no for p in pages] == [1, 2, 3, 4, 5, 6]
    for page in pages:
        assert "Chapter 3" not in page.text
        assert str(page.page_no + 70) not in page.text.split()
        assert f"page {page.page_no} about SSTables" in page.text
        assert "LSM-trees" in page.text


def test_running_footer_pattern_removed_even_when_text_never_repeats(tmp_path):
    doc = pymupdf.open()
    titles = ["Reliability", "Scalability", "Replication", "Partitioning", "Transactions"]
    for i, title in enumerate(titles, start=1):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 120), f"Body text number {i} about {title.lower()}.", fontsize=11)
        footer = f"{title} | {i + 8}" if i % 2 else f"{i + 8} | Chapter {i}: {title}"
        page.insert_text((72, 815), footer, fontsize=9)
    path = tmp_path / "footers.pdf"
    doc.save(path)
    doc.close()
    for i, page in enumerate(extract_pages(path), start=1):
        assert "|" not in page.text
        assert f"Body text number {i}" in page.text


def test_code_block_keeps_lines_and_indent_and_is_fenced(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 120), "You could write a query such as the following one:", fontsize=11)
    code = "SELECT *\n    FROM tweets\n    WHERE id = 1"
    page.insert_text((72, 160), code, fontsize=9, fontname="cour")
    page.insert_text((72, 260), "That query is slow for large tables.", fontsize=11)
    path = tmp_path / "code.pdf"
    doc.save(path)
    doc.close()
    text = extract_pages(path)[0].text
    assert "```\nSELECT *\n    FROM tweets\n    WHERE id = 1\n```" in text
    assert text.index("You could write") < text.index("```") < text.index("That query")


def test_superscript_is_marked():
    plain = {"text": "fan-out", "flags": 6}
    sup = {"text": "ii", "flags": 5}
    assert _line_text([plain, sup]) == "fan-out^ii"
    assert _line_text([{"text": "10", "flags": 4}, {"text": "9", "flags": 5}]) == "10^9"


def test_toc_extracted(tmp_path):
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page()
    doc.set_toc([[1, "Chapter One", 1], [2, "Section A", 2]])
    path = tmp_path / "toc.pdf"
    doc.save(path)
    doc.close()
    assert extract_toc(path) == [
        {"level": 1, "title": "Chapter One", "page": 1},
        {"level": 2, "title": "Section A", "page": 2},
    ]


def test_pages_roundtrip(tmp_path):
    pdf = tmp_path / "book.pdf"
    make_pdf(pdf, n_pages=3)
    pages = extract_pages(pdf)
    out = tmp_path / "out" / "book.pages.jsonl"
    save_pages(pages, out)
    assert load_pages(out) == pages


def test_a_monospaced_block_made_only_of_blanks_does_not_crash():
    from rag.ingestion.extract import _block_text

    span = {"text": "    ", "flags": 8, "bbox": (10, 10, 50, 20)}  # 8 = monospaced
    block = {"lines": [{"spans": [span], "bbox": (10, 10, 50, 20)}, {"spans": [span], "bbox": (10, 22, 50, 32)}]}
    text, is_code = _block_text(block)
    assert text.strip() == "" and is_code is False
