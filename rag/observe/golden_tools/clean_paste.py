"""Repair question files pasted out of chat tools, then write strict JSONL.

    python -m rag.observe.golden_tools.clean_paste data/golden/batch3.jsonl data/golden/batch3.clean.jsonl

Fixes what chat UIs commonly do to JSON: markdown escapes such as \\_ , HTML entities such as
&gt; , several objects on one line, and must_not_contain given as a string. It does not guess
missing values: bad gold_pages are reported, not invented.
"""

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

_BAD_ESCAPE = re.compile(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})')


# notes is the last key of each object, so its value ends at the first "} that is followed by the
# next object or the end of the text. Models often put raw double quotes inside it.
_NOTES = re.compile(r'"notes":\s*"(.*?)"\}(?=\s*(?:\{"id"|\Z))', re.DOTALL)


def _fix_notes(text: str) -> Tuple[str, int]:
    count = 0

    def replace(match: "re.Match[str]") -> str:
        nonlocal count
        body = match.group(1)
        try:
            json.loads(f'"{body}"')
            return match.group(0)  # already valid
        except json.JSONDecodeError:
            count += 1
            return '"notes": ' + json.dumps(body, ensure_ascii=False) + "}"

    return _NOTES.sub(replace, text), count


def repair_text(text: str) -> Tuple[str, List[str]]:
    changes = []
    removed = sorted({m.group(0) + (text[m.end()] if m.end() < len(text) else "") for m in _BAD_ESCAPE.finditer(text)})
    fixed, n = _BAD_ESCAPE.subn("", text)
    if n:
        # name them: a pattern such as \\d inside evidence text would otherwise change without notice
        changes.append(f"removed {n} invalid backslash escapes, kinds: {', '.join(removed[:8])}")
    fixed, n = _fix_notes(fixed)
    if n:
        changes.append(f"re-escaped raw double quotes inside notes in {n} objects")
    unescaped = html.unescape(fixed)
    if unescaped != fixed:
        changes.append("decoded HTML entities such as &gt;")
    return unescaped, changes


def parse_objects(text: str) -> List[Dict[str, Any]]:
    """Read concatenated JSON objects, whether separated by newlines or only by spaces."""
    decoder = json.JSONDecoder()
    objects, pos = [], 0
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            return objects
        try:
            obj, pos = decoder.raw_decode(text, pos)
        except json.JSONDecodeError as err:
            context = text[max(0, err.pos - 60) : err.pos + 60].replace("\n", " ")
            raise ValueError(f"{err.msg} near: ...{context}...") from err
        objects.append(obj)


def normalise(obj: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    notes = []
    if isinstance(obj.get("must_not_contain"), str):
        obj["must_not_contain"] = [obj["must_not_contain"]]
        notes.append("must_not_contain converted to a list")
    if "ground_truth_answer" in obj and "reference_answer" not in obj:
        obj["reference_answer"] = obj.pop("ground_truth_answer")
    obj.setdefault("evidence_terms", [])
    obj.setdefault("notes", "")
    pages = obj.get("gold_pages", [])
    if obj.get("answerable") and not all(
        isinstance(p, list) and len(p) == 2 and all(isinstance(n, int) for n in p) for p in pages
    ):
        notes.append(f"gold_pages {pages!r} is not a list of [start, end] pairs")
    return obj, notes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()

    text, changes = repair_text(args.source.read_text(encoding="utf-8"))
    try:
        objects = parse_objects(text)
    except ValueError as err:
        print("Could not parse:", err)
        raise SystemExit(1)

    problems = []
    with open(args.out, "w", encoding="utf-8") as f:
        for obj in objects:
            obj, notes = normalise(obj)
            problems += [f"{obj.get('id', '?')}: {n}" for n in notes if "converted" not in n]
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(f"{len(objects)} questions -> {args.out}")
    for change in changes:
        print("  fixed:", change)
    for problem in problems:
        print("  PROBLEM:", problem)


if __name__ == "__main__":
    main()
