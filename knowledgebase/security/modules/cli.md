# Security review sheet: Command line

| | |
| --- | --- |
| Module id | `cli` |
| Kind | backend |
| Code | `kb_librarian/cli.py`, `kb_librarian/cli_commands.py`, `kb_librarian/cli_doctor.py`, `kb_librarian/cli_doctor_probes.py`, `kb_librarian/cli_profiles.py` |
| Tests | `tests/test_cli.py`, `tests/test_doctor.py`, `tests/test_doctor_network.py`, `tests/test_profile_retention.py`, `tests/test_retrieval_cli.py` |
| Depends on | argparse; every other backend module |

## Purpose

`kb-librarian`: `check` (CI gate, nothing persisted), `audit [--offline|--live|--network|--atlassian]`,
`index [--write|--embeddings]`, `cancel`, `reports list|show`, `rollback --reason [--force]`, `atlassian sync`,
`translate sync`, `security …`, `profiles purge|stats`, `eval`, `insights [--json] [--window-days N]`, `insights prune`.

`doctor [--network] [--model]` (`cli_doctor.py`; the online probes and the check record in
`cli_doctor_probes.py`) prints one `OK|WARN|FAIL name — detail` line per
readiness check and exits 0 (all OK), 1 (a WARN) or 2 (any FAIL). Offline: Python 3.11, `kb.config.yaml`
loads, the catalog loads, `.librarian/` writable (create + delete a temp file), which model credential is
present, `KB_API_KEY` ≥ 16 characters when set, SSO all-or-none, `KB_SESSION_SECRET` ≥ 32 when set,
`KB_ALLOW_LIVE` / `KB_ATLASSIAN_ALLOW_WRITE` state (WARN when on), Atlassian all-or-none, retention
configured, embeddings (`embeddings_check`: OK with chunk/page counts and model id; WARN "no embedding
index" when `.librarian/index/embeddings.sqlite` is missing; WARN when the index's model id differs from
the configured embedder's — the configured embedder is constructed for its id only, never called). `--network` adds the IdP discovery document (when SSO is configured) and Atlassian
`/rest/api/3/myself` (when configured); `--model` adds one model turn.

## Entry points

`kb_librarian.cli:main(argv, out)` (Poetry script `kb-librarian`); `main` calls
`configure_logging(settings)` first, so the CLI logs like the API (`KB_LOG_LEVEL`, `KB_LOG_FORMAT`).

`index --embeddings` (`cmd_index`, `retrieval.build.build_index`) chunks every page — withheld ones
included — embeds the chunks whose text changed through the embedder the environment configures
(`KB_EMBED_URL`, else the offline hash embedder), prunes what is gone, and prints one line of counts
(`embeddings: N embedded, N unchanged, N removed, N pages`); the nightly workflow runs it before the
audit. It writes state under `.librarian/index/`, never a page, so it is not behind `KB_ALLOW_LIVE`.

`profiles purge [--older-than-days N] [--live]` and `profiles stats` (`kb_librarian/cli_profiles.py`,
`cmd_profiles`) operate on the reader records in `.librarian/users/`; the deployment's scheduled job
runs `profiles purge --live` with `KB_PROFILE_RETENTION_DAYS` set.

`eval [--items N] [--budget USD] [--json] [--lang xx] [--golden PATH]` (`kb_librarian/cli_evals.py`,
`cmd_eval`, reviewed under the `evals` module) runs the golden set through the read-only chat path and
exits 0 / 1 (a threshold missed) / 2 (invalid golden file, no items, or every item errored).

`insights [--json] [--window-days N]` and `insights prune` (`kb_librarian/cli_insights.py`,
`cmd_insights`; reviewed under `insights`): the first regenerates `.librarian/insights/latest.json`
from reader records, problem reports and chat telemetry (counts and rates under k-anonymity,
withheld pages excluded) and prints the top pages by problem reports, by quiz fail rate, and the
unanswered counts — paths and numbers only; the second drops chat telemetry lines older than
`KB_CHAT_LOG_DAYS` and prints `removed=N`. Neither touches a page or a reader record.

## Trust boundaries

Runs as the invoking user with the invoking user's environment. The root is `--root` or the
nearest `kb.config.yaml` upward from cwd. Used by CI workflows and by operators on a host.

## Data handled

Reports and findings printed to stdout; `reports show` prints a saved (redacted) report.

## Secrets

None read directly; `LibrarianSettings()` reads `KB_*` from the environment. `doctor` looks at
whether `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` are set and reports presence and a length
class (`short` < 16, `medium` < 48, `long`) for those, `KB_API_KEY`, `KB_SESSION_SECRET` — never a value.

## External calls

Via the modules it drives: the model API (audit, translate), Atlassian (with `--atlassian` /
`atlassian sync`), HTTP link checks (`--network`). `doctor --network`: `OidcProvider.configuration()`
(discovery GET) and `AtlassianClient.get("/rest/api/3/myself")`, both through the existing clients with
an injectable transport; `doctor --model`: one `query()` turn with no tools, `max_turns=1`,
`max_budget_usd=0.05`, `effort="low"`.

## Mutations

Delegated: page writes only through the action log during live audits/translations, `index --write`,
`rollback`. `mode_notice` prints "forced DRY RUN" whenever `--live` was asked without
`KB_ALLOW_LIVE=true`.

`profiles purge --live` deletes reader records (`.librarian/users/<hash>.json`) inactive for longer
than the cut-off. It is dry-run by default, and its `--live` is **not** behind `KB_ALLOW_LIVE`: that
gate is about page edits by the model's write tools, and a purge never touches a page nor goes
through `ActionLog`. Without `--older-than-days` or `KB_PROFILE_RETENTION_DAYS` it exits 2 and
removes nothing; a record holding a revocation epoch is kept until `KB_SESSION_TTL_HOURS` have
passed since its last activity; its output is counts only (`removed=N failed=M`, never a subject,
a hashed stem or a path — a filesystem error is reported by exception type alone).

## Controls in place

- Exit codes: 0 ok, 1 blocking findings, 2 failed, 3 cancelled — CI reads them.
- `--capabilities` validated against `CAPABILITY_PROMPTS`; `--reason` required for rollback.
- `--force` on rollback is explicit and recorded on the action.
- `doctor` never prints a secret value or an exception message (only the exception type — messages
  may name paths); the `--model` probe offers no tools (`tools=[]`, `allowed_tools=[]`,
  `DISALLOWED_BUILTINS`, `setting_sources=[]`) and is never run in CI without a credential. Its
  credential check also looks for the bundled CLI's own store (`~/.claude/.credentials.json`,
  presence only) and says that `--model` is the authoritative probe (a proxy may supply a credential).
