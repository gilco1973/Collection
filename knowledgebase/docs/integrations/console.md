---
title: The console for readers
owner: ai-platform-engineering
status: active
reviewed: 2026-09-18
tags: [agents, paved-road]
audience: [engineer, everyone]
---
# The console for readers

What a reader gets from the console beyond browsing and search, how each feature is
switched on, and what it stores. Operator features (audits, rollback) are described in
[Platform integration](platform.md); the librarian's safety model in
[The librarian agent](../governance/librarian-agent.md).

## Sign-in with the organisation's identity provider

Readers sign in over OpenID Connect (authorization code with PKCE; `kb_librarian/auth/`).
The server needs `KB_OIDC_ISSUER`, `KB_OIDC_CLIENT_ID`, `KB_OIDC_REDIRECT_URI`
(`https://<console>/api/auth/callback`), optionally `KB_OIDC_CLIENT_SECRET`, and
`KB_SESSION_SECRET` (at least 32 characters); the issuer and redirect URI must be https.
Without all of them the console shows no sign-in at all. The ID token is verified against
the provider's published keys (issuer, audience, expiry, nonce) and the reader receives an
HttpOnly, SameSite=Lax, Secure, HMAC-signed session cookie (`KB_SESSION_TTL_HOURS`, default
12) — there is no server-side session table, and cookie-authenticated requests are refused
when they come from another site. `/api/me` reports `user`, `sso_configured`, `role` and
`operator_via` (`key`, `group` or null).

**Operator groups.** Identity can grant the operator role: `KB_OIDC_OPERATOR_GROUPS` lists
(comma-separated) the group names that do, and `KB_OIDC_GROUPS_CLAIM` (default `groups`)
names the ID-token claim that carries the person's groups. The provider must be configured
to put that claim in the ID token; a claim that is absent, or not a list of strings, grants
nothing. The decision is made once, at sign-in, and stored in the session, so a group change
at the provider takes effect at the person's next sign-in. `KB_API_KEY` stays the break-glass
path. Audits record who asked: `key` for the bearer key, a pseudonym (`user:` + 16 hex digits
of a keyed hash of the identity) for a group operator — never a subject, name or e-mail, and not
something a reader can compute from a guessed name; the server log links it to the person. Operator actions from a session are same-origin only,
like every other cookie-authenticated change.

**Sign out everywhere.** Settings offers "Sign out everywhere" next to "Sign out": the
server moves the reader's session epoch (kept in their profile record) and every cookie
issued before it is refused from then on, whichever browser holds it; a fresh sign-in works
immediately. Plain "Sign out" only drops this browser's cookie. "Delete my data" removes the
reading record but keeps the epoch, so sessions you signed out everywhere stay signed out.

## Reading progress

A signed-in reader's progress is kept server-side (`kb_librarian/profile/`, one JSON file
per reader named by a hash of the issuer and subject): the pages they opened, the persona
they chose and their quiz tallies — paths, timestamps and counts, never page text and never
the answers they chose. The console records a view when a page is opened, marks pages
"Read", shows per-section progress in Browse and "Continue reading" on the home page, and
offers "Delete my data" in Settings. Withheld pages are never recorded. Endpoints:
`GET /api/profile`, `PUT /api/profile/persona`, `POST /api/profile/views`,
`POST /api/profile/quizzes`, `DELETE /api/profile` — all 401 without a session.

## Personas

A signed-in reader can pick the persona closest to their role (the contract's
`audience_values` minus `everyone`: new hire, engineer, data scientist, product, risk,
leadership) from the home page or Settings. The console then puts "For you" first: a card of
pages written for that persona (`GET /api/pages?audience=<persona>`), sections holding such
pages ahead of the rest with an "n for you" count, and in Browse a "For you" group above a
dimmed "Other audiences" group. It is a display preference only — every page stays listed
and openable, and "No persona" restores the plain order. Anonymous readers see no persona
UI, and the Audits menu entry appears only for operators (the server enforces the role
regardless).

## Ask the librarian

A floating chat widget is on every page (text or voice, via the browser's speech
recognition). It answers by searching and reading pages through the same read-only tools
audits use — no write tool is even offered — and lists the pages it actually read as source
links. Each answer is one short, capped agent turn (`POST /api/chat`, `kb_librarian/chat/`),
not part of an audit: no report is saved, and its turn and budget ceilings
(`KB_CHAT_MAX_TURNS`, `KB_CHAT_MAX_BUDGET_USD`) are separate from the audit ceilings. It is
open to any role, like search, and rate-limited per client. Search itself is hybrid once an embedding
index exists (`kb-librarian index --embeddings`; `GET /api/search?mode=keyword|semantic|hybrid`,
hybrid by default): keyword matches and meaning-based matches are fused, and the librarian gets the
same index as a `semantic_search` tool for open questions — withheld pages are excluded from both.

## Explain, elaborate, quiz me

Select some text on a page and a small toolbar offers **Explain** (the passage in plain
language, grounded in the page), **Elaborate** (background, related pages, pitfalls) and
**Quiz me** (three multiple-choice questions about the passage — or the whole page when a
page is opened with `?quiz=1`). Each is one chat turn with a `mode` and the page as
`context`. The quiz comes back as strict JSON, is validated server-side and graded in the
browser, with the model's one-line reason per answer and an "Explain what I got wrong"
follow-up. A signed-in reader's tally (path, score, total) is saved to their profile.

## Suggestions (the proactive librarian)

From the profile and section list it already fetches, the console works out up to two
suggestions in the browser — pick up a page left 3–30 days ago, test yourself on a page read
more than once, open a section never visited, or start with the first section — and shows
them in a dismissible strip under the header (`web/src/nudges.ts`,
`web/src/components/Nudges.tsx`). Nothing is sent or stored server-side for this: dismissals
(which lapse after 30 days; dismissing one page promotes the next) and the "Suggestions"
on/off switch in Settings live in the browser's local storage, keyed per reader, and
"Delete my data" clears that too.

## What is stored where

| Data | Where | Who can see it |
| --- | --- | --- |
| Session (subject, issuer, name, e-mail, operator flag, session epoch) | Signed cookie in the browser | The reader's browser and the API |
| Views, persona, quiz tallies | `.librarian/users/` on the server | Only that reader, through `/api/profile` |
| Operator key | Browser storage, by explicit choice | That browser |
| Suggestion dismissals and on/off switch | Browser storage, keyed per reader | That browser |
| Chat questions, selections, answers | Nowhere — one request, then discarded | — |
| Chat telemetry (time, mode, language, persona, cited page paths, refused, cost, duration — never the text) | `.librarian/chat-log.jsonl` on the server, pruned after `KB_CHAT_LOG_DAYS` | Operators, as counts in the Insights tab |

A reader's record is kept for as long as the reader is active: every recorded view, persona
change or quiz tally refreshes its `updated_at`. The deployment's scheduled purge
(`kb-librarian profiles purge --live`, run from its cron job) removes a record once it has
been untouched for `KB_PROFILE_RETENTION_DAYS` days; with the variable unset nothing is
purged automatically. "Delete my data" stays immediate and never waits for the schedule.
Operators see only a count and the oldest/newest activity (`kb-librarian profiles stats`),
never who.
