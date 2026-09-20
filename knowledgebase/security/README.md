# Security review package

Everything the AI security team needs to review this project module by module and sign each
one off with a name, a signature, a date and the exact version reviewed.

## What is reviewed

`registry.yaml` lists every reviewable module or component: backend packages, frontend
components/pages, deployment and CI, and the review tooling itself. Each has one **review
sheet** under `modules/` that states, from the code as it is:

- purpose and entry points;
- trust boundaries (who can call it, with what role, from where);
- data handled (classification, what is persisted, what reaches the model);
- secrets it touches and where they come from;
- external calls (network, subprocess, filesystem outside the project);
- mutations (what it can change, and the gate that decides);
- controls in place, residual risks, and a reviewer checklist;
- the **sign-off table**.

## Versions

A module's version is a SHA-256 over three things: its registry entry's `paths` (the declared
scope), the prose of its review sheet above the sign-off table (what was claimed), and every
file the globs match (`path\0content\0` in sorted order). It changes exactly when the reviewed
code, its scope or its sheet changes; appending a sign-off row, tests and other modules do not
move it. The ledger stores the full digest (`status` shows the first 12 characters). The git
commit is recorded next to it for orientation, but the content hash is what drift detection
compares — a sign-off follows the code across rebases and branches.

## Workflow

```bash
poetry run kb-librarian security status                  # every module: version, state, last reviewer
poetry run kb-librarian security submit api-core          # the submission packet (sheet + file manifest)
poetry run kb-librarian security submit api-core > /tmp/api-core.md   # ...to attach to a ticket or e-mail
poetry run kb-librarian security sign api-core \
    --reviewer "A. Reviewer (AI Security)" \
    --signature "sig:ssh-ed25519:…" \
    --decision approved --notes "Reviewed against SR-2026-xx"
poetry run kb-librarian security verify                  # exit 1 if any module is unsigned/changed/rejected
```

`submit` prints a self-contained packet: identity, version, commit, sign-off state, the
per-file SHA-256 manifest, the full sheet, and the exact `sign` command. Send it to the
reviewer however your process requires; nothing leaves the machine on its own.

`sign` records the decision **for the current version only** in two places that are written
together: the machine-readable ledger `signoffs/<module>.json` and a new row in the sheet's
sign-off table. Both are committed with the code, so the review history is in git.

- **Signature**: free text the reviewer owns — a typed name plus employee id, a ticket
  reference, or (recommended) the id/fingerprint of a detached signature they produced over
  the submission packet (`ssh-keygen -Y sign` / `gpg --detach-sign`). The tool stores it
  verbatim and never interprets it.
- **Decision**: `approved`, `conditional` (approved with notes that must be actioned) or
  `rejected`.

## States

| State | Meaning |
| --- | --- |
| `unsigned` | no sign-off on record |
| `approved` / `conditional` / `rejected` | the last sign-off is for the current version |
| `changed` | the code changed since the last sign-off; re-submit |

`verify` fails on `unsigned`, `changed`, `rejected` and `conditional` (pass
`--allow-conditional` to accept modules whose conditions are being tracked elsewhere), so it
can gate a release branch.

## Adding a module

When code is added that is not covered by an existing module's globs, add a registry entry
and a sheet (copy the structure of a neighbouring sheet) in the same commit. Keep sheets
factual: they describe what the code does, not what it should do; risks go in the residual
risks section, not in the controls section.
