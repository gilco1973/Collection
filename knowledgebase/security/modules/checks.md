# Security review sheet: Deterministic checks and the sensitive-content scanner

| | |
| --- | --- |
| Module id | `checks` |
| Kind | backend |
| Code | `kb_librarian/checks/` (`base.py`, `structure.py`, `frontmatter_check.py`, `freshness.py`, `links.py`, `catalogs.py`, `sensitive.py`) |
| Tests | `tests/test_checks.py` |
| Depends on | httpx (external link verification, opt-in only) |

## Purpose

The deterministic, no-LLM checks behind `kb-librarian check` (the CI gate), the offline audit
and the agent's `run_checks` tool. `sensitive.py` is the single sensitive-content policy: it
scans pages and YAML catalogs, decides what the API **withholds** from readers
(`withholds()`), and **redacts** anything about to be persisted (`redact()`).

## Entry points

`run_all_checks(catalog, config, today, offline)`, `check_sensitive`, `scan_lines`,
`withholds(lines, path)`, `redact(text)`, `scan_file`.

## Trust boundaries

Input is untrusted page content. Findings are reported to operators (reports) and, per page,
to readers (`/api/pages/{path}/findings`).

## Data handled

Page text in memory during a scan. **Findings never echo a matched value**: messages carry
only the category and line number (`possible <label> on line N`).

## Secrets

None held. The scanner's job is to find them in content: AWS/Anthropic/OpenAI/GitHub/Slack/
Google/Atlassian keys, JWTs, private-key blocks, connection strings with passwords, Azure
account keys, bearer/basic credentials, `password=`-style assignments, IBANs (mod-97), card
numbers (Luhn), e-mail addresses and IPv4 addresses.

## External calls

`links.py` verifies external URLs over HTTP **only** when `offline=False` (`--network`, or the
API's `network: true` from an operator). Default is offline; trusted hosts come from the contract.

## Mutations

None.

## Controls in place

- Severity policy: `critical` and `error` findings withhold a page/catalog from readers
  (`WITHHOLD_SEVERITIES`); the same function is used by pages, section listings, search and
  the raw catalog file endpoint.
- `<!-- kb-allow-sensitive -->` allow-lists a documented placeholder on one line, but a
  `critical` match is still reported unless the value itself looks like a placeholder.
- References to secrets (`${…}`, `os.environ`, `process.env`, `env(`, upper-case env names)
  and `@example.com` addresses are recognised as non-secrets to limit false positives.
- `redact()` applies the same patterns to every string leaf of a report before it is saved.

## Residual risks and reviewer attention points

- Pattern-based detection: novel token formats are missed until a pattern is added; review
  the list against the organisation's own credential formats.
- `warning`-level matches (e-mail, IPv4) do not withhold: a page with a personal e-mail is
  served, flagged for the owner.
- `redact()` on report text can only mask what the patterns match; tool inputs the agent
  supplied (e.g. a `reason`) are redacted too, but free text is never guaranteed clean.

## Reviewer checklist

- [ ] Every finding message construction uses label + line only (no `match.group` in messages).
- [ ] `WITHHOLD_SEVERITIES` unchanged or change justified.
- [ ] New credential formats the organisation uses are covered.

## Sign-off

Submit with `kb-librarian security submit checks`; the reviewer records the decision with
`kb-librarian security sign checks …`, which appends a row here and to `security/signoffs/checks.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
