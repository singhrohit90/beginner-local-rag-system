---
status: testing
phase: 01-safety-net-and-prompt-seam
source: [01-VERIFICATION.md]
started: 2026-10-25T00:00:00Z
updated: 2026-10-25T00:00:00Z
---

## Current Test

number: 1
name: Read max_model_len from the model server and record it
expected: |
  The command prints (model id, max_model_len); docs/models.md names the number, the model id and the date; test_history.py's check of MODEL_CONTEXT_TOKENS against the Context window section still passes; the D-11 worst-case budget test still fits.
awaiting: user response

## Tests

### 1. Reconnect the PuTTY tunnel to 127.22.10.1:30007, then run the one-off command recorded in docs/models.md (Context window) to read max_model_len, and write the number into docs/models.md and into MODEL_CONTEXT_TOKENS in rag/query/history.py (currently the 8192 floor).
expected: The command prints (model id, max_model_len); docs/models.md names the number, the model id and the date; test_history.py's check of MODEL_CONTEXT_TOKENS against the Context window section still passes; the D-11 worst-case budget test still fits.
result: [pending]

### 2. Confirm the gitignored .env does not set RAG_NONCE_KEY (judgment-tier prohibition of plan 01-01).
expected: No RAG_NONCE_KEY line in .env. Every snapshot test fixes rag.security.defenses._NONCE_KEY with monkeypatch, so the tests pass whatever .env holds.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
