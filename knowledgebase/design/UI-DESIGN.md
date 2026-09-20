# KnowledgeBase Console — UI design specification (v1)

Scope: a web console that (a) reads the organisational AI knowledge base (markdown pages with
frontmatter) and (b) operates the librarian agent. Stack: React 18 + Vite + TypeScript, Tailwind
utility classes only, i18next (10 languages, Hebrew RTL), WCAG 2.1 AA, 360px to desktop. Backend:
a small FastAPI JSON API over `kb_librarian` (contract in section 8). Organisation-neutral.

Non-negotiables carried through every screen:

- **Dry run is unmistakable.** Every audit surface carries a persistent `RunModeBadge`; dry-run
  proposals are never called "applied". Live surfaces get an amber top border and label.
- **Live mutations need a typed reason.** Run-live and rollback are gated by `ConfirmWithReason`
  (reason min 10 chars, typed confirmation token). Server-side `KB_ALLOW_LIVE` still wins; the UI
  shows "Forced to dry run by server policy" when the API reports it.
- **No raw secrets.** The API redacts; the UI renders only `before_state`/`after_state` fields the
  API returns and never fetches page source for pages with a `sensitive` finding (shows a notice).

## 1. Personas and jobs-to-be-done

| Persona | Who | Top jobs |
| --- | --- | --- |
| Reader | New joiner, engineer, data scientist at a regulated bank | Find the right page fast; know if it is current and who owns it; follow onboarding order; report a problem |
| Operator | Platform engineer on librarian on-call | Start dry-run/live audit with chosen capabilities and budget; watch progress; cancel; read findings by severity; roll back an action; prove what the agent did (tool trail, cost) |
| Owner | Section/page owner (e.g. `model-risk-management`) | See my pages past review window; see manual-review items raised for my paths; see proposed/applied changes to my pages; confirm the contract that governs my section |

Readers are the majority; operator and owner views are behind a role claim (`viewer`, `operator`,
`owner:<team>`) returned by `GET /api/me`. Read-only for everyone by default.

## 2. Information architecture

```
/                      Home (reader dashboard; operators see health strip)
/kb                    Browse: section list
/kb/:section           Section page list
/kb/page/*path         Page view + metadata panel + report a problem
/search?q=             Search
/audits                Audits list (+ "Run audit" button, operator only)
/audits/new            Run audit form (operator only)
/audits/:id            Audit detail; tabs via ?tab=findings|actions|review|tools|summary
/audits/:id/actions/:actionId/rollback   Rollback confirmation (route so it is linkable/back-able)
/settings              Contract view (kb.config.yaml, read-only) + language + theme
```

Navigation: top bar (logo text "Knowledge base", search box, language switcher, theme toggle,
user role chip) + primary nav: Home · Browse · Search · Audits · Settings. Desktop: left rail
(w-56) with sections listed under Browse. Mobile (<768px): bottom tab bar with 5 items; left rail
becomes a slide-over opened from a hamburger. All nav is `<nav aria-label>` with `aria-current`.

## 3. Screens

Shared states: `loading` uses skeleton blocks (`animate-pulse`, `aria-busy`); `empty` uses
`EmptyState` with one action; `error` uses `ErrorState` with retry and request id. Every screen
sets `document.title` via i18n. Wireframes: D = desktop (>=1024px), M = mobile (360px).

### 3.1 Home `/`

```
D ┌────────────────────────────────────────────────────────────┐  M ┌──────────────┐
  │ [rail] │ Welcome · Start here → onboarding/day-one          │    │ Welcome      │
  │ Home   │ ┌ Onboarding path ─────────────────────────────┐   │    │ Start here → │
  │ Browse │ │ Day one → First week → 30/60/90 → Checklist  │   │    │ Onboarding   │
  │ Search │ └──────────────────────────────────────────────┘   │    │  path (list) │
  │ Audits │ Sections (10 cards: title, owner, page count)      │    │ Sections     │
  │ Sett.  │ [operator] Health: last audit · findings by sev    │    │  (stacked)   │
  └────────────────────────────────────────────────────────────┘    │ [tabbar]     │
```

Components: `OnboardingPath`, `SectionCard` grid, `HealthStrip` (operators/owners only).
Owners additionally see "Your pages needing review (n)" linking to Search with
`owner=<team>&stale=true`. API: `GET /api/sections`, `GET /api/audits?limit=1`,
`GET /api/pages?owner=<team>&stale=true&limit=5` (owner only).

