# Phase 5: Chat page and honest docs - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-22
**Phase:** 05-chat-page-and-honest-docs
**Mode:** `--auto` — every question took the recommended option without a user prompt
**Areas discussed:** Conversation id on the page, Stale id and 409 handling, Clarifying question, Page verification, Docs, UI design contract

---

## Conversation id on the page

Selected: one `conversationId` variable set from each response; reset on New conversation, scope change, document change, checkbox change, deleting a targeted document; reset also clears the log.

## Stale id and 409 handling

| Option | Description | Selected |
|--------|-------------|----------|
| On 404 "no such conversation": clear id, notice, resend once without id | User never left with an error to clear | ✓ |
| Show the 404 as an error | Matches today but fails ROADMAP SC2 | |

409 full: show message and hint, keep id; 409 busy: show message; superseded stream cannot set the id.

## Clarifying question

Selected: ordinary assistant bubble via `textContent`, "clarifying question" label, no passages panel.

## Page verification

Selected: static checks plus API tests from earlier phases plus a manual browser checklist marked `human_needed` (non-blocking in the unattended run).

## Docs

Selected: README Step 11 with numbers from `docs/chat_memory_eval.md`; backlog marks done and adds compaction, retention, reload-resume, panel; interview relabels only built-and-measured points; provisional results stated as provisional.

## UI design contract

Selected: reuse existing styles; no UI-SPEC needed (auto-generated only if the gate demands it).

## Claude's Discretion

- Notice wording, button placement, Step 11 order

## Deferred Ideas

- Reload-resume GET, conversation list, rewritten question panel, turn counter
