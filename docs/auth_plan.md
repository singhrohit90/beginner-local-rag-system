# Authentication plan for the API (rag/api)

Status: the API has no authentication. It is meant for localhost only (uvicorn binds 127.0.0.1). Do not expose it, and do not put it in a container reachable from other machines, until the steps below are done.

Decision: authentication will be done with Keycloak, not with a home-made API key. So no shared-secret `X-API-Key` check is built.

## Keep (not replaced by Keycloak)
- Check the `Host` header against an allowlist (`127.0.0.1`, `localhost`, later the real hostname). Stops DNS rebinding, which a login does not stop on a local server.
- Check the `Origin` header on POST and DELETE against the server's own origin. Stops other web pages from driving the API from the user's browser. Matters most while sessions use cookies; with bearer tokens in a header it is a second layer.
- Upload checks already in `rag/api/service.py` (`%PDF` content check, size limit, generated ids, id validation before any path use).

## Replace with Keycloak
- Add a token check in `rag/api/main.py` as one FastAPI dependency: validate the bearer JWT (signature against the Keycloak JWKS, issuer, audience, expiry) and read the user id and roles from it.
- Put the user id on every document: write `owner` in `status.json` at upload, and make `list`, `get`, `ask` and `delete` in `rag/api/service.py` refuse documents the caller does not own. This is the access-control test listed as untested in the security plan, and it matters more than the login itself.
- The page (`rag/api/static/index.html`) gets its token through the Keycloak login redirect (authorization code with PKCE) and sends it as `Authorization: Bearer ...`.
- Config from `.env`: `KEYCLOAK_ISSUER`, `KEYCLOAK_AUDIENCE`.

## Later, with the vector database
- Store `owner` (and later groups) as metadata on every chunk, and filter on it inside the database query, not after retrieval. Filtering after retrieval leaks the existence of other users' documents through result counts and lets one user's chunks crowd out another's.
- The per-source cap already uses `meta["source"]`; reuse the same field for ownership checks.

## Storage layout
Keep `data/uploads/<doc_id>/` flat and record `owner` in `status.json`. Do not nest by owner folder: ownership is metadata that moves into the vector database later, the check has to be in the service anyway, and a folder per user makes sharing, user renames and listing harder without adding real protection.

## Clients other than the page (scraper, MCP server)
- The HTTP API is the one contract. The page, a scraping program and an MCP server are all clients of it. Version it (`/v1/...`); FastAPI already publishes the OpenAPI description at `/openapi.json`.
- Origin rule: reject a request only when an `Origin` header is present and not allowed. Programs that are not browsers send no `Origin`, so they are not affected. The Host allowlist must include the real hostname once the API is not on localhost.
- Each program gets its own Keycloak client and uses the client-credentials flow, so it holds a machine identity and a bearer token like any user. Never share one token between the page, the scraper and the MCP server.
- MCP server: a thin separate process (`rag/mcp/` or its own repo) with tools such as `upload_document`, `list_documents`, `ask`. It calls the HTTP API and never imports `rag/api/service.py`, so authentication and the ownership check live in one place.
- Retrieved passages returned to an MCP caller are untrusted text that the caller's own model will read. Return them clearly labelled as quoted source text, and keep the output guard on.
- API additions for programs: dedupe uploads by content hash or a caller-supplied `external_id` so a scraper can retry without duplicates, and keep upload asynchronous with status polling (already the case).

## Order
1. Host and Origin checks (small, useful now).
2. Owner field on documents and the ownership check in the service (works without Keycloak, using a fixed test user). **Done:** `status.json` has `owner`, every service method takes it, another owner's document is a 404, and the owner filter runs inside the store's search; `current_owner` in `rag/api/main.py` is the single place Keycloak will plug in.
3. Keycloak token validation and the login redirect.
4. Owner filter in the vector database query.