### 3.2 Browse `/kb`, `/kb/:section`

Section list: table (D) / cards (M) with title, owner, `review_every_days`, page count, stale
count. Section page list: `PageTable` rows = title, status (`StatusBadge`), reviewed date +
"n days ago", owner, audience chips. Sort by title/reviewed; filter by status and audience via
`FilterBar` (querystring-backed). Empty: "No pages in this section yet". API:
`GET /api/sections`, `GET /api/sections/:id/pages`.

### 3.3 Page view `/kb/page/*path`

```
D ┌──────────┬──────────────────────────────────┬─────────────────┐ M ┌──────────────┐
  │ rail     │ Breadcrumb: Browse › Section › … │ Metadata        │   │ Breadcrumb   │
  │ (TOC on  │ # Title                          │ owner  status   │   │ # Title      │
  │  page)   │ rendered markdown (headings get  │ reviewed  next  │   │ [Details ▾]  │
  │          │ ids; code blocks; tables scroll) │ tags · audience │   │ markdown     │
  │          │                                  │ [Report problem]│   │ [Report      │
  │          │                                  │ Open findings n │   │  problem] FAB│
  └──────────┴──────────────────────────────────┴─────────────────┘   └──────────────┘
```

Components: `Breadcrumb`, `MarkdownView`, `MetadataPanel` (collapsible `<details>` on mobile,
default closed), `ReportProblemDialog`. Deprecated pages get a top `Banner tone="warning"`
"Deprecated — see …". Stale pages (reviewed + section window < today) get `Banner tone="info"`.
If the page has an open `sensitive` finding, body is replaced by `Banner tone="critical"`
"Content withheld pending review" — the API already returns no body; the UI must not retry
another endpoint. Report a problem: dialog with category (outdated / wrong / broken link /
sensitive content / other), free text (max 1000), sends `POST /api/pages/*path/reports`; success
toast "Sent to <owner>". Internal links resolve to `/kb/page/...`; external links get
`rel="noopener"` and an "external" icon + sr-only text. API: `GET /api/pages/*path`,
`GET /api/pages/*path/findings`.

### 3.4 Search `/search?q=`

Input with 300ms debounce, results list (title, section, snippet with `<mark>`, status, owner),
facets (section, status, audience, owner, stale) as checkbox groups; on mobile facets in a
slide-over. `aria-live="polite"` announces "n results". Empty: "No pages match" + tip to browse.
API: `GET /api/search?q=&section=&status=&audience=&owner=&stale=&page=`.

### 3.5 Audits list `/audits`

```
D ┌───────────────────────────────────────────────────────────────┐ M ┌───────────────┐
  │ Audits                          [Run audit] (operator)        │   │ Audits [Run]  │
  │ Filter: mode ○all ○dry ○live  status ▾  type ▾                 │   │ filters ▾     │
  │ ┌ id ─────┬ mode ──────┬ type ─┬ status ──┬ crit/err/warn/info┬ cost ┬ date ┐ │   │ ┌ card ─────┐ │
  │ │ audit-5f│ DRY RUN    │ agent │ completed│ 0/2/7/3            │ $0.41│ …    │ │   │ │ DRY RUN   │ │
  │ │ audit-6d│ ●LIVE      │ agent │ in prog. │ live progress bar  │      │      │ │   │ │ completed │ │
  └───────────────────────────────────────────────────────────────┘   └───────────────┘
```

Rows are links; `RunModeBadge` in every row, live rows also `border-s-4 border-amber-500`. In-progress
rows poll `GET /api/audits/:id` every 3s (or SSE, see 8). API: `GET /api/audits?mode=&status=&type=&page=`.

### 3.6 Run audit form `/audits/new` (operator)

```
D/M ┌──────────────────────────────────────────────────────────────┐
    │ Run an audit                                                 │
    │ Mode   (●) Dry run — proposes, changes nothing   [default]   │
    │        ( ) Live — may edit frontmatter/index  ⚠ amber panel  │
    │        Server: live runs ENABLED / DISABLED (from /api/me)   │
    │ Type   (●) Agent (model)  ( ) Offline (checks only)          │
    │ Capabilities ☑structure ☑frontmatter ☑freshness ☑links       │
    │              ☑sensitive ☐atlassian (disabled if unconfigured)│
    │ Max turns [40]  Budget USD [2.00]  ☐ Verify links over HTTP  │
    │                                   [Cancel] [Start dry run]   │
    └──────────────────────────────────────────────────────────────┘
```