- A rejected setting (`LibrarianSettings` validation) is one `FAIL settings — KB_<VAR>: <reason>` line
  per variable and exit 2 for every command (`config.settings_errors`; the value is never printed),
  never a traceback; `deploy/serve.py` does the same on stderr. An empty variable reads as unset
  (`env_ignore_empty`), so the shipped ConfigMap and Secret template start the process as they are.
- `KB_ROOT` (the deployment's convention) locates the project for every command when `--root` is
  not given; `--root` wins, then `KB_ROOT`, then the nearest `kb.config.yaml`.

## Residual risks and reviewer attention points

- Whoever can run the CLI with `KB_ALLOW_LIVE=true` in the environment can mutate pages
  (subject to file permissions). The weekly live workflow is gated by a repository variable and
  opens a PR rather than pushing to the default branch.
- No interactive confirmation for live runs; the environment gate is the confirmation.
- Whoever can run `profiles purge --live` on the host can delete reader records: the CLI runs with
  the invoking user's file permissions and the explicit flag is the only confirmation.

## Reviewer checklist

- [ ] No page-writing subcommand bypasses `resolve_dry_run` (`profiles purge` writes no page; its
      only gate is the explicit `--live`).
- [ ] Every new subcommand that writes a page goes through `ActionLog`.
- [ ] `profiles purge` removes nothing without `--live`, refuses without a retention period, and
      prints no subject or hashed stem.
- [ ] `doctor` output contains no secret value (presence and length class only); `--model` keeps `max_turns=1` and the $0.05 cap.

## Sign-off

Submit with `kb-librarian security submit cli`; the reviewer records the decision with
`kb-librarian security sign cli …`, which appends a row here and to `security/signoffs/cli.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
