# Contributing a component

The Collection holds components: self-contained pieces an engineer copies into their project and uses the same day.
This page is the contract. `python3 tools/shelf.py --check` enforces the parts that can be checked.

## The contract

1. **One directory, one component.** `components/<group>/<name>/` where the group is `python`, `typescript` or `skills`.
   The directory name is the component's name.
2. **A manifest.** `component.json` with these fields:

   | Field | Meaning |
   | --- | --- |
   | `name` | Same as the directory |
   | `version` | Semantic version of the component; bump it on any change a consumer would notice. Sign-offs bind to it |
   | `signoff` | `{owner, ai_security}`, each `null` while pending or `{by, date, version}`. A component is signed only when both name the current version; a version bump makes both stale. Record one with `python3 tools/shelf.py --sign <name> --role owner|ai-security --by "Name <email>"` and commit the manifest: the commit is the signature |
   | `kind` | `tool` (code you call), `integration` (a client for an external system), `skill` (a procedure for Claude Code or a person, as `SKILL.md`), `pattern` (a small reference implementation of a practice) |
   | `language` | `python`, `typescript`, `markdown`, `mixed` |
   | `summary` | One line, under 160 characters |
   | `status` | `ready` (tests green, used in a real project), `draft`, `deprecated` |
   | `source` | `{project, path, snapshot}`: where it was lifted from and when |
   | `owner` | Who answers questions |
   | `tags` | Tags from the knowledge base's taxonomy, for the shelf's tag index |
   | `spec` | `{document, sections, requirements, replacement_test}`: the platform design specification sections and PLT ids the component implements in interim form, and the test the platform must pass before it is retired (the specification's §14.3 rule) |
   | `requires` | Runtime dependencies beyond the language's standard library, if any |
   | `pairs_with` | Other components it is designed to plug into (names must exist) |
   | `test` | The command that proves it works, run from the component directory; empty only for markdown-only components |
   | `walkthrough` | `WALKTHROUGH.md`: numbered steps from the live example to the component running in the reader's own project, every command real |
   | `example` | `{path, run}`: the live example. Code components have a runnable one (`python3 example.py`, `npx tsx example.ts`) that `python3 tools/shelf.py --examples` runs; document skills have a filled `EXAMPLE.md` from a real product |
   | `vendored` | `[{path, from}]`: files copied verbatim from another component; the check refuses drift |

3. **A version, two sign-offs, a walkthrough and a live example.** Every component carries all four (the table above).
   The owner signs when the tests are green and the component has been used once for real; the AI security engineer
   signs after reading the README's rules and the walkthrough and running the example. Until both have signed at the
   current version, the hub lists the component as preview.
4. **A README that gets someone running in five minutes.** Use `components/_template/README.md`: what it is for, the
   five-minute start, what is inside, how to reuse it, the rules it enforces, where it came from, known limits.
5. **Self-contained.** Python components use the standard library only unless `requires` says otherwise. A component
   imports nothing outside its directory. When two components need the same file, one owns it and the other vendors
   it (`vendored`), so a reader sees exactly what they copy.
6. **Tests that run with one command.** Python: `python3 -m unittest discover -s tests -t .`. TypeScript:
   `npm ci && npx vitest run`. Skills: a checklist in `SKILL.md` under "Checks before you are done".
7. **Fakes ship with the real thing.** An integration comes with an in-memory fake behind the same method surface,
   so a consumer can test without an account (the way Meg's connectors do).
8. **No secrets, no real ids.** Placeholders are visibly placeholders. Credentials are names looked up at call time.
9. **Provenance and the specification.** `source` names the project and snapshot; `spec` names the platform design
   specification sections and requirement ids the component implements in interim form, and its replacement test; the README's "Where it came from" names what was changed
   during extraction. When the origin evolves, update the copy deliberately, never by re-vendoring blindly.

## Adding one

```
python3 tools/new_component.py python my-tool --kind tool --summary "What it does in one line"
# fill README.md, WALKTHROUGH.md, example.py, code, tests; set status to ready when tests are green and it has been used once for real
python3 tools/shelf.py --write && python3 tools/shelf.py --test --only python && python3 tools/shelf.py --examples --only python
# then the owner and the AI security engineer each: python3 tools/shelf.py --sign my-tool --role owner --by "Name <email>"
```

Open a pull request. The review checks the contract above, reads the README as a newcomer would, and runs the tests.

## Changing one

Keep the README's "Known limits" honest. Bump `version` on any change a consumer would notice; both sign-offs go
stale and are recorded again. A breaking change to a `ready` component is a major version, or a new directory with a
version suffix (`name-v2`) and a `deprecated` status on the old one, so consumers who copied it are not surprised.

## Style

Short files, docstrings that say why, one idea per module. Comments and docs in plain prose; no marketing. Names say
what a thing is, not what it hopes to be. Standard library first; a dependency has to earn its place in `requires`.