The primary button label changes with mode: "Start dry run" (neutral) vs "Start LIVE audit"
(amber, `aria-describedby` warning). Choosing Live opens `ConfirmWithReason` (title "Start a live
audit", typed token `LIVE`, reason field). If `/api/me.live_allowed` is false, the Live radio is
disabled with hint "Disabled by server policy (KB_ALLOW_LIVE)". Validation inline, on blur.
On success navigate to `/audits/:id?tab=summary`. API: `GET /api/me`, `GET /api/contract`
(capability list, defaults), `POST /api/audits`.

### 3.7 Audit detail `/audits/:id`

```
D ┌────────────────────────────────────────────────────────────────────────┐
  │ ← Audits   audit-5f6053d239e7   [DRY RUN]  agent · completed · 2m 14s   │
  │ ▓▓▓▓▓▓▓▓▓░░ turns 27/40 · $0.41/$2.00     [Cancel audit] (in_progress)  │
  │ Tabs: Findings (12) | Actions (4) | Review queue (2) | Tool trail (31) | Summary │
  │ ┌ tab panel ───────────────────────────────────────────────────────┐   │
  │ │ Findings: filter sev ▾ check ▾ path search  · sorted crit→info    │   │
  │ │ ┌ [CRITICAL] sensitive  docs/x.md:12   message   fix hint   auto ┐ │   │
  │ └──────────────────────────────────────────────────────────────────┘   │
  └────────────────────────────────────────────────────────────────────────┘
M: header stacks; tabs become a horizontally scrollable `role="tablist"`; rows become cards.
```

Header: `AuditHeader` with `RunModeBadge`, status, `ProgressBar` (turns and cost vs budget),
Cancel button (operator, only `in_progress`; confirmation dialog, no reason needed) →
`POST /api/audits/:id/cancel`. While `in_progress`, poll every 3s; stop on terminal status.
Failed audits show `error` in `ErrorState` inside Summary.

- **Findings tab.** `FindingsTable` grouped by severity with `SeverityBadge`; columns check,
  path (link to page view), line, message, fix_hint, auto-fixable. Filters in querystring.
  Sensitive findings show `details` keys only (e.g. `pattern: iban`), never a value.
- **Actions tab.** `ActionCard` per `LibrarianAction`: type, path, description, timestamp, and
  `BeforeAfterDiff` (`before_state` → `after_state`, side-by-side on D, stacked on M).
  Dry-run actions are titled "Proposed (dry run)" and have no rollback button. Live actions
  show `[Roll back]` unless `rolled_back` (then a "Rolled back on <date>: <reason>" note).
  If the API returns `before_state: null` with `redacted: true`, render "Redacted".
- **Review queue tab.** `ReviewItem` list: path, reason, severity, raised_by, at; owner column
  derived from section; filter "mine" for owners. Actions: copy link, open page. No resolve
  action in v1 (see 9).
- **Tool trail tab.** `ToolCallRow` timeline: time, tool, ok/denied icon, summary; expand to
  show `input` as a JSON tree (already redacted server-side). Denied calls get
  `text-red-700` + "Denied by gate".
- **Summary tab.** Counts by severity, fixes applied vs proposed, manual review count, tool
  calls, turns, cost, duration, capabilities, `ai_summary` rendered as markdown (sanitised;
  no raw HTML). Download buttons: JSON, Markdown (`GET /api/audits/:id/export?format=`).

API: `GET /api/audits/:id` (full report), `POST /api/audits/:id/cancel`.

### 3.8 Rollback confirmation `/audits/:id/actions/:actionId/rollback` (operator)

```
┌ Roll back action act-1a2b ─────────────────────────────────────┐
│ ⚠ This edits the knowledge base now (LIVE).                    │
│ Page docs/paved-roads/rag-service.md · set_frontmatter_field   │
│ Current → will become:  [after_state] → [before_state]         │
│ Reason (required, min 10 chars) [______________________]       │
│ Type ROLLBACK to confirm        [________]                      │
│                                  [Cancel]  [Roll back now]     │
└────────────────────────────────────────────────────────────────┘
```

`ConfirmWithReason` with `token="ROLLBACK"`. Button disabled until both valid. On 409
(already rolled back / page changed since) show `ErrorState` with the server message. On success
return to Actions tab with toast and the card updated. API: `GET /api/audits/:id` (action),
`POST /api/audits/:id/actions/:actionId/rollback { reason }`.

### 3.9 Settings / Contract `/settings`

Read-only view of `kb.config.yaml`: sections table (id, path, title, owner, review window),
frontmatter rules (required fields, status values, audience values), taxonomy tag chips, trusted
hosts, Atlassian mirror sections (keys only, never credentials). Also: language select (10
languages, applies `dir` on `<html>`), theme (system/light/dark, stored in localStorage), server
policy chips: live allowed yes/no, Atlassian configured yes/no. API: `GET /api/contract`,
`GET /api/me`.

## 4. Component inventory (each file <200 lines)

```ts
// layout
AppShell({ children })                          // top bar + rail/bottom tabs + <main id="main">
TopBar({ role: Role })                          // search shortcut, LanguageSwitcher, ThemeToggle
SideRail({ sections: SectionSummary[] })        // desktop only
BottomTabs()                                    // mobile only
SkipLink()                                      // "Skip to content" → #main
// primitives
Button({ variant: 'primary'|'secondary'|'danger'|'live', size?, disabled?, loading?, onClick, children })
Badge({ tone: Tone, children })                 // Tone = 'neutral'|'info'|'warning'|'error'|'critical'|'success'|'live'|'dry'
RunModeBadge({ dryRun: boolean, size?: 'sm'|'lg' })   // "DRY RUN" / "LIVE"; never omitted on audit UIs
SeverityBadge({ severity: 'critical'|'error'|'warning'|'info' })
StatusBadge({ status: 'draft'|'active'|'deprecated'|'unknown' })
AuditStatusBadge({ status: 'in_progress'|'completed'|'failed'|'cancelled' })
Banner({ tone: Tone, title: string, children?, dismissible?: boolean })
Dialog({ open, onClose, titleId, children })    // focus trap, Esc closes, returns focus
ConfirmWithReason({ open, title, warning, token: string, minReasonLength?: number,
                    onConfirm: (reason: string) => Promise<void>, onCancel })
Tabs({ tabs: { id, label, count? }[], active, onChange })   // roving tabindex, arrows
Table<T>({ columns: Column<T>[], rows: T[], rowKey, caption, sort?, onSort? })  // cards on M
FilterBar({ filters: FilterDef[], values, onChange })       // querystring-backed
Pagination({ page, pageSize, total, onChange })
ProgressBar({ value, max, label })              // role="progressbar"
Skeleton({ lines?: number })  EmptyState({ title, hint?, action? })  ErrorState({ error, onRetry? })
Toast()/useToast()                              // aria-live="polite" region in AppShell
// kb
SectionCard({ section: SectionSummary })       PageTable({ pages: PageSummary[] })
Breadcrumb({ items: { label, to? }[] })         MarkdownView({ markdown: string, basePath: string })
MetadataPanel({ meta: PageMeta, stale: boolean, findingsCount: number })
ReportProblemDialog({ path, owner, open, onClose })
OnboardingPath({ steps: PageSummary[] })        SearchBox({ value, onChange, onSubmit })
SearchResults({ results: SearchHit[] })         Facets({ facets: FacetGroup[], values, onChange })
// audits
HealthStrip({ latest: AuditSummary | null })    AuditTable({ audits: AuditSummary[] })
AuditHeader({ audit: AuditReport, onCancel? })  RunAuditForm({ me: Me, contract: Contract, onSubmit })
FindingsTable({ findings: Finding[] })          ActionCard({ action: LibrarianAction, canRollback: boolean })
BeforeAfterDiff({ before: string | null, after: string | null, redacted: boolean })
ReviewItem({ item: ManualReviewItem, owner?: string })
ToolCallRow({ call: ToolCall })                 AuditSummaryPanel({ summary: AuditSummaryCounts, report })
ContractView({ contract: Contract })            LanguageSwitcher()  ThemeToggle()
```

Hooks: `useApi<T>(path, { poll?: ms })`, `useQueryState` (querystring filters), `useMe()`, `useDir()`.
Pages under `src/pages/`, components under `src/components/{layout,ui,kb,audits}/`.

## 5. Design tokens (Tailwind)

| Token | Light | Dark |
| --- | --- | --- |
| Page bg / surface / border | `bg-slate-50` / `bg-white` / `border-slate-200` | `bg-slate-950` / `bg-slate-900` / `border-slate-800` |
| Text primary / muted | `text-slate-900` / `text-slate-600` | `text-slate-100` / `text-slate-400` |
| Primary action | `bg-blue-700 hover:bg-blue-800 text-white` | `bg-blue-500 hover:bg-blue-400 text-slate-950` |
| Focus ring (all) | `focus-visible:outline-none focus-visible:ring-2 ring-offset-2 ring-blue-600` | `ring-blue-400 ring-offset-slate-900` |
| critical | `bg-red-100 text-red-900 border-red-300` | `bg-red-950 text-red-200 border-red-700` |
| error | `bg-orange-100 text-orange-900 border-orange-300` | `bg-orange-950 text-orange-200 border-orange-700` |
| warning | `bg-amber-100 text-amber-900 border-amber-300` | `bg-amber-950 text-amber-200 border-amber-700` |
| info | `bg-sky-100 text-sky-900 border-sky-300` | `bg-sky-950 text-sky-200 border-sky-700` |
| status active / draft / deprecated / unknown | `emerald-` / `slate-` / `zinc-` (strike icon) / `violet-` (same 100/900/300 pattern) | 950/200/700 pattern |
| audit in_progress / completed / failed / cancelled | `blue-` / `emerald-` / `red-` / `slate-` | as above |
| DRY RUN badge | `bg-slate-200 text-slate-900 border border-dashed border-slate-500` + outlined beaker icon | `bg-slate-800 text-slate-100 border-slate-400` |
| LIVE badge / live button | `bg-amber-500 text-slate-950 font-bold` + filled bolt icon; surfaces `border-t-4 border-amber-500` | `bg-amber-400 text-slate-950` |

Severity and mode are never colour-only: each badge has an icon and a text label; all pairs meet
4.5:1. Dark mode: `class` strategy on `<html>`, default from `prefers-color-scheme`. Type `text-base`
body, `text-sm` (14px) minimum. Gutter `px-4` mobile, `px-8` desktop; touch targets `min-h-11`.

## 6. i18n keys (English source), RTL notes

Namespace per screen, file `public/locales/<lng>/console.json`; all 10 languages ship every key.

```
common: appName "Knowledge base"; nav.home "Home"; nav.browse "Browse"; nav.search "Search";
  nav.audits "Audits"; nav.settings "Settings"; skipToContent "Skip to content"; loading "Loading…";
  retry "Retry"; cancel "Cancel"; close "Close"; back "Back"; requestId "Request id {{id}}";
  external "opens external site"; daysAgo "{{count}} day ago" / _other "{{count}} days ago"
mode: dry "DRY RUN"; live "LIVE"; dryHint "Proposes changes, edits nothing";
  liveHint "May edit frontmatter and the index"; forced "Forced to dry run by server policy"
severity: critical "Critical"; error "Error"; warning "Warning"; info "Info"
status: draft "Draft"; active "Active"; deprecated "Deprecated"; unknown "Unknown"
auditStatus: in_progress "In progress"; completed "Completed"; failed "Failed"; cancelled "Cancelled"
home: title "Welcome"; startHere "Start here"; path "Onboarding path"; sections "Sections";
  health "Knowledge-base health"; lastAudit "Last audit"; yourStale "Your pages needing review ({{count}})"
browse: title "Browse"; pages "{{count}} pages"; reviewEvery "Reviewed every {{days}} days";
  empty "No pages in this section yet"; owner "Owner"; reviewed "Reviewed"; audience "Audience"
page: details "Details"; nextReview "Next review"; tags "Tags"; report "Report a problem";
  reportSent "Sent to {{owner}}"; category.outdated "Outdated"; category.wrong "Incorrect";
  category.link "Broken link"; category.sensitive "Sensitive content"; category.other "Other";
  describe "Describe the problem"; deprecated "This page is deprecated"; stale "Past its review window";
  withheld "Content withheld pending review"; openFindings "{{count}} open findings"
search: placeholder "Search pages"; results "{{count}} results"; empty "No pages match";
  facets "Filters"; stale "Needs review"
audits: title "Audits"; run "Run audit"; empty "No audits yet — run a dry run"; mode "Mode";
  type "Type"; type.agent "Agent"; type.offline "Offline"; findings "Findings"; cost "Cost"; date "Date"
runForm: title "Run an audit"; startDry "Start dry run"; startLive "Start LIVE audit";
  liveDisabled "Disabled by server policy"; capabilities "Capabilities"; maxTurns "Max turns";
  budget "Budget (USD)"; network "Verify external links over HTTP"; confirmLive "Start a live audit";
  liveWarning "This run may edit pages. Every change is recorded and can be rolled back."
audit: back "Audits"; cancel "Cancel audit"; cancelConfirm "Stop this audit after its next step?";
  turns "Turns {{n}} of {{max}}"; spend "Spend {{usd}} of {{max}}"; duration "Duration";
  tabs.findings "Findings"; tabs.actions "Actions"; tabs.review "Review queue"; tabs.tools "Tool trail";
  tabs.summary "Summary"; proposed "Proposed (dry run)"; applied "Applied"; rollback "Roll back";
  rolledBack "Rolled back on {{date}}: {{reason}}"; redacted "Redacted"; denied "Denied by gate";
  fixHint "Suggested fix"; autoFixable "Auto-fixable"; raisedBy "Raised by"; mine "Only my pages";
  download.json "Download JSON"; download.md "Download Markdown"; aiSummary "Agent summary"
rollback: title "Roll back action {{id}}"; warning "This edits the knowledge base now (LIVE).";
  becomes "Current → will become"; reason "Reason"; reasonHint "Required, at least {{min}} characters";
  typeToken "Type {{token}} to confirm"; confirm "Roll back now"; conflict "This action can no longer be rolled back"
settings: title "Settings"; contract "Contract"; language "Language"; theme "Theme"; theme.system "System";
  theme.light "Light"; theme.dark "Dark"; policy.live "Live runs"; policy.atlassian "Atlassian";
  enabled "Enabled"; disabled "Disabled"; trustedHosts "Trusted hosts"; taxonomy "Tags taxonomy"
errors: generic "Something went wrong"; forbidden "You do not have permission for this";
  notFound "Not found"; validation "Check the highlighted fields"
```

RTL: set `dir` on `<html>` from the language (he → rtl). Logical utilities only (`ps-`, `pe-`, `ms-`,
`me-`, `text-start`, `border-s-4`, `rounded-s`), never `pl-/ml-/left-`. Mirror directional icons with
`rtl:rotate-180`; breadcrumb separators swap via `rtl:`. Code blocks, paths, ids and diffs stay
`dir="ltr"` inside an RTL page. Numbers/dates via `Intl` for the locale; plurals via `_one/_other`.

## 7. Accessibility checklist (WCAG 2.1 AA)

All screens: skip link; one `<h1>`; landmarks (`header`, `nav`, `main`, `aside`); visible focus
ring; 4.5:1 text contrast in both themes; 200% zoom without horizontal scroll at 360px;
`prefers-reduced-motion` disables pulse/transition; no information by colour alone; every icon
button has `aria-label`; route change moves focus to `<h1>` and announces title.

| Screen | Specific checks |
| --- | --- |
| Home | Section cards are links with the card title as accessible name; health counts have sr-only severity words |
| Browse / Section | `<table>` with `<caption>`, `scope="col"`, sortable headers use `aria-sort`; card fallback keeps same reading order |
| Page view | Markdown headings preserve hierarchy; TOC is `<nav aria-label="On this page">`; metadata `<details>`/`<summary>`; external link sr-only suffix; report dialog traps focus, first field focused, errors via `aria-describedby` |
| Search | Combobox pattern not used; plain input + `aria-live` result count; facets are fieldset/legend with checkboxes |
| Audits list | Mode badge has text; in-progress rows announce updates with `aria-live="polite"` at most once per 10s |
| Run form | Radios in `fieldset`; live warning linked via `aria-describedby`; disabled live option explains why in text; submit disabled state announced |
| Audit detail | Tabs follow WAI-ARIA tabs pattern (arrow keys, Home/End, `aria-controls`); `role="progressbar"` with `aria-valuenow`; cancel dialog focus-managed; timeline is `<ol>` |
| Rollback | Dialog `role="alertdialog"`; token input has `autocomplete="off"`, `spellcheck=false`; error summary focused on failure |
| Settings | Language `<select>` labelled, changes `lang`+`dir`; theme radios; contract tables as above |

## 8. Proposed API contract (FastAPI, JSON, `/api`)

All responses `Content-Type: application/json`; errors `{ "error": { "code", "message", "request_id" } }`.
Auth: session cookie or bearer; role claims resolved server-side. Redaction happens in the API:
page bodies of pages with open `sensitive` findings are omitted; `before_state`/`after_state`
and `tool_calls[].input` pass through the existing redaction and carry `redacted: true` when
anything was removed. Dates are ISO-8601 UTC.

| Method, path | Purpose / shape |
| --- | --- |
| `GET /me` | `{ role: "viewer"\|"operator"\|"owner", teams: string[], live_allowed: bool, atlassian_configured: bool }` |
| `GET /contract` | `kb.config.yaml` as JSON + `{ capabilities: string[], defaults: { max_turns, max_budget_usd } }` |
| `GET /sections` | `[{ id, path, title, owner, review_every_days, page_count, stale_count }]` |
| `GET /sections/{id}/pages` | `{ items: PageSummary[] }`; `PageSummary = { path, title, owner, status, reviewed, tags, audience, stale }` |
| `GET /pages/{path}` | `{ meta: PageSummary & { next_review }, body_markdown: string \| null, withheld: bool, section: { id, title } }` |
| `GET /pages/{path}/findings` | `{ items: Finding[] }` (latest completed audit) |
| `POST /pages/{path}/reports` | body `{ category, message }` → `201 { id, owner }` (persists to `.librarian/problems/`) |
| `GET /pages` | `?owner=&stale=&limit=` → `{ items: PageSummary[] }` |
| `GET /search` | `?q=&section=&status=&audience=&owner=&stale=&page=&page_size=` → `{ items: [{ ...PageSummary, snippet }], total, facets: { section: [{value,count}], status, audience, owner } }` |
| `GET /audits` | `?mode=dry\|live&status=&type=&page=` → `{ items: AuditSummary[], total }` = `AuditReport.summary()` + `audit_date`, `completed_at`, `capabilities` |
| `POST /audits` | body `{ type: "agent"\|"offline", dry_run: bool, capabilities: string[], max_turns?, max_budget_usd?, network?: bool, atlassian?: bool, reason?: string }` → `202 { audit_id, dry_run, forced_dry_run: bool }`; `reason` required when `dry_run=false`; `403` if role is not operator |
| `GET /audits/{id}` | full `AuditReport` (redacted) + `summary` + `max_turns`, `max_budget_usd` |
| `GET /audits/{id}/events` | SSE, optional: `status`, `tool_call`, `finding`, `done`; UI falls back to 3s polling when unavailable |
| `POST /audits/{id}/cancel` | → `202 { status: "cancelling" }`; `409` if not in progress |
| `POST /audits/{id}/actions/{action_id}/rollback` | body `{ reason }` (min 10) → `200 { action: LibrarianAction }`; `409` if dry-run, already rolled back, or server live-disabled; `403` for non-operators |
| `GET /audits/{id}/export?format=json\|md` | file download of the persisted report |

The API wraps existing functions: `run_offline_audit`, `run_agent_audit` (background task with
`task_manager` for cancel), `cmd_reports` storage, `rollback_action`, `catalog` for pages/search.
Server-side `LibrarianSettings.resolve_dry_run` remains authoritative; the UI only displays the result.

## 9. Out of scope for v1 (and why)

- **Editing pages in the console.** Ownership and `reviewed` bumps stay in git review; an in-browser
  editor would bypass the CI gate and the "librarian never rewrites prose" rule.
- **Resolving / assigning review-queue items.** Needs a persisted queue state and identity model
  the package does not have; v1 links to the page and its owner instead.
- **Live streaming of agent reasoning.** Only tool calls are audited; showing model text would
  invite trust in unverified content. Tool trail + summary suffice.
- **Atlassian sync and Jira creation from the UI.** Mutating Atlassian writes have a separate
  server gate; expose read-only "mirrored to Confluence" chips only.
- **Scheduling, comments/ratings, PWA, notifications, SSO admin.** CI already schedules audits; feedback
  goes through "Report a problem"; none serve the reader/operator jobs above.
