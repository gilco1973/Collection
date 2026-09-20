# Security review sheet: Atlassian clients and Confluence mirror

| | |
| --- | --- |
| Module id | `atlassian` |
| Kind | backend |
| Code | `kb_librarian/atlassian/` (`client.py`, `confluence.py`, `jira.py`, `markdown.py`, `sync.py`) |
| Tests | `tests/test_atlassian.py` (httpx `MockTransport`; no network) |
| Depends on | httpx |

## Purpose

Read and gated-write access to Confluence Cloud and Jira Cloud, plus the section mirror
(`kb-librarian atlassian sync`) that publishes active pages of configured sections to a space.

## Entry points

`AtlassianClient.from_settings(settings, dry_run=)`, `ConfluenceClient.search/get_page/find_page/
create_page/update_page/publish`, `JiraClient.create_issue`, `sync_sections`, `markdown_to_storage`.

## Trust boundaries

- Outbound to the organisation's Atlassian tenant with a **service account's API token** (basic
  auth). Responses are untrusted data (returned to the model via the data envelope).
- Writes need **both** `KB_ATLASSIAN_ALLOW_WRITE=true` **and** a live (non dry-run) run:
  `writes_enabled = allow_write and not dry_run`; `post`/`put` call `ensure_write_allowed`
  before sending anything, and `publish` refuses before even looking up the page.

## Data handled

Page bodies (Internal tier) published to Confluence with a footer naming the source path; Jira
issue summaries/descriptions written by the model (capped upstream). Search results and page
bodies read from Confluence.

## Secrets

`KB_ATLASSIAN_EMAIL` + `KB_ATLASSIAN_API_TOKEN` (`SecretStr`), passed straight into the httpx
client's auth; never logged or returned.

## External calls

HTTPS to `KB_ATLASSIAN_BASE_URL` (`/wiki/rest/api/...`, Jira REST). Timeout 20 s. Test
injection through `transport=`.

## Mutations

Confluence page create/update, Jira issue create — external systems, **not rollback-able**;
recorded as `LibrarianAction`s without file state via `record_external_action`.

## Controls in place

- Hard write gate in the base client (`AtlassianWriteRefused`), independent of the agent gate.
- Read tools only search the configured space; CQL input is sanitised (`cql_text`).
- Mirror skips non-active pages and reports `would-publish` when writes are gated.
- `markdown_to_storage` HTML-escapes every text run (`html.escape`, quotes included) before
  the small inline substitutions, so page text cannot inject storage-format markup or close a
  link's `href` attribute; fenced code goes into a CDATA body.

## Residual risks and reviewer attention points

- The service account's permissions define the blast radius: restrict it to the one space and
  project (nightly CI uses a read-only account by policy — verify).
- Storage-format conversion is hand-written and covers a small subset; a `]]>` sequence inside
  a fenced code block would end the CDATA section early (renders wrongly; not markup injection
  since Confluence sanitises storage format on write).
- No retry/backoff; `raise_for_status` surfaces failures to the tool as errors.

## Reviewer checklist

- [ ] Every write path calls `ensure_write_allowed` before any request.
- [ ] Credentials appear nowhere in logs, reports or tool results.
- [ ] `markdown_to_storage` escapes `<`, `>`, `&` in text.

## Sign-off

Submit with `kb-librarian security submit atlassian`; the reviewer records the decision with
`kb-librarian security sign atlassian …`, which appends a row here and to `security/signoffs/atlassian.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
