"""A short profile of a document: what it is, what it covers, who it is for.

Questions such as "when should I use this book and when that one?" are about the documents, not in
them, so no chunk of text answers them. The profile gathers what the PDF itself says about the whole:
its name, page count, table of contents and the opening pages (a preface or "who this book is for").
It is built from text that extraction already produced, so it needs no model and cannot invent
anything. rag/query/about.py answers from profiles; the normal query pipeline does not use them.

    profile.json   next to the document's other files, so deleting the document deletes it too
"""

import re
from typing import Any, Dict, List, Sequence

from rag.common.types import Page

PROFILE_FILE = "profile.json"
PROFILE_VERSION = 2  # a stored profile of another version is built again
TOC_LEVELS = 2  # chapters and their sections; deeper levels are detail
TOC_ENTRIES = 80
TITLE_PAGE_CHARS = 600
OPENING_CHARS = 2500
OPENING_SEARCH_PAGES = 60  # a preface sits in the first pages
_OPENING_HEADING = re.compile(
    r"^\s*(preface|foreword|introduction|who (?:this|the) (?:book|guide) is for|audience|about this (?:book|guide))\b",
    re.IGNORECASE | re.MULTILINE,
)


_CONTENTS_PAGE = re.compile(r"^\s*(table of )?contents\b", re.IGNORECASE)


def _opening(pages: Sequence[Page], toc: Sequence[dict]) -> Dict[str, Any]:
    """The text that most likely says what the document is for: the pages where a preface or an
    introduction starts, found through the contents list when it names one, else by looking for such a
    heading on a page (skipping the contents page, which lists the word without saying anything),
    else the first pages with text after the title page."""
    candidates = [p for p in pages[:OPENING_SEARCH_PAGES] if p.text.strip()]
    for entry in toc:
        if _OPENING_HEADING.match(entry.get("title", "")) and entry.get("page", 0) <= OPENING_SEARCH_PAGES:
            start = [i for i, p in enumerate(candidates) if p.page_no >= entry["page"]]
            if start:
                text = "\n\n".join(p.text for p in candidates[start[0]:start[0] + 2])
                return {"opening_page": candidates[start[0]].page_no, "opening": text[:OPENING_CHARS]}
    for index, page in enumerate(candidates):
        if _CONTENTS_PAGE.match(page.text):
            continue
        if _OPENING_HEADING.search(page.text[:400]):
            text = "\n\n".join(p.text for p in candidates[index:index + 2])
            return {"opening_page": page.page_no, "opening": text[:OPENING_CHARS]}
    text = "\n\n".join(p.text for p in candidates[1:3])
    return {"opening_page": candidates[1].page_no if len(candidates) > 1 else None, "opening": text[:OPENING_CHARS]}


def build_profile(name: str, pages: Sequence[Page], toc: Sequence[dict]) -> Dict[str, Any]:
    """The profile of one document, as plain data that can be saved as JSON."""
    first = next((p for p in pages if p.text.strip()), None)
    outline: List[dict] = [e for e in toc if e.get("level", 1) <= TOC_LEVELS][:TOC_ENTRIES]
    return {
        "version": PROFILE_VERSION,
        "name": name,
        "pages": len(pages),
        "toc_total": len(toc),
        "toc": outline,
        "title_page": first.text[:TITLE_PAGE_CHARS] if first else "",
        **_opening(pages, toc),
    }
