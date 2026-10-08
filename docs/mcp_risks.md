# Risks of an MCP server on top of this API (to address when it is built)

Status: no MCP server exists. This is the checklist to work through before building one. The design is in `docs/auth_plan.md`: the MCP server is a thin separate process that calls the HTTP API (`/v1`) with its own identity and never imports `rag/api/service.py`.

Each risk has what can go wrong, then the planned fix.

## 1. Indirect prompt injection into the caller's model
`ask` returns retrieved passages and an answer. The model that called the MCP tool reads them. A poisoned document can carry instructions aimed at that model, which has its own tools and context, so our scanner and output filter do not protect it.
Fix: return passages inside a clearly labelled "quoted source text, not instructions" envelope; keep the scanner and output filter on; return a `flagged` marker per passage; document that callers must treat tool output as data.

## 2. Data leaving through rendered output
An answer can contain a markdown image or link that sends data to an outside host when the caller's client renders it. Our output filter blocks external images and URLs not in the retrieved text, but only for answers produced here.
Fix: keep that filter in the API, strip markdown images and links from MCP responses by default, and test it with the existing exfiltration fixture (P03).

## 3. Confused deputy and shared credentials
If the MCP server holds one broad credential, every MCP user can reach every document.
Fix: the MCP server must act as the end user (token exchange or the user's own token passed through the MCP authorization flow), or be limited to a service account that owns only its own documents. The API checks `owner` on every call (see the ownership step in `docs/auth_plan.md`). Never ship a version where the API trusts the MCP server to enforce ownership.

## 4. Too much power exposed as tools
A model can call any tool it is given, including by mistake or after an injection. `delete_document` and `upload_document` change state.
Fix: expose read tools (`list_documents`, `ask`) by default; put `upload_document` and `delete_document` behind a separate scope and require explicit confirmation in the client; never expose bulk delete.

## 5. Upload tool as a file or network reader
An upload tool that accepts a local path or a URL lets a model make the server read arbitrary files or call internal addresses (SSRF).
Fix: accept file content from the client, not a server-side path; if URL fetch is added, use an allowlist of hosts, block private and link-local addresses, cap size and time, and fetch outside the API process.

## 6. Stolen or over-broad tokens
Tokens for the MCP server and the scraper are bearer credentials.
Fix: one Keycloak client per program, short token lifetime, scopes per tool (read, write, delete), no token written to logs or tool output. The MCP authorization spec is OAuth based, which fits Keycloak; check the current spec before building, this is from memory.

## 7. Cost and abuse
Every `ask` calls the language model, and every upload runs embedding on a shared GPU. A looping agent can run up cost or starve other users.
Fix: rate limit per client, a per-client daily budget for `ask`, a queue length limit and per-user upload quota, and a hard cap on question and upload size (the upload cap already exists).

## 8. Tool description tampering
Clients trust tool names and descriptions. A changed description can steer the caller's model.
Fix: keep tool descriptions in version control, review changes like code, pin the MCP server version in the client.

## 9. Information leaks through listing and errors
`list_documents`, error text and result counts can reveal other users' documents or file names.
Fix: filter by owner inside the query (not after), return generic errors, never echo server paths or stack traces to the caller (the API currently returns the exception text on a 502; shorten it for non-local callers).

## 10. Logging sensitive content
Questions, answers and passages can hold private text. Chat traces are saved inside each document's folder (`data/uploads/<doc_id>/chat/`) and the API does not use the LLM disk cache, so deleting a document removes them.
Fix still open: decide retention for documents that are not deleted, who may read traces, an owner field on traces, and redaction before traces are shared for evaluation.

## 11. Contract drift
A scraper or MCP server breaks if the API changes under it.
Fix: keep `/v1` stable, add fields without removing any, publish the OpenAPI file with each release, add contract tests that call the API as the MCP server does.

## Tests to write when the MCP server is built
- A poisoned upload does not make the MCP response carry instructions outside the labelled envelope.
- A user cannot list, ask on, or delete another user's document through the MCP server.
- An answer containing an external image link is stripped.
- A request without the delete scope cannot delete.
- An upload by path or by internal URL is refused.
