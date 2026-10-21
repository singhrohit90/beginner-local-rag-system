# Phase 2: Conversation store and memory in the answer prompt - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-22
**Phase:** 02-conversation-store-and-memory-in-the-answer-prompt
**Mode:** `--auto` — every question took the recommended option without a user prompt
**Areas discussed:** D1 cross-document storage, Conversation identity and lookup, File format and concurrency, What a turn stores, History in the prompt, Budget and hard cap (D3), Cache and isolation, Module split

---

## D1 cross-document storage

| Option | Description | Selected |
|--------|-------------|----------|
| A: store under `data/uploads/_conversations/<owner_key>/`, cascade on delete | Memory works in the page's default multi-document flow | ✓ |
| B: refuse history for cross-document scope, `conversation_id: null` plus message | Smaller; no new delete path | |

## Conversation identity and lookup

| Option | Description | Selected |
|--------|-------------|----------|
| 32 hex `secrets.token_hex(16)`, validated in the store so a malformed id is the same 404 | One body for every miss (CONV-02) | ✓ |
| Pydantic `pattern=` validation | Malformed id would be a 422, a different body | |

Scope binding: conversation bound to its starting scope; a different scope is the same 404.

## File format and concurrency

| Option | Description | Selected |
|--------|-------------|----------|
| One JSON file rewritten atomically | ARCHITECTURE.md recommendation; reuses `_atomic_write` pattern | ✓ |
| Append-only JSONL under a lock | Torn-last-line case to parse | |

| Option | Description | Selected |
|--------|-------------|----------|
| 409 for a second request while one holds the conversation lock | Every window complete | ✓ |
| Lock only the write | A later window may miss a turn | |

## What a turn stores

Selected: question, rewritten (null), answer as shown, resolved doc_ids, UTC timestamp, query_id, scan rule names; persisted on the success path only; kept even when `keep_traces=False` (flagged).

## History in the prompt

Selected: window 6, neutralize every stored question and answer, `render_block` into `history_block`; retrieval still on the raw message; trace block `conversation` with dropped-turn count.

## Budget and hard cap (D3)

| Option | Description | Selected |
|--------|-------------|----------|
| Option A numbers (6 / 400 / 40 / 60 / 50 turns) plus 20,000 stored words | Safe at the 8192 floor | ✓ |
| Option B numbers (6 / 600 / 60 / 20 turns / 8,000 words) | Needs a measured larger window | |

Cap refused with 409 before any model call and any SSE byte; a second budget check covers a long live question.

## Cache and isolation

Selected: spy test that every service `get_llm` call has `cache_dir=None`.

## Module split

Selected: `rag/api/conversations.py` new; `service.py` and `main.py` wire it; `tests/test_conversations.py` plus additions to `tests/test_api.py` and `tests/test_stream_api.py`.

## Claude's Discretion

- `ConversationStore` method names, exact error strings, where `_describe` adds the fields

## Deferred Ideas

- GET resume and explicit conversation delete (v2), per-turn citations (v2), retention TTL, larger caps by measurement, page plumbing (Phase 5)
