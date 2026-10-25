"""Service and route tests of the rewrite step behind the RAG_REWRITE switch (rag/api/service.py,
rag/query/rewrite.py). Fake models only; a real client is used only with urllib.request.urlopen patched.
The helpers come from the Phase 2 test module, which is not edited."""

import json
import urllib.error

import pytest

from rag.api.conversations import new_turn
from rag.common.embed import HashingEmbedder
from rag.common.llm import FakeLLM, get_llm
from rag.common.trace import load_trace
from rag.query.rewrite import REWRITE_SYSTEM_PROMPT
from tests.test_api import COMPACTION, REPLICATION
from tests.test_conversations import (add_document, client_for, conversation_file, make_service, recording,
                                      seed_turns, stored)
from tests.test_ollama import FakeResponse
from tests.test_stream_api import frames

RAFT_TURN = ("How does replication work in the Raft design?", "Raft keeps copies on several nodes and elects a leader.")
PRONOUN = "and how does that compare to the other book?"
OFF = {"status": "off", "reason": None, "rewritten_question": None}
SEVEN_KEYS = {"question", "rewritten", "answer", "doc_ids", "asked_at", "query_id", "scan"}
FOUR_KEYS = {"id", "turn", "history_turns", "dropped_turns"}
FAILURE_SHAPES = {  # case id -> (what the rewriter does, the reason code the caller sees)
    "refused": (urllib.error.URLError(ConnectionRefusedError()), "unavailable"),
    "cannot_reach": (RuntimeError("cannot reach the model server at 127.22.10.1:30007"), "unavailable"),
    "ollama_serve": (RuntimeError("Ollama is not running; start it with ollama serve"), "unavailable"),
    "timeout_error": (TimeoutError(), "timeout"),
    "timed_out_text": (RuntimeError("the request timed out"), "timeout"),
    "empty": ("", "empty"),
    "prose": ("Sure, here is the standalone question you asked for.", "unparsed"),
}
LEAKS = ("127.22.10.1", "ollama serve")  # exception text that must never reach the caller


def rewriter(*replies):
    """A fake rewriter that records (system, user) and plays its replies in order, the last repeating."""
    seen = []
    script = list(replies)

    def reply(system, user):
        seen.append((system, user))
        value = script.pop(0) if len(script) > 1 else script[0]
        if isinstance(value, BaseException):
            raise value
        return value

    return FakeLLM(reply), seen


def rewrite_service(tmp_path, *replies, llm=None):
    """A service with the switch on and a scripted rewriter; returns it and the rewriter's prompts."""
    fake, seen = rewriter(*replies)
    return make_service(tmp_path, llm=llm, rewrite=True, rewrite_llm=fake), seen


def append_flagged_turn(service, owner, doc_ids, cid, question, answer, resolved, kind="answer", topic_start=False):
    """Store a turn carrying kind and topic_start flags, which seed_turns cannot write."""
    conversation = service.conversations.open(owner, doc_ids, cid)
    service.conversations.append_turn(
        conversation, new_turn(question, answer, resolved, "seed-flag", kind=kind, topic_start=topic_start),
        lambda ids: True)


def trace_of(service, doc_id, result):
    """The saved trace of a single-document question."""
    return load_trace(service.root / doc_id / "chat" / f"{result['query_id']}.json")


def test_the_first_turn_makes_no_rewrite_call(tmp_path):
    service, seen = rewrite_service(tmp_path, "REWRITE: should never be used")
    doc_id = add_document(service, REPLICATION)
    first = service.ask_documents("local", [doc_id], PRONOUN)
    assert seen == []
    assert first["rewrite"] == {"status": "skipped", "reason": None, "rewritten_question": None}
    assert first["kind"] == "answer"
    trace = trace_of(service, doc_id, first)
    assert trace.question == PRONOUN
    assert trace.config["conversation"]["rewrite"] == "skipped"


