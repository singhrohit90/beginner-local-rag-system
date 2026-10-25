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
        text = Path(override).read_text(encoding="utf-8")
    else:
        client, _ = make_client(tmp_path)
        text = client.get("/").text
    return text.replace("\r\n", "\n")  # the checkout may have CRLF line ends


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


def test_conversation_conflicts_read_as_sentences_and_keep_the_id(tmp_path):
    obs = run_harness(tmp_path, "conflict_409")
    full, busy = obs["full"], obs["busy"]
    assert len(full["askBodies"]) == 1 and full["askBodies"][0]["conversation_id"] == A_ID
    assert SERVER_STRINGS["full"] + " Use the New conversation button." in full["errorText"]
    assert "409:" not in full["errorText"]
    assert full["conversationId"] == A_ID and full["sendDisabled"] is False
    assert len(busy["askBodies"]) == 2  # the busy answer is not retried
    assert SERVER_STRINGS["busy"] in busy["errorText"] and "409:" not in busy["errorText"]
    assert busy["conversationId"] == A_ID and busy["sendDisabled"] is False


def test_a_clarifying_question_shows_markup_as_text(tmp_path):
    obs = run_harness(tmp_path, "clarify")
    shown, after = obs["shown"], obs["after"]
    assert "Do you mean <b>x</b> or the other one?" in shown["logText"]
    assert "clarifying question" in shown["logText"]
    assert "B" not in shown["logTags"]  # the tag stayed text; no element was made from it
    assert shown["detailText"] == "A clarifying question: no passages were retrieved for it."
    assert "Stages" not in shown["detailText"] and "Passages sent to the model" not in shown["detailText"]
    assert shown["conversationId"] == A_ID
    assert after["askBodies"][1]["conversation_id"] == A_ID


def test_a_superseded_ask_is_aborted_and_cannot_bring_its_id_back(tmp_path):
    obs = run_harness(tmp_path, "superseded")
    assert obs["abortedAtReset"] is True
    assert obs["conversationId"] is None
    assert obs["logText"] == "" and obs["errorText"] == ""
    assert obs["sendDisabled"] is False
    assert len(obs["askBodies"]) == 1


def test_the_page_declares_one_conversation_id_and_sends_it_only_when_set(tmp_path):
    page = page_text(tmp_path)
    assert page.count("let conversationId = null, epoch = 0, inflight = null;") == 1
    assert "if (conversationId) body.conversation_id = conversationId;" in page
    assert "conversationId = r.conversation_id" in page
    for stored in ("localStorage", "sessionStorage", "document.cookie"):
        assert stored not in page
    assert all("conversation" not in line for line in page.splitlines() if "/v1/ask-about" in line)


def test_the_new_conversation_button_does_not_submit_and_sits_before_ask(tmp_path):
    page = page_text(tmp_path)
    assert '<button type="button" id="newconv"' in page
    assert (page.index('id="question"') < page.index('id="scope"') < page.index('id="config"')
            < page.index('id="newconv"') < page.index('id="send"'))
    assert '$("newconv").onclick' in page


def test_every_target_change_resets_the_conversation(tmp_path):
    page = page_text(tmp_path)

    def cut(start: str, end: str) -> str:
        at = page.index(start)
        return page[at:page.index(end, at)]

    assert page.count("resetConversation(") == 7  # the definition and six call sites
    scope_line = next(line for line in page.splitlines() if '$("scope").onchange' in line)
    assert "resetConversation(" in scope_line
    select = cut("function select(", "function scopeLabel")
    assert "resetConversation(" in select and '$("scope").value === "one"' in select
    pick = cut("pick.onclick", "node.prepend(pick)")
    assert "resetConversation(" in pick and '$("scope").value === "checked"' in pick
    delete = cut("del.onclick", 'node.append(el("div", {}, del))')
    assert delete.index("targets()") < delete.index("await") < delete.index("resetConversation(")
    upload = cut('$("upload").onsubmit', "async function streamAsk")
    assert upload.index("resetConversation(") < upload.index("selected = d.id")


def test_a_stale_id_is_retried_once_and_other_errors_are_not(tmp_path):
    page = page_text(tmp_path)
    assert 'const CONV_GONE = "no such conversation";' in page
    assert "sent && err.status === 404 && err.detail === CONV_GONE" in page
    assert page.count("Started a new conversation (the previous one is no longer available).") == 1
    at = page.index("function askContent(")
    ask_content = page[at:page.index("\n}\n", at)]
    assert ask_content.count("streamAsk(") == 2 and "delete body.conversation_id;" in ask_content


def test_a_running_ask_can_be_cancelled(tmp_path):
    page = page_text(tmp_path)
    assert page.count("new AbortController") == 1
    at = page.index("async function streamAsk")
    assert "signal" in page[at:page.index("getReader", at)]
    assert "inflight.abort()" in page
    assert "if (mine !== epoch) return;" in page


def test_a_clarifying_question_is_labelled_and_has_no_passages_panel(tmp_path):
    page = page_text(tmp_path)
    assert 'r.kind === "clarify"' in page
    assert "clarifying question" in page
    assert "function detailClarify()" in page


def test_the_page_builds_no_markup_from_text(tmp_path):
    page = page_text(tmp_path)
    assert page.count("innerHTML") == 1 and "innerHTML" not in page.replace("never innerHTML", "")
    for markup in ("outerHTML", "insertAdjacentHTML", "document.write"):
        assert markup not in page
    assert page.count("</script>") == 1
    # the strings this phase added reach the DOM through el() and text nodes
    assert 'msg.before(el("div", { class: "meta" }, note))' in page
    assert 'el("small", { class: "meta" }, "clarifying question")' in page


def test_the_page_matches_the_server_conversation_errors(tmp_path):
    main = (Path(__file__).resolve().parent.parent / "rag" / "api" / "main.py").read_text(encoding="utf-8")
    for text in SERVER_STRINGS.values():
        assert text in main
    page = page_text(tmp_path)
    for text in ("no such conversation", "conversation is full", "conversation is busy"):
        assert text in page
