import pymupdf

from rag.ingest.clean import clean_block, is_noise, normalize_key
from rag.ingest.extract import extract_pages, load_pages, save_pages


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
    assert clean_block("exam-\nple of a  soft\nbreak") == "example of a soft break"
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


def test_pages_roundtrip(tmp_path):
    pdf = tmp_path / "book.pdf"
    make_pdf(pdf, n_pages=3)
    pages = extract_pages(pdf)
    out = tmp_path / "out" / "book.pages.jsonl"
    save_pages(pages, out)
    assert load_pages(out) == pages