def test_the_pronoun_follow_up_makes_exactly_one_rewrite_call(tmp_path):
    rewrite = "How does replication in the Raft design compare to Paxos-notes.pdf?"
    service, seen = rewrite_service(tmp_path, "REWRITE: " + rewrite)
    raft = add_document(service, REPLICATION, name="raft.pdf")
    paxos = add_document(service, COMPACTION, name="Paxos-notes.pdf")
    cid = seed_turns(service, "local", None, [raft, paxos], [RAFT_TURN])
    result = service.ask_documents("local", None, PRONOUN, conversation_id=cid)
    assert len(seen) == 1
    system, user = seen[0]
    assert system == REWRITE_SYSTEM_PROMPT
    assert "raft.pdf" in user and "Paxos-notes.pdf" in user
    assert user.splitlines()[-1] == "Last message: " + PRONOUN
    assert result["rewrite"]["status"] == "rewritten"
    assert result["rewrite"]["rewritten_question"] == rewrite


def test_the_trace_the_response_and_the_turn_record_both_texts(tmp_path):
    rewrite = "How does replication keep copies on several nodes?"
    service, seen = rewrite_service(tmp_path, "REWRITE: " + rewrite)
    doc_id = add_document(service, REPLICATION)
    cid = seed_turns(service, "local", [doc_id], [doc_id], [("What does replication keep?", "Copies on several nodes.")])
    result = service.ask_documents("local", [doc_id], "and why that?", conversation_id=cid)
    trace = trace_of(service, doc_id, result)
    assert trace.question == rewrite
    conversation = trace.config["conversation"]
    assert set(conversation) == FOUR_KEYS | {"original_question", "rewritten_question", "rewrite",
                                             "fallback_reason", "rewrite_ms", "rejected_question"}
    assert conversation["original_question"] == "and why that?"
    assert conversation["rewritten_question"] == rewrite
    assert conversation["rewrite"] == "rewritten"
    assert conversation["fallback_reason"] is None and conversation["rejected_question"] is None
    assert conversation["rewrite_ms"] >= 0
    assert result["rewrite"] == {"status": "rewritten", "reason": None, "rewritten_question": rewrite}
    last = stored(conversation_file(service, "local", [doc_id], cid))["turns"][-1]
    assert last["question"] == "and why that?" and last["rewritten"] == rewrite
    assert set(last) == SEVEN_KEYS


def test_a_long_marker_free_message_passes_unchanged_with_no_call(tmp_path):
    service, seen = rewrite_service(tmp_path, "REWRITE: should never be used")
    doc_id = add_document(service, REPLICATION)
    cid = seed_turns(service, "local", [doc_id], [doc_id], [("What does replication keep?", "Copies on several nodes.")])
    message = "Explain how quorum reads guarantee visibility of committed writes in leaderless systems"
    result = service.ask_documents("local", [doc_id], message, conversation_id=cid)
    assert seen == []
    assert result["rewrite"]["status"] == "skipped"
    assert trace_of(service, doc_id, result).question == message


def test_with_the_switch_off_nothing_changes(tmp_path):
    fake, seen = rewriter("CLARIFY: Raft or Paxos?")
    llm, asked = recording()
    service = make_service(tmp_path, llm=llm, rewrite_llm=fake)  # switch off, rewriter present
    doc_id = add_document(service, REPLICATION)
    sent = ["What does replication keep?", "and why that?", "and how?"]
    results = [service.ask_documents("local", [doc_id], sent[0])]
    cid = results[0]["conversation_id"]
    append_flagged_turn(service, "local", [doc_id], cid, "Tell me about compaction", "It merges segments.", [doc_id],
                        kind="clarify", topic_start=True)
    for message in sent[1:]:
        results.append(service.ask_documents("local", [doc_id], message, conversation_id=cid))
    assert seen == []
    for message, result in zip(sent, results):
        assert result["rewrite"] == OFF and result["kind"] == "answer"
        trace = trace_of(service, doc_id, result)
        assert set(trace.config["conversation"]) == FOUR_KEYS
        assert trace.question == message
    assert "What does replication keep?" in asked[-1][1]  # the stored flags do not cut the Phase 2 window
    turns = stored(conversation_file(service, "local", [doc_id], cid))["turns"]
    assert [t["question"] for t in turns] == [sent[0], "Tell me about compaction", sent[1], sent[2]]
    for index in (0, 2, 3):
        assert set(turns[index]) == SEVEN_KEYS, turns[index]


def test_the_switch_needs_a_rewriter(tmp_path):
    with pytest.raises(ValueError):
        make_service(tmp_path, rewrite=True)


