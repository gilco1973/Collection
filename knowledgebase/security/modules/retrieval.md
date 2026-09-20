# Security review sheet: Grounded retrieval

| | |
| --- | --- |
| Module id | `retrieval` |
| Kind | backend |
| Code | `kb_librarian/retrieval/` (`chunks.py`, `embedder.py`, `index.py`, `retriever.py`, `build.py`, `state.py`) |
| Tests | `tests/test_retrieval.py`, `tests/test_retrieval_api.py`, `tests/test_retrieval_chat.py` |
| Depends on | httpx, sqlite3 (standard library), `catalog`, `config` |

## Purpose

A question phrased unlike the page still finds it. Pages are split into heading-bounded chunks
(`chunk_document`: `#`/`##`/`###` sections, ≤ 3 000 characters, id `path#slug`, sha256 of the text),
embedded (`Embedder` protocol: `HashEmbedder` offline, `HttpEmbedder` over https) and stored in one
sqlite file, `.librarian/index/embeddings.sqlite` (`VectorIndex`: chunk id, path, heading, a
300-character excerpt, hash, model id, float32 vector). `Retriever.search(query, limit,
allowed_paths)` embeds the question and answers with the best chunk per page, cosine similarity in
pure Python. `rrf` fuses the keyword order and the semantic order (reciprocal rank fusion, k = 60).
Consumers: `GET /api/search?mode=` (`api-pages`, `api-core`), the chat's `semantic_search` tool
(`tools`, `chat`), `kb-librarian index --embeddings` and `doctor` (`cli`).

## Entry points

`build_index(root, config, embedder)` (the CLI and the nightly job), `retriever_for(root, settings)`
(the chat runner), `RetrieverCache.get` (`AppState.retriever()`), `semantic_hits(retriever, catalog,
query, withheld)` (the search route), `embedder_from_settings(settings)`, `index_path(root)`.

## Trust boundaries

- The **query text is untrusted** (a reader's search box or the model's tool input). It is embedded
  and compared; it never reaches SQL as text (parameters and temporary tables only) and is never
  logged.
- **Page text is Internal tier** and is what the index holds. Excerpts return to readers and to the
  model only for pages in the caller's `allowed_paths`.
- The embedding endpoint is a configured third party (or an on-premises service): it sees chunk
  text and query text and returns numbers. Its responses are validated for shape before use.

## Data handled

The index holds text from **every page, withheld ones included**: a 300-character excerpt per chunk
(most of a short page) plus the vectors, on the state volume under `.librarian/index/`. It is
Internal tier like the docs and rebuildable from them; nothing personal is in it. Withholding is
not decided at build time — a page's sensitive verdict can change with an audit or an edit — so it is
**enforced on every query**: `VectorIndex.query` joins the caller's `allowed_paths` inside the SQL
query, and every caller passes the same readable view the chat and the API already compute
(`_readable`, `withheld_paths`). A withheld page can never be a hit, and a change in `withheld_paths`
needs no rebuild. The build is idempotent (only chunks whose hash changed are embedded; removed pages
and renamed sections are pruned; a model change starts over).

## Secrets

`KB_EMBED_API_KEY` (`SecretStr` in settings), unwrapped once in `embedder_from_settings` and sent as
a bearer header by `HttpEmbedder`. Errors carry the failure type or HTTP status only (`from None`,
so the request with its headers is never chained); the key is never logged.

## External calls

`HttpEmbedder` only: POST `{"model", "input": [...]}` to `KB_EMBED_URL` (https, validated like the
IdP URLs), batches of 64, 30 s timeout. **Text leaves the host only through the configured
embedder; the hash embedder sends nothing** and is the default without `KB_EMBED_URL`.

## Mutations

`build_index` writes `.librarian/index/embeddings.sqlite` (state, not pages; not an action, not gated
by `KB_ALLOW_LIVE`, like reports and translations of state). Nothing in this module writes to `docs/`.
`semantic_search` is a read-only tool (not in `MUTATING_TOOLS`).

## Controls in place

- `allowed_paths` is a required positional argument of `Retriever.search` and `VectorIndex.query`;
  an empty set yields nothing (fail closed).
- Best chunk per page, positive similarity only, `limit` applied after the join.
- `HttpEmbedder` raises `EmbedError` on HTTP, JSON and shape failures, and a `sqlite3.Error` from the
  index (a rebuild holding the write lock, a damaged file) is handled the same way: the API degrades
  to keyword search and reports `"mode": "keyword"`; the chat tool returns an error result; the build
  fails; `doctor` reports FAIL. Readers never run the schema script (a write), so a search takes no
  write lock.
- `HttpEmbedder` opens one short-lived client per `embed` call (nothing to close, nothing leaks
  between chat turns) and its `model_id` is `model@endpoint-tag` (eight hex characters of the URL's
  digest, never the host name): a change of model **or** endpoint makes `doctor` warn and the next
  build start over. `KB_EMBED_MODEL` is required whenever `KB_EMBED_URL` is set (settings validator).
- `SemanticThrottle` (`state.py`): at most 30 embedder calls per client per minute from `/api/search`
  (any role, unauthenticated); beyond it the search is answered by keyword and says so. The chat tool
  is bounded by the chat's own per-client throttle and turn ceilings, and runs the embed in a worker
  thread so a slow endpoint never blocks the API's event loop.
- `HashEmbedder` uses an unkeyed blake2b of each token: deterministic across processes and hosts.
- One sqlite connection per operation: no shared state between threadpool workers.
- `doctor` warns when the index is missing or built with a different model than the configured embedder.

## Residual risks and reviewer attention points

- The index file is a second copy of page text (excerpts) outside `docs/`: it inherits the state
  volume's permissions, and anyone who can read the volume can read withheld excerpts. Treat
  `.librarian/index/` like `.librarian/snapshots/`.
- With a hosted embedder, every page's text (withheld ones included) is sent to that provider at build
  time, and every search-box query and `semantic_search` question is sent at query time. Choosing the provider — or keeping the hash embedder / an on-premises endpoint — is the
  bank's decision; the code makes no call without `KB_EMBED_URL`.
- The hash embedder is token overlap, not meaning: it proves the pipeline offline and finds
  shared words, not synonyms. Quality depends on the configured provider.
- Cosine similarity is computed in Python over every allowed chunk per query; a knowledge base far
  beyond a few thousand chunks would need the interface's vector-database implementation.
- Localised pages (`docs/i18n/`) are not indexed separately: a `lang` search fuses the localized
  keyword order with the English chunks' semantic order.

## Reviewer checklist

- [ ] Every caller of `query`/`search` passes the readable view (`_readable`, `withheld_paths`) as
      `allowed_paths`; no call site passes "all pages".
- [ ] `EmbedError` messages carry no key, no URL query, no text.
- [ ] `semantic_search` remains annotated read-only and out of `MUTATING_TOOLS`.
- [ ] `KB_EMBED_URL` stays https-only; `KB_EMBED_API_KEY` stays a `SecretStr`.

## Sign-off

Submit with `kb-librarian security submit retrieval`; the reviewer records the decision with
`kb-librarian security sign retrieval …`, which appends a row here and to `security/signoffs/retrieval.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
