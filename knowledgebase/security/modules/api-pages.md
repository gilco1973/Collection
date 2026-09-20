# Security review sheet: Reader endpoints

| | |
| --- | --- |
| Module id | `api-pages` |
| Kind | backend |
| Code | `kb_librarian/api/routes_pages.py` |
| Tests | `tests/test_api_pages.py`, `tests/test_retrieval_api.py`, `tests/test_review_round*.py` |
| Depends on | `api-core`, `checks` (sensitive), `service.py`, `retrieval` |

## Purpose

Everything a reader (viewer role, unauthenticated) can call: `GET /api/me`, `/contract`,
`/sections`, `/sections/{id}/pages`, `/pages`, `/pages/{path}`, `/pages/{path}/findings`,
`/search`, `/files/{path}` (raw YAML catalogs), and `POST /pages/{path}/reports` (problem reports).

## Entry points

The routes above, mounted under `/api`. Optional `lang` on content routes. `/pages` takes the
optional filters `owner`, `stale`, `audience` (the console's "for you" list sends the reader's
persona as `audience`) and `limit`; `/search` takes `q`, `section`, `status`, `audience`, `owner`,
`stale` and `mode` (`keyword|semantic|hybrid`, default `hybrid`, regex-validated). All filters are
applied by `service.search` to page metadata. `mode` decides the order: keyword (catalog order of
substring matches), semantic (`AppState.retriever()` over the embedding index, best chunk per page),
or their reciprocal-rank fusion; the semantic pass (`retrieval.state.semantic_hits`) passes the
catalog's readable paths minus `withheld_paths` as `allowed_paths`, so a withheld page is excluded
inside the index query and again in `service.search`. Without an index, a blank `q`, or an embedder
failure every mode is keyword and the response says `"mode": "keyword"`; otherwise `mode` echoes the
effective mode. Items keep their shape and gain `excerpt` (the best chunk's 300-character excerpt for a
semantic hit, `null` otherwise).

## Trust boundaries

All inputs are untrusted. `path` parameters are looked up in the catalog (dictionary), never
joined to the filesystem — except `/files/{path}`, which accepts only paths listed in the
contract's `catalogs`, refuses symlinks, and re-checks the resolved path is under the docs root.

## Data handled

Page bodies and metadata (Internal tier), findings for a page, problem reports written by
readers to `.librarian/problems/<id>.json` (`category`, `message` ≤ 1000 chars, page owner,
timestamp; both text fields pass through `redact()`).

## Secrets

None. Withheld pages return `body_markdown: null` with redacted metadata; a withheld catalog
file returns 404.

## External calls

None.

## Mutations

Only problem reports (append-only JSON files). Throttled 5 per client per minute; queue capped
at `KB_MAX_PROBLEM_REPORTS` (500) → 429 when full.

## Controls in place

- Query validation: `q` ≤ 200 chars, `stale` pattern, `limit` 1–1000, `status` alias, `mode` pattern.
- The query text goes to the embedder as a string to embed (the configured endpoint when
  `KB_EMBED_URL` is set), never to SQL as text and never to a log. Embedder calls from this route are
  capped per client (`retrieval.state.SemanticThrottle`, 30 per minute); over the cap the search is
  answered by keyword with `"mode": "keyword"`, never refused.
- Listing filters (`audience`, `owner`, `section`, `status`) only narrow a listing; they never
  grant or withhold access — an unmatched value returns an empty list, and every page stays
  reachable through `/pages/{path}` regardless of its audience. Filters run over the same
  redacted summaries the plain listing returns: a withheld page appears with its redacted
  metadata (path, redacted title/owner/tags, audience), never its body or snippet, and never as
  a search match or a facet value.
- `/me` reveals only role, `live_allowed` and whether Atlassian is configured (booleans).
- `/contract` returns the reviewed `kb.config.yaml` plus capability names and default ceilings — no secrets.
- Withholding applied uniformly through `service.withheld_paths`/`withholds`.
- Problem-report throttle buckets are pruned so memory is bounded by active clients.

## Residual risks and reviewer attention points

- Problem reports are free text from anonymous readers stored on disk; they are redacted but
  not otherwise validated — treat the queue as untrusted input when triaging.
- `request.client.host` behind a proxy that is not in `FORWARDED_ALLOW_IPS` collapses all
  clients into one throttle bucket (safe direction: stricter).
- `/files/{path}` serves YAML as `text/plain`; content is Internal tier like pages.

## Reviewer checklist

- [ ] `/files` path checks (allow-list, symlink, parent) intact.
- [ ] Every content route obtains its catalog from `state.catalog_for(lang)`.
- [ ] Problem report fields are redacted before write.

## Sign-off

Submit with `kb-librarian security submit api-pages`; the reviewer records the decision with
`kb-librarian security sign api-pages …`, which appends a row here and to `security/signoffs/api-pages.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
