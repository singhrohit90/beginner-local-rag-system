import json

import pytest

from rag.eval.clean_paste import normalise, parse_objects, repair_text


def test_repairs_markdown_escapes_and_entities():
    raw = '{"a": "followee\\_id -&gt; users", "b": "tab\\there"}'
    text, changes = repair_text(raw)
    obj = json.loads(text)
    assert obj["a"] == "followee_id -> users"
    assert obj["b"] == "tab\there"  # a valid \t escape is left alone
    assert len(changes) == 2


def test_raw_quotes_inside_notes_are_re_escaped():
    raw = ('{"id": "a", "notes": ""He said "hi" here." === PDF PAGE 5 ==="} '
           '{"id": "b", "notes": "plain"}')
    text, changes = repair_text(raw)
    objs = parse_objects(text)
    assert [o["id"] for o in objs] == ["a", "b"]
    assert objs[0]["notes"] == '"He said "hi" here." === PDF PAGE 5 ==='
    assert objs[1]["notes"] == "plain"
    assert any("notes" in c for c in changes)


def test_parses_objects_separated_only_by_spaces():
    text = '{"id": 1} {"id": 2}\n{"id": 3}'
    assert [o["id"] for o in parse_objects(text)] == [1, 2, 3]


def test_unparseable_value_is_reported_not_guessed():
    with pytest.raises(ValueError):
        parse_objects('{"id": 8, "gold_pages": , "x": 1}')


def test_normalise():
    obj, notes = normalise({"id": "a", "answerable": True, "ground_truth_answer": "x",
                            "gold_pages": [1], "must_not_contain": "PWNED"})
    assert obj["reference_answer"] == "x" and obj["must_not_contain"] == ["PWNED"]
    assert any("not a list" in n for n in notes)
