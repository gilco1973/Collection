# Security review sheet: Security review tooling

| | |
| --- | --- |
| Module id | `security-review` |
| Kind | tooling |
| Code | `kb_librarian/security/` (`registry.py`, `ledger.py`, `cli_security.py`), `security/registry.yaml` |
| Tests | `tests/test_security_review.py`, `tests/test_security_cli.py` (+ `tests/security_fixtures.py`) |
| Depends on | PyYAML, pydantic, git (optional, for the commit id) |

## Purpose

`kb-librarian security status|submit|sign|verify`: computes each module's content version,
prints submission packets, records sign-offs bound to a version, and detects drift.

## Entry points

The CLI subcommands; `load_registry`, `compute_version`, `record_signoff`, `module_status`.

## Trust boundaries

Runs locally as the invoking user on the repository checkout. The reviewer's name, signature
and notes are typed by whoever runs `sign`; the tool does **not** authenticate the reviewer
or verify a cryptographic signature — that is the review process's job (a detached signature
over the submission packet, kept with the ticket, is the recommended practice).

## Data handled

File paths and SHA-256 digests of project files; reviewer name/signature/date/decision/notes
written to `security/signoffs/<module>.json` and the sheet table. All of it is committed to git.

## Secrets

None. Nothing in the packet is secret; file *contents* are hashed, not printed.

## External calls

`git rev-parse --short=12 HEAD` (subprocess, 5 s timeout, failure tolerated → `None`).

## Mutations

`sign` appends to the ledger JSON and inserts a row in the sheet's sign-off table. Nothing else writes.

## Controls in place

- Version = SHA-256 over the module's `paths` entry, the sheet prose above `## Sign-off`, and
  the sorted `path\0content\0` of matched files — so narrowing a module's scope or rewriting
  what its sheet claims invalidates the sign-off, while appending a sign-off row does not.
  Symlinked files and directories, anything resolving outside the project, `__pycache__` and
  `node_modules` are excluded; patterns must be relative and free of `..`; a module matching
  no files is an error (a typo in a glob cannot produce an "approved" empty module).
- The ledger stores the full 64-hex digest (12 chars are shown for display only).
- A sign-off is stored only for the *current* version; the sheet row is prepared before the
  ledger is written, so the two files cannot diverge.
- `verify` exits non-zero on `unsigned`, `changed`, `rejected` and — unless
  `--allow-conditional` — `conditional`, for use as a release gate.
- Pydantic validation of registry and ledger entries; module ids restricted to `[a-z0-9-]`;
  a test asserts every source, config, dependency, deploy and CI file is in some module.

## Residual risks and reviewer attention points

- Anyone with write access to the repository can add a sign-off row (`sign` authenticates
  nobody); protect `security/` with code owners so only the security team can merge changes to
  `signoffs/`, and have reviewers put a detached signature over the packet (its id in the
  `signature` column) so a row can be verified out of band.
- Table rows are appended by text manipulation of the sheet, scoped to the `## Sign-off`
  section; a sheet without that heading makes `sign` fail loudly rather than write elsewhere.
- `verify` is not in CI by default (nothing is signed yet); wire it into the release branch
  once the first round of sign-offs exists.

## Reviewer checklist

- [ ] `security/` is covered by a CODEOWNERS rule naming the security team.
- [ ] `verify` is wired into the release branch's CI (optional, recommended).

## Sign-off

Submit with `kb-librarian security submit security-review`; the reviewer records the decision with
`kb-librarian security sign security-review …`, which appends a row here and to `security/signoffs/security-review.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