def spied_settings(monkeypatch, tmp_path):
    """build_default_service offline: no .env, a temporary data folder, a hashing embedder and a get_llm
    spy that records (spec, cache_dir). Returns the call list."""
    import rag.api.main as main

    built = []
    monkeypatch.setattr("rag.common.secrets.load_env", lambda *args, **kwargs: None)
    monkeypatch.setattr("rag.common.config.DATA_DIR", tmp_path)
    monkeypatch.setattr("rag.common.embed.get_embedder", lambda spec: HashingEmbedder())
    monkeypatch.setattr("rag.common.llm.get_llm",
                        lambda spec, cache_dir="UNSET": built.append((spec, cache_dir)) or FakeLLM(lambda s, u: "x"))
    monkeypatch.setenv("RAG_STORE", "memory")
    monkeypatch.setenv("RAG_EMBEDDER", "hash-for-this-test")
    for name in ("RAG_REWRITE", "RAG_REWRITER", "RAG_LLM"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(main, "_EMBEDDERS", {})  # nothing loaded here outlives the test
    return built


def test_build_default_service_ships_the_switch_off(monkeypatch, tmp_path):
    from rag.api.main import build_default_service

    built = spied_settings(monkeypatch, tmp_path)
    service = build_default_service()
    assert service.rewrite is False and service.rewrite_llm is None
    assert len(built) == 1 and built[0][1] is None


@pytest.mark.parametrize("value, spec, on", [("0", None, False), ("true", None, False), ("on", None, False),
                                             ("1", None, True), ("1", "ollama:llama3.2", True)])
def test_build_default_service_builds_the_rewriter_only_when_on(monkeypatch, tmp_path, value, spec, on):
    from rag.api.main import build_default_service

    built = spied_settings(monkeypatch, tmp_path)
    monkeypatch.setenv("RAG_REWRITE", value)
    if spec:
        monkeypatch.setenv("RAG_REWRITER", spec)
    service = build_default_service()
    assert service.rewrite is on
    if on:
        assert len(built) == 2 and built[1] == (spec or "ollama:qwen2.5:7b", None)
        assert service.rewrite_llm is not None
    else:
        assert len(built) == 1 and service.rewrite_llm is None
    assert all(cache_dir is None for _, cache_dir in built), built


def test_a_pronoun_follow_up_is_rewritten_and_retrieval_runs_on_the_rewrite(tmp_path):
    llm, asked = recording()
    service, seen = rewrite_service(tmp_path, "REWRITE: How does compaction merge sorted segments?", llm=llm)
    replication = add_document(service, REPLICATION, name="replication.pdf")
    compaction = add_document(service, COMPACTION, name="compaction.pdf")
    cid = seed_turns(service, "local", None, [replication, compaction],
                     [("What does replication keep?", "Copies on several nodes.")])
    message = "and how does that work for the other one?"
    result = service.ask_documents("local", None, message, conversation_id=cid)
    assert len(seen) == 1 and result["rewrite"]["status"] == "rewritten"
    assert result["passages"][0]["doc_name"] == "compaction.pdf"
    assert "Question: How does compaction merge sorted segments?" in asked[-1][1]
    assert message not in asked[-1][1].split("Question:")[-1]


def test_the_streamed_response_has_the_same_rewrite_and_kind_as_the_ordinary_one(tmp_path):
    service, seen = rewrite_service(tmp_path, "REWRITE: How does replication keep copies on several nodes?")
    doc_id = add_document(service, REPLICATION)
    client = client_for(service)
    turn = [("What does replication keep?", "Copies on several nodes.")]
    one = seed_turns(service, "local", [doc_id], [doc_id], turn)
    two = seed_turns(service, "local", [doc_id], [doc_id], turn)
    ordinary = client.post(f"/v1/documents/{doc_id}/ask", json={"question": "and why that?", "conversation_id": one})
    streamed = client.post(f"/v1/documents/{doc_id}/ask/stream",
                           json={"question": "and why that?", "conversation_id": two})
    assert ordinary.status_code == 200 and streamed.status_code == 200
    events = frames(streamed)
    name, final = events[-1]
    body = ordinary.json()
    assert name == "final"
    assert final["kind"] == body["kind"] == "answer"
    assert final["rewrite"] == body["rewrite"]
    assert body["rewrite"]["status"] == "rewritten"
    assert len(seen) == 2


@pytest.mark.parametrize("streamed", [False, True], ids=["ordinary", "streamed"])
@pytest.mark.parametrize("case", list(FAILURE_SHAPES))
def test_a_rewriter_failure_is_a_visible_fallback_before_any_sse_byte(tmp_path, case, streamed):
    reply, reason = FAILURE_SHAPES[case]
    llm, asked = recording()
    service, seen = rewrite_service(tmp_path, reply, llm=llm)
    doc_id = add_document(service, REPLICATION)
    turn = [("What does replication keep?", "Copies on several nodes.")]
    fb = {"status": "fallback", "reason": reason, "rewritten_question": None}
    client = client_for(service)
    if not streamed:
        cid = seed_turns(service, "local", [doc_id], [doc_id], turn)
        response = client.post(f"/v1/documents/{doc_id}/ask", json={"question": "and why that?", "conversation_id": cid})
        assert response.status_code == 200
        body = response.json()
        assert body["rewrite"] == fb and body["answer"]
        assert len(seen) == 1 and len(asked) == 1
        trace = trace_of(service, doc_id, body)
        assert trace.question == "and why that?"
        assert trace.config["conversation"]["fallback_reason"] == reason
        assert not any(leak in response.text for leak in LEAKS)
        return
    cid = seed_turns(service, "local", [doc_id], [doc_id], turn)
    events = service.ask_documents_stream("local", [doc_id], "and why that?", conversation_id=cid)
    assert len(seen) == 1  # the rewrite was decided before the first event was read
    read = list(events)
    assert read[-1]["event"] == "final" and read[-1]["data"]["rewrite"] == fb
    assert not any(event["event"] == "error" for event in read)
    assert trace_of(service, doc_id, read[-1]["data"]).config["conversation"]["fallback_reason"] == reason
    other = seed_turns(service, "local", [doc_id], [doc_id], turn)
    response = client.post(f"/v1/documents/{doc_id}/ask/stream",
                           json={"question": "and why that?", "conversation_id": other})
    assert response.status_code == 200
    names = [name for name, _ in frames(response)]
    assert names[-1] == "final" and "error" not in names
    assert frames(response)[-1][1]["rewrite"] == fb
    assert not any(leak in response.text for leak in LEAKS)
    assert len(seen) == 2 and len(asked) == 2  # one answer-model call per question


def test_a_real_ollama_client_that_is_down_gives_unavailable(tmp_path, monkeypatch):
    real = get_llm("ollama:qwen2.5:7b", cache_dir=None)
    service = make_service(tmp_path, rewrite=True, rewrite_llm=real)

    def refuse(request, timeout=None):
        raise urllib.error.URLError(ConnectionRefusedError())

    monkeypatch.setattr("urllib.request.urlopen", refuse)
    doc_id = add_document(service, REPLICATION)
    cid = seed_turns(service, "local", [doc_id], [doc_id], [("What does replication keep?", "Copies on several nodes.")])
    response = client_for(service).post(f"/v1/documents/{doc_id}/ask",
                                        json={"question": "and why that?", "conversation_id": cid})
    assert response.status_code == 200
    assert response.json()["rewrite"] == {"status": "fallback", "reason": "unavailable", "rewritten_question": None}
    assert not any(leak in response.text for leak in LEAKS)


def test_the_real_ollama_request_for_a_rewrite_is_pinned(tmp_path, monkeypatch):
    real = get_llm("ollama:qwen2.5:7b", cache_dir=None)
    service = make_service(tmp_path, rewrite=True, rewrite_llm=real)
    sent = []

    def capture(request, timeout=None):
        sent.append((json.loads(request.data), timeout))
        body = {"message": {"content": "STANDALONE"}, "prompt_eval_count": 40, "eval_count": 2, "done_reason": "stop"}
        return FakeResponse(json.dumps(body).encode())

    monkeypatch.setattr("urllib.request.urlopen", capture)
    doc_id = add_document(service, REPLICATION)
    cid = seed_turns(service, "local", [doc_id], [doc_id], [("What does replication keep?", "Copies on several nodes.")])
    result = service.ask_documents("local", [doc_id], "and why that?", conversation_id=cid)
    assert len(sent) == 1
    payload, timeout = sent[0]
    assert payload["options"]["temperature"] == 0.0 and payload["options"]["num_predict"] == 120
    assert "format" not in payload  # no json_mode
    assert payload["messages"][0] == {"role": "system", "content": REWRITE_SYSTEM_PROMPT}
    # characterised on the first run (RESEARCH A2): the option keys and the client's timeout
    assert sorted(payload["options"]) == ["num_ctx", "num_predict", "temperature"]
    assert timeout == 600.0
    assert result["rewrite"]["status"] == "standalone"


TWO_NAMES_TURN = ("How do Raft and Paxos elect a leader?", "Both elect a leader by majority vote.")
CLARIFY_LINE = "CLARIFY: Do you mean Raft or Paxos?"
# The page reads these from the final event without a guard (rag/api/static/index.html lines 287-326),
# so a clarifying question must carry every one of them.
PAGE_KEYS = ("answer", "blocked", "citations", "skipped_by_scanner", "passages", "stages", "llm", "seconds",
             "abstained", "documents", "query_id", "conversation_id", "turn", "kind", "rewrite")


def ask(service, client, doc_id, cid, message, streamed):
    """Post to the ordinary or the streamed route; returns (status_code, data, frame_names, text), where for a
    stream data is the last frame's data and frame_names lists every frame."""
    url = f"/v1/documents/{doc_id}/ask" + ("/stream" if streamed else "")
    response = client.post(url, json={"question": message, "conversation_id": cid})
    if response.status_code != 200 or not streamed:
        return response.status_code, response.json(), [], response.text
    events = frames(response)
    return response.status_code, events[-1][1], [name for name, _ in events], response.text


@pytest.mark.parametrize("streamed", [False, True], ids=["ordinary", "streamed"])
def test_a_clarifying_question_uses_the_normal_shape(tmp_path, streamed):
    llm, asked = recording()
    service, seen = rewrite_service(tmp_path, CLARIFY_LINE, llm=llm)
    doc_id = add_document(service, REPLICATION)
    cid = seed_turns(service, "local", [doc_id], [doc_id], [TWO_NAMES_TURN])
    client = client_for(service)
    status, data, names, _ = ask(service, client, doc_id, cid, "how does it handle failures?", streamed)
    assert status == 200
    assert all(key in data for key in PAGE_KEYS), [key for key in PAGE_KEYS if key not in data]
    assert data["kind"] == "clarify" and data["answer"] == "Do you mean Raft or Paxos?"
    assert data["passages"] == [] and data["citations"] == [] and data["stages"] == []
    assert data["abstained"] is False and data["blocked"] == [] and data["skipped_by_scanner"] == []
    assert data["llm"] == service.rewrite_llm.name
    assert data["query_id"].startswith("clarify-")
    assert data["conversation_id"] == cid and data["turn"] == 2
    assert data["rewrite"] == {"status": "clarify", "reason": None, "rewritten_question": None}
    assert asked == [] and len(seen) == 1  # no answer-model call
    assert not list((service.root / doc_id / "chat").glob("clarify-*.json"))  # no trace written
    if streamed:
        assert names == ["final"] and data["replace"] is False
        other = seed_turns(service, "local", [doc_id], [doc_id], [TWO_NAMES_TURN])
        events = list(service.ask_documents_stream("local", [doc_id], "how does it handle failures?",
                                                   conversation_id=other))
        assert [event["event"] for event in events] == ["final"]


def test_a_clarification_is_stored_with_its_kind(tmp_path):
    service, seen = rewrite_service(tmp_path, CLARIFY_LINE)
    doc_id = add_document(service, REPLICATION)
    service.conversations.max_turns = 2
    cid = seed_turns(service, "local", [doc_id], [doc_id], [TWO_NAMES_TURN])
    result = service.ask_documents("local", [doc_id], "how does it handle failures?", conversation_id=cid)
    assert result["kind"] == "clarify"
    turn = stored(conversation_file(service, "local", [doc_id], cid))["turns"][1]
    assert set(turn) == SEVEN_KEYS | {"kind"}
    assert turn["kind"] == "clarify" and turn["question"] == "how does it handle failures?"
    assert turn["answer"] == "Do you mean Raft or Paxos?" and turn["rewritten"] is None
    full = client_for(service).post(f"/v1/documents/{doc_id}/ask",
                                    json={"question": "Raft, please", "conversation_id": cid})
    assert full.status_code == 409
    assert full.json() == {"detail": "this conversation is full; start a new conversation"}
