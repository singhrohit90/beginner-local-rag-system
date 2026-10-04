import re
import unicodedata


def normalize_key(text: str) -> str:
    """Key used to detect repeated headers/footers: digits collapsed, case and spacing ignored."""
    text = re.sub(r"\d+", "#", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def clean_block(text: str) -> str:
    """Clean one text block (roughly a paragraph). Keeps no newlines inside the block."""
    text = unicodedata.normalize("NFKC", text)  # splits ligatures such as the "fi" glyph
    text = text.replace("­", "")  # soft hyphen
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # re-join words hyphenated across lines
    text = re.sub(r"\s*\n\s*", " ", text)  # soft line breaks inside a paragraph
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def is_noise(text: str) -> bool:
    """True for blocks with no content: empty, or only digits and punctuation (page numbers)."""
    return not re.search(r"[A-Za-z]", text)
