# Security review sheet: Console shell

| | |
| --- | --- |
| Module id | `web-shell` |
| Kind | frontend |
| Code | `web/src/App.tsx`, `main.tsx`, `components/Layout.tsx`, `Identity.tsx`, `LanguageSwitcher.tsx`, `ContentLanguageSwitcher.tsx`, `Nudges.tsx`, `contentLanguage.ts`, `nudges.ts`, `nudgeStore.ts`, `usePageTitle.ts`, `format.ts`, `vite-env.d.ts`, `i18n/index.ts`, `web/index.html`, the build/tool configs (`vite.config.ts`, `tsconfig.json`, `tailwind.config.js`, `postcss.config.js`, `scripts/check-i18n.mjs`) and the frontend dependency set `package.json` + `package-lock.json` |
| Tests | `web/src/test/routes.test.tsx`, `web/src/test/components.test.tsx`, `web/src/test/nudges.test.ts`, `web/src/test/nudgesui.test.tsx` |
| Depends on | React 18, react-router 6, i18next, Vite, Tailwind |

## Purpose

Routing (a single `BrowserRouter` at the build's `BASE_URL`; there is no hash router and no demo
mode), the layout with primary
navigation (the **Audits** link, in both the desktop and the mobile bar, is rendered only when
`/api/me` reports the operator role; the mobile bar sizes its columns to the visible links),
role badge, sign-in/sign-out controls (`Identity`: a plain link to
`/api/auth/login?next=<current path>` and a POST sign-out; rendered only when `/api/me` says
`sso_configured`), UI-language switcher (10 locales, RTL for Hebrew), content-language switcher
(from the contract's `i18n.languages`), document title, and the chat widget mount.

The shell also mounts the **suggestion strip** (`Nudges.tsx`, between the header and `<main>`):
a proactive-librarian feature computed entirely in the browser. `nudges.ts` is a pure function
over the reader's `/api/profile` and the `/api/sections` list — both already served to the
reader — plus a clock and the dismissals, returning at most two suggestions (resume a page
left 3–30 days ago, quiz a page read twice, open a never-visited section, or start with the
first section). `nudgeStore.ts` keeps the reader's dismissals and the on/off preference.

## Entry points

`main.tsx` → `<App />`; routes `/`, `/kb`, `/kb/:section`, `/kb/page/*`, `/search`, `/audits`,
`/audits/new`, `/audits/:id`, `/audits/:id/actions/:actionId/rollback`, `/settings`.

## Trust boundaries

Runs in the reader's browser. Role is *displayed* from `/api/me`; every privileged action is
enforced server-side (`require_operator`) — the UI only hides/disables controls. Hiding the
Audits link from viewers is such a display choice: the `/audits` routes still mount for anyone
who types the URL, and they render read-only there because the API refuses operator calls.

## Data handled

UI language preference (i18next detector/localStorage), content language (in-memory store),
current route. No content of its own.

Suggestions: read-only use of the profile (page paths, titles, visit counts and timestamps,
quiz paths, per-section counts) and the section list. The strip subscribes to the same
`/api/profile` and `/api/sections` queries the home page uses — nothing else is requested, and
only while the reader is signed in *and* has suggestions enabled (anonymous readers, and readers
who switched them off, trigger no request at all). **Nothing new leaves the browser**: there is
no server-side behaviour tracking, no new endpoint and no new stored data on the server.
`localStorage` holds, under `kb.nudges.<fnv1a(sub)>` (a hash of the OpenID subject, so the key
does not spell out the identity), one JSON value per reader: `{enabled, dismissed}` where
`dismissed` maps a nudge id (`resume:<path>`, `quiz:<path>`, `section:<id>`, `welcome`) to the
ISO time it was dismissed — page *paths*, never page content. Dismissals lapse after 30 days;
"Delete my data" in Settings removes the whole entry (`clearNudgeState`); every read and write
is wrapped so a blocked or full storage degrades to session-only memory. The strip is
display-only: its links are ordinary client-side routes, and it never suggests the route the
reader is on.

## Secrets

None (the key lives in `web-api-client`/Settings).

## External calls

None; no third-party scripts, fonts or analytics. `index.html` loads only the Vite module.

## Mutations

None.

## Controls in place

- No `dangerouslySetInnerHTML` anywhere in the shell; translations are rendered as text
  (i18next `escapeValue` default is safe with React).
- Route params are passed to pages as strings; page components key on them to reset state.
- Skip link and focus management for accessibility; no inline scripts, so the server CSP
  (`default-src 'self'`) holds.
- Content language is applied only when the API confirms `translated`; RTL direction is set on
  the article only for translated RTL content.
- Suggestions are pure and deterministic (`computeNudges` takes its clock as an argument),
  render text only, and are gated on a signed-in `/api/me`; stored values are validated on read
  (`enabled` must be exactly `false` to disable, dismissal entries must be strings) and corrupt
  JSON falls back to the defaults.

## Residual risks and reviewer attention points

- Vite's dev server proxies `/api`; not relevant in production, but do not expose a dev build.
- The console is path-routed only, so whatever serves `web/dist` must answer every console route
  with `index.html` (the bundled server does); there is no static or demo build mode any more.

## Reviewer checklist

- [ ] No third-party script/style origins introduced (CSP would block them anyway).
- [ ] Role from `/api/me` is used for display only (nav link visibility, role badge).
- [ ] `App.tsx` mounts one `BrowserRouter`; no build-time switch selects another router.
- [ ] The suggestion strip still uses only the shared profile/sections queries, gated on
      sign-in and the preference, writes nothing but `kb.nudges.*` to `localStorage`, and
      "Delete my data" still clears that entry; its links stay client-side routes.

## Sign-off

Submit with `kb-librarian security submit web-shell`; the reviewer records the decision with
`kb-librarian security sign web-shell …`, which appends a row here and to `security/signoffs/web-shell.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
