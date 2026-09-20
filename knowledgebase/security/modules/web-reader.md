# Security review sheet: Reader pages

| | |
| --- | --- |
| Module id | `web-reader` |
| Kind | frontend |
| Code | `web/src/pages/Home.tsx`, `Browse.tsx`, `PageView.tsx`, `Search.tsx`, `components/PersonaPicker.tsx` |
| Tests | `web/src/test/pages.test.tsx`, `web/src/test/pageview.test.tsx`, `web/src/test/persona.test.tsx`, `web/src/test/selection.test.tsx` |
| Depends on | `web-api-client`, `web-markdown`, `web-chat-voice` (voice search, selection toolbar, chat bus), `profile` (persona, reading history) |

## Purpose

Home (hero search with voice, section cards, start-here links), Browse (sections and their
pages with stale counts), PageView (article, metadata, findings, problem-report form,
content-language fallback notice, withheld banner, the selection toolbar over the article and
the `?quiz=1` whole-page quiz request), Search (query + facets, voice input).

**Persona** (signed-in readers only): `PersonaPicker` lists the personas the server offers
(`GET /api/profile` → `personas`, the contract's audience values minus `everyone`) as chips and
saves the choice with `PUT /api/profile/persona` (or `null` for "no persona"). Home asks a reader
without a persona to choose one (dismissible until the home page is next opened — component
state only, nothing stored), shows a "For you" card of up to 8
pages whose `audience` includes the persona (`GET /api/pages?audience=`), and lists the sections
that contain such pages first with an "n for you" count. Browse splits a section into "For you"
(audience includes the persona or `everyone`) and a dimmed "Other audiences" group. The persona
is a **display preference**: it reorders and groups, never filters access — every page stays
listed, linked and openable. Anonymous readers and servers without SSO see none of this.

## Entry points

Routes `/`, `/kb`, `/kb/:section`, `/kb/page/*` (optionally `?quiz=1`), `/search?q=…`.

## Trust boundaries

Browser-side; all data from the API. The problem-report form is the only reader input that
leaves the browser (besides search/chat queries and, through the selection toolbar, the page
text a reader selects — see `web-chat-voice`). PageView mounts `SelectionToolbar` only for a
page that is not withheld and passes it the article element, the page path and title; a
`?quiz=1` link calls `openChat({mode: "quiz", context: {path, title}})` once the page is in and
then removes the flag from the URL (never for a withheld page).

## Data handled

Page content and metadata, findings for the page, the reader's problem report text, and — when
signed in — the reader's own profile (persona, viewed paths) from `/api/profile`.

## Secrets

None. A withheld page shows the withheld banner and no body; its metadata arrives redacted.

## External calls

None beyond the API client.

## Mutations

`POST /pages/{path}/reports` from the problem-report form (category from a fixed list,
message 10–1000 chars, HTML `minLength/maxLength/required` mirrored server-side).
`PUT /profile/persona` from the persona picker — a value from the server's own `personas` list
or `null`, validated again server-side; it changes only the signed-in reader's record.

## Controls in place

- Body rendered through `Markdown` (no HTML); the leading H1 duplicate is stripped textually.
- Catalog links limited to the contract's catalog files (`catalogFiles`), via `/api/files`.
- Search query comes from the URL (`?q=`) and is sent as a query parameter; results and
  snippets are rendered as text.
- Frontmatter errors and withheld states are rendered as alerts with fixed copy, not raw data.
- Persona chips are built from the API's `personas` list, never from free text; labels come from
  the console's translations (an id without a label is shown as the id itself). The persona
  query is sent as a URL parameter through `URLSearchParams`.
- The persona only reorders/groups listings that the reader could already see; "Other
  audiences" pages are dimmed, not removed.

## Residual risks and reviewer attention points

- The `translated` fallback notice makes clear when English is shown; there is no
  "machine-translated" marker on translated pages (policy question, see the `i18n` sheet).
- Voice input uses the browser's SpeechRecognition (see `web-chat-voice`): audio is processed
  by the browser vendor's service on supporting browsers.

## Reviewer checklist

- [ ] Every body/summary render goes through `Markdown`; no `innerHTML`.
- [ ] Problem-report constraints match the API's `ProblemReport` model.
- [ ] Persona UI renders only when `/api/me` has a `user`; no persona UI path hides a page.

## Sign-off

Submit with `kb-librarian security submit web-reader`; the reviewer records the decision with
`kb-librarian security sign web-reader …`, which appends a row here and to `security/signoffs/web-reader.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
