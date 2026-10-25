"""Service and route tests of the rewrite step behind the RAG_REWRITE switch (rag/api/service.py,
rag/query/rewrite.py). Fake models only; a real client is used only with urllib.request.urlopen patched.
The helpers come from the Phase 2 test module, which is not edited."""

from rag.api.conversations import new_turn
from rag.common.llm import FakeLLM
from rag.common.trace import load_trace
from rag.query.rewrite import REWRITE_SYSTEM_PROMPT
from tests.test_api import COMPACTION, REPLICATION
from tests.test_conversations import add_document, conversation_file, make_service, seed_turns, stored

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
