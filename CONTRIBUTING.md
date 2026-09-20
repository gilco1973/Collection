# Contributing a component

The Collection holds components: self-contained pieces an engineer copies into their project and uses the same day.
This page is the contract. `python3 tools/catalog.py --check` enforces the parts that can be checked.

## The contract

1. **One directory, one component.** `components/<group>/<name>/` where the group is `python`, `typescript` or `skills`.
   The directory name is the component's name.
2. **A manifest.** `component.json` with these fields:

   | Field | Meaning |
   | --- | --- |
   | `name` | Same as the directory |
   | `kind` | `tool` (code you call), `integration` (a client for an external system), `skill` (a procedure for Claude Code or a person, as `SKILL.md`), `pattern` (a small reference implementation of a practice) |
   | `language` | `python`, `typescript`, `markdown`, `mixed` |
   | `summary` | One line, under 160 characters |
   | `status` | `ready` (tests green, used in a real project), `draft`, `deprecated` |
   | `source` | `{project, path, snapshot}`: where it was lifted from and when |
   | `owner` | Who answers questions |
   | `tags` | Free words for the catalog's tag index |
   | `requires` | Runtime dependencies beyond the language's standard library, if any |
   | `pairs_with` | Other components it is designed to plug into (names must exist) |
   | `test` | The command that proves it works, run from the component directory; empty only for markdown-only components |
   | `vendored` | `[{path, from}]`: files copied verbatim from another component; the check refuses drift |

3. **A README that gets someone running in five minutes.** Use `components/_template/README.md`: what it is for, the
   five-minute start, what is inside, how to reuse it, the rules it enforces, where it came from, known limits.
4. **Self-contained.** Python components use the standard library only unless `requires` says otherwise. A component
   imports nothing outside its directory. When two components need the same file, one owns it and the other vendors
   it (`vendored`), so a reader sees exactly what they copy.
5. **Tests that run with one command.** Python: `python3 -m unittest discover -s tests -t .`. TypeScript:
   `npm ci && npx vitest run`. Skills: a checklist in `SKILL.md` under "Checks before you are done".
6. **Fakes ship with the real thing.** An integration comes with an in-memory fake behind the same method surface,
   so a consumer can test without an account (the way Meg's connectors do).
7. **No secrets, no real ids.** Placeholders are visibly placeholders. Credentials are names looked up at call time.
8. **Provenance.** `source` names the project and snapshot; the README's "Where it came from" names what was changed
   during extraction. When the origin evolves, update the copy deliberately, never by re-vendoring blindly.

## Adding one

```
python3 tools/new_component.py python my-tool --kind tool --summary "What it does in one line"
# fill README.md, code, tests; set status to ready when tests are green and it has been used once for real
python3 tools/catalog.py --write && python3 tools/catalog.py --test --only python
```

Open a pull request. The review checks the contract above, reads the README as a newcomer would, and runs the tests.

## Changing one

Keep the README's "Known limits" honest. A breaking change to a `ready` component is a new directory with a version
suffix (`name-v2`) and a `deprecated` status on the old one, so consumers who copied it are not surprised.

## Style

Short files, docstrings that say why, one idea per module. Comments and docs in plain prose; no marketing. Names say
what a thing is, not what it hopes to be. Standard library first; a dependency has to earn its place in `requires`.
