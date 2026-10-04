import re
import unicodedata


def normalize_key(text: str) -> str:
    """Key used to detect repeated headers/footers: digits collapsed, case and spacing ignored."""
    text = re.sub(r"\d+", "#", text.lower())
    return re.sub(r"\s+", " ", text).strip()


# O'Reilly style running footers: "42 | Chapter 3: Storage" or "Replication | 179".
_FOOTER_RE = re.compile(r"^\s*\d+\s*\|\s*\S.*$|^.*\S\s*\|\s*\d+\s*$", re.DOTALL)


def clean_block(text: str) -> str:
    """Clean one text block (roughly a paragraph). Keeps no newlines inside the block.

    Line-break hyphens are the typographic hyphen U+2010 (or a soft hyphen) and are joined away.
    An ASCII hyphen at a line end is a real hyphen, so it is kept ("multi-\\nmachine" becomes
    "multi-machine"). Change this if a source PDF breaks words with ASCII hyphens.
    """
    text = unicodedata.normalize("NFKC", text)  # splits ligatures such as the "fi" glyph
    text = re.sub(r"[‐­]\s*\n\s*", "", text)  # hyphenated line break: join the word
    text = re.sub(r"(?<=\w)-\s*\n\s*", "-", text)  # real hyphen at a line end: keep it
    text = text.replace("‐", "-")  # remaining typographic hyphens are real hyphens
    text = text.replace("­", "")
    text = re.sub(r"\s*\n\s*", " ", text)  # soft line breaks inside a paragraph
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def is_running_footer(text: str) -> bool:
    """A margin block that carries a page number next to a pipe, such as "Reliability | 9"."""
    return bool(_FOOTER_RE.match(text)) and len(text) < 120


def is_noise(text: str) -> bool:
    """True for blocks with no content: empty, or only digits and punctuation (page numbers)."""
    return not re.search(r"[A-Za-z]", text)
