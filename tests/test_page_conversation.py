"""Static and behaviour tests for the chat page's conversation handling.

The behaviour tests run the page's real script in node (tests/page_harness.js) against a fake DOM and a stubbed
fetch, so they need no browser, model or network; like the page syntax test, they skip when node is missing.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.test_api import make_client

HARNESS = Path(__file__).with_name("page_harness.js")
SERVER_STRINGS = {  # the three conversation bodies guarded() in rag/api/main.py returns
    "gone": "no such conversation",
    "full": "this conversation is full; start a new conversation",
    "busy": "conversation is busy, retry when the previous answer is finished",
}
A_ID, B_ID, C_ID, D_ID = "a" * 32, "b" * 32, "c" * 32, "d" * 32


def page_text(tmp_path) -> str:
    """The page under test: the served page, or the file named by PAGE_UNDER_TEST.

    PAGE_UNDER_TEST is test-only. It lets the fail-first proof run these tests against an older page kept in a
    scratch file, without ever putting that page into the working tree or the index."""
    override = os.environ.get("PAGE_UNDER_TEST")
    if override:
        return Path(override).read_text(encoding="utf-8")
    client, _ = make_client(tmp_path)
    return client.get("/").text


def script_text(tmp_path) -> str:
    return re.search(r"<script>(.*)</script>", page_text(tmp_path), re.S).group(1)


def run_harness(tmp_path, scenario: str) -> Dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    run = subprocess.run([node, str(HARNESS), scenario, json.dumps(SERVER_STRINGS)], input=script_text(tmp_path),
                         capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["ok"], out.get("error")
    return out["obs"]


def test_a_follow_up_sends_the_id_the_first_answer_returned(tmp_path):
    obs = run_harness(tmp_path, "follow_up")
    bodies = obs["askBodies"]
    assert len(bodies) == 2
    assert set(bodies[0]) == {"question", "doc_ids", "config"}
    assert set(bodies[1]) == {"question", "doc_ids", "config", "conversation_id"}
    assert bodies[1]["conversation_id"] == A_ID
    assert bodies[0]["doc_ids"] is None  # scope "all my documents"
    assert obs["conversationId"] == A_ID
    assert "How does replication survive a node failure?" in obs["logText"]
    assert "and what about its drawbacks?" in obs["logText"]
    assert obs["errorText"] == ""


def test_new_conversation_clears_the_log_and_the_next_question_has_no_id(tmp_path):
    obs = run_harness(tmp_path, "new_conversation")
    assert obs["afterAsk"] == A_ID
    assert obs["afterReset"]["id"] is None
    assert obs["afterReset"]["logText"] == ""
    assert obs["afterReset"]["detailText"] == "Click an answer to see its passages and stage timings."
    assert len(obs["askBodies"]) == 2 and "conversation_id" not in obs["askBodies"][1]
    assert obs["conversationId"] == B_ID


def test_each_target_change_drops_the_id_and_a_highlight_does_not(tmp_path):
    steps = run_harness(tmp_path, "target_change")["steps"]
    expected = {
        "asked_all": (A_ID, False),
        "highlight_all": (A_ID, False),  # under "all my documents" a row click only highlights
        "scope_change": (None, True),
        "asked_one": (B_ID, False),
        "same_doc_one": (B_ID, False),
        "other_doc_one": (None, True),
        "asked_checked": (C_ID, False),
        "checkbox_checked": (None, True),
        "asked_before_delete": (D_ID, False),
        "deleted_target": (None, True),
    }
    assert {name: (s["id"], s["logEmpty"]) for name, s in steps.items()} == expected


def test_a_stale_id_starts_a_new_conversation_with_one_resend(tmp_path):
    obs = run_harness(tmp_path, "stale_404")
    bodies = obs["askBodies"]
    assert len(bodies) == 2
    assert bodies[0]["conversation_id"] == A_ID
    assert "conversation_id" not in bodies[1] and bodies[1]["question"] == bodies[0]["question"]
    assert "Started a new conversation (the previous one is no longer available)." in obs["logText"]
    assert obs["errorText"] == ""
    assert obs["conversationId"] == B_ID


def test_another_404_is_an_ordinary_error_without_a_retry(tmp_path):
    obs = run_harness(tmp_path, "other_404")
    assert len(obs["askBodies"]) == 1 and obs["askBodies"][0]["conversation_id"] == A_ID
    assert "404: no such document" in obs["errorText"]
    assert "no answer" in obs["logText"]
    assert obs["conversationId"] == A_ID
    assert "Started a new conversation" not in obs["logText"]
