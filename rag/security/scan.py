"""An ingestion-time scanner for instruction-like text inside documents.

It is a simple rule list, so it is easy to read, test and bypass. It exists to measure what a
keyword filter buys you: what fraction of injected documents it catches, how many ordinary book
chunks it wrongly flags, and which attacks walk straight past it (other languages, paraphrase).
Never treat a scanner like this as the only defence.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Sequence

_FLAGS = re.IGNORECASE

RULES: Dict[str, "re.Pattern[str]"] = {
    "ignore-previous": re.compile(
        r"\b(ignore|disregard|forget|override)\b.{0,25}\b(previous|prior|above|earlier|all|the)\b"
        r".{0,25}\b(instructions?|rules?|guidance|prompts?)\b", _FLAGS),
    "role-notice": re.compile(
        r"\b(system|internal|admin(istrator)?|developer|editorial)\s+"
        r"(notice|instruction|message|prompt|override|policy|rule)\b", _FLAGS),
    "address-the-model": re.compile(
        r"\b(for|to)\s+(the\s+)?(ai|assistant|llm|model|chatbot)s?\b|\bai assistants?\b", _FLAGS),
    "output-directive": re.compile(
        r"\b(begin|start|open|end|finish|append|prefix)\b.{0,30}\b(your|the)\s+"
        r"(answer|reply|response|output)\b", _FLAGS),
    "reply-only": re.compile(r"\b(reply|respond|answer|write)\s+(only|exclusively)\b", _FLAGS),
    "reveal-prompt": re.compile(
        r"\b(print|reveal|repeat|output|show)\b.{0,40}\b(system (prompt|instructions?)|"
        r"internal reference)\b", _FLAGS),
    "exfil-image-or-link": re.compile(r"!\[[^\]]*\]\(https?://[^)]*\)|https?://\S+\?\S*=", _FLAGS),
    "fake-boundary": re.compile(r"-{2,}\s*(end|begin)\s+of\s+(passages|context)", _FLAGS),
    "spoofed-citation": re.compile(r"\[S\d+\]"),
}


@dataclass
class ScanResult:
    flagged: bool
    rules: List[str]


def scan_text(text: str) -> ScanResult:
    hits = [name for name, pattern in RULES.items() if pattern.search(text)]
    return ScanResult(bool(hits), hits)


def scan_chunks(chunks: Sequence) -> Dict[str, ScanResult]:
    """Scan every chunk and return the result per chunk id."""
    return {c.chunk_id: scan_text(c.text) for c in chunks}
