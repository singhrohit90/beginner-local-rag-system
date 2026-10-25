"""Service and route tests of the rewrite step behind the RAG_REWRITE switch (rag/api/service.py,
rag/query/rewrite.py). Fake models only; a real client is used only with urllib.request.urlopen patched.
The helpers come from the Phase 2 test module, which is not edited."""

import pytest

from rag.api.conversations import new_turn
from rag.common.embed import HashingEmbedder
from rag.common.llm import FakeLLM
from rag.common.trace import load_trace
from rag.query.rewrite import REWRITE_SYSTEM_PROMPT
from tests.test_api import COMPACTION, REPLICATION
from tests.test_conversations import (add_document, client_for, conversation_file, make_service, recording,
                                      seed_turns, stored)
from tests.test_stream_api import frames

RAFT_TURN = ("How does replication work in the Raft design?", "Raft keeps copies on several nodes and elects a leader.")
PRONOUN = "and how does that compare to the other book?"
OFF = {"status": "off", "reason": None, "rewritten_question": None}
SEVEN_KEYS = {"question", "rewritten", "answer", "doc_ids", "asked_at", "query_id", "scan"}
FOUR_KEYS = {"id", "turn", "history_turns", "dropped_turns"}


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
