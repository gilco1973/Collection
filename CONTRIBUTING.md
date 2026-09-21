# Contributing a component

The Collection holds AI components: self-contained pieces an engineer copies into a project and uses the same day,
and procedures anyone can follow. This page is the contract. `python3 tools/shelf.py --check` enforces the parts
that can be checked; the hub's sign-off queue and onboarding tracker show the rest.

## The categories

Every component is one of six categories. The category says who it is for and what it must contain beyond the
common contract below; the shelf, the hub's Discover tabs and the knowledge base group by it.

| Category | What it is | Who uses it | What it must contain |
| --- | --- | --- | --- |
| `agent` | An AI agent | Operators, from the hub or a channel; engineers deploy one | A **template** (`TEMPLATE.md`: role, stages, tools by tier, what it never does), the **tools** it may call and the **harness** it runs inside, all three declared in the manifest's `agent` |
| `harness` | The loop an agent runs inside | Engineers building an agent | Fixed hooks, action tiers, budgets, kill switches, a chained record |
| `tool` | Code with one clear surface | Engineers; an agent calls one through its harness | The code and a test that proves it |
| `integration` | A client for an external system | Engineers connecting a system | The client and an in-memory fake behind the same methods |
| `pattern` | A small reference implementation of a practice | Engineers adopting the practice | The implementation and the practice page it belongs to |
| `skill` | A procedure | Anyone: a person or a coding assistant follows it, nothing to run | `SKILL.md` with the procedure and its checks, a template and a filled example |

An agent is the composite: `agent.template` is a file in the component whose first ```` ```json ```` block names
`name`, `role`, `ladder`, `stages`, `tools` (each with target, op, tier, contract, permission, args and result
shape), `never` and `budget`; `agent.tools` names existing tool, integration or pattern components; `agent.harness`
names an existing harness component. The code builds the harness's signed catalog from the template, so the agent
can call exactly what the template lists. `components/agents/incident-first-read-agent` is the reference.

## The contract

1. **One directory, one component.** `components/<group>/<name>/` where the group is `agents`, `python`,
   `typescript` or `skills`. The directory name is the component's name.
2. **A manifest.** `component.json` with these fields:

   | Field | Meaning |
   | --- | --- |
   | `name` | Same as the directory |
   | `version` | Semantic version of the component; bump it on any change a consumer would notice. Sign-offs bind to it |
   | `category` | One of the six categories above |
   | `agent` | Agents only: `{template, tools, harness}` as described above |
   | `signoff` | `{owner, ai_security}`, each `null` while pending or `{by, date, version}`. A component is signed only when both name the current version; a version bump makes both stale. Recorded through the hub's sign-off queue or `python3 tools/shelf.py --sign`; never written by hand |
   | `used_in` | Projects the component has been used in for real. The owner signs only after one is recorded (the sign-off form asks for it) |
   | `language` | `python`, `typescript`, `markdown`, `mixed` |
   | `summary` | One line, under 160 characters |
   | `status` | `ready` (tests green), `draft`, `deprecated` |
   | `source` | `{project, path, snapshot}`: where it was lifted from and when |
   | `owner` | Who answers questions, as their handle (the local part of their address); the hub lets that person sign as owner |
   | `tags` | Tags from the knowledge base's taxonomy, for the shelf's tag index |
   | `spec` | `{document, sections, requirements, replacement_test}`: the platform design specification sections and PLT ids the component implements in interim form, and the test the platform must pass before it is retired (the specification's §14.3 rule) |
   | `requires` | Runtime dependencies beyond the language's standard library, if any |
   | `pairs_with` | Other components it is designed to plug into (names must exist) |
   | `test` | The command that proves it works, run from the component directory; empty only for markdown-only components |
   | `walkthrough` | `WALKTHROUGH.md`: numbered steps from the live example to the component running in the reader's own project, every command real |
   | `example` | `{path, run}`: the live example. Code components have a runnable one (`python3 example.py`, `npx tsx example.ts`) that `python3 tools/shelf.py --examples` runs; document skills have a filled `EXAMPLE.md` from a real product |
   | `vendored` | `[{path, from}]`: files copied verbatim from another component; the check refuses drift |

3. **A version, two sign-offs, a walkthrough and a live example.** Every component carries all four.
4. **A README that gets someone running in five minutes.** Use `components/_template/README.md`: what it is for, the
   five-minute start, what is inside, how to reuse it, the rules it enforces, where it came from, known limits.
5. **Self-contained.** Python components use the standard library only unless `requires` says otherwise. A component
   imports nothing outside its directory. When two components need the same file, one owns it and the other vendors
   it (`vendored`), so a reader sees exactly what they copy. An agent vendors its harness and its tools.
6. **Tests that run with one command.** Python: `python3 -m unittest discover -s tests -t .`. TypeScript:
   `npm ci && npx vitest run`. Skills: a checklist in `SKILL.md` under "Checks before finishing". An agent has one
   test per line of its template's `never`.
7. **Fakes ship with the real thing.** An integration comes with an in-memory fake behind the same method surface,
   so a consumer can test without an account.
8. **No secrets, no real ids.** Placeholders are visibly placeholders. Credentials are names looked up at call time.
9. **Provenance and the specification.** `source` names the project and snapshot; `spec` names the platform design
   specification sections and requirement ids the component implements in interim form, and its replacement test;
   the README's "Where it came from" names what was changed during extraction. When the origin evolves, update the
   copy deliberately, never by re-vendoring blindly.

## Onboarding a component: the six stages

A component's way to the shelf is read from its manifest, never guessed; `python3 tools/shelf.py --list` prints
the stage and the hub's onboarding tracker (Build → Onboarding) shows it with what has to happen next.

| Stage | What proves it |
| --- | --- |
| 1 scaffolded | `python3 tools/new_component.py` made the directory: version 0.1.0, both sign-offs pending, a spec entry, a tag from the taxonomy |
| 2 built | README, walkthrough, live example and tests filled and green; `status` set to `ready` |
| 3 used once for real | `used_in` names a project; the owner records it on the sign-off form or with `--used-in` |
| 4 owner signed | The owner signed at this version after running the tests and the example |
| 5 AI security signed | An AI security engineer signed at this version after reading the rules and the walkthrough and running the example |
| 6 on the shelf | Both sign-offs name the current version: Discover lists it as GA and the knowledge base page says so. A version bump returns it to stage 3 |

`deprecated` is past the shelf: the directory stays until consumers have moved to the replacement.

## Signing off

Two people sign every component at every version: the **owner**, by name (the manifest's `owner` is their handle
and the hub matches it to the signed-in person), and an **AI security engineer**, by role (`ai.security` on the
platform principal, granted by the security team lead). Each attests on the form that the tests are green, the
live example ran, the walkthrough was read end to end, and the rules and known limits were read; the server refuses
a form with a box unticked, so the API cannot be used to skip it. The owner also names the project of the first
real use.

The manifest is the record and the commit is the signature:

```
# on the hub: Build → Sign-offs, or the Sign-off card on the component's listing; then download the queue
python3 tools/shelf.py --apply-signoffs shelf-signoffs.json   # re-runs the tests, writes signoff.<role> at the current version
python3 tools/shelf.py --write
git commit -am "Sign off <component> <version>"
# or from a terminal, one at a time
python3 tools/shelf.py --sign <name> --role owner --by "Name <email>" --used-in <project>
python3 tools/shelf.py --sign <name> --role ai-security --by "Name <email>"
```

A sign-off recorded at another version is stale and skipped; the person read a different component.

## Adding one

```
python3 tools/new_component.py python my-tool --category tool --summary "What it does in one line"
python3 tools/new_component.py agents my-agent --category agent --summary "What it does in one line"
# fill README.md, WALKTHROUGH.md, the example, code, tests (an agent: TEMPLATE.md first, then one test per `never` line)
python3 tools/shelf.py --write && python3 tools/shelf.py --test --only python && python3 tools/shelf.py --examples --only python
# set status to ready when the tests are green; use it once for real; then both sign-offs as above
```

Open a pull request. The review checks the contract above, reads the README as a newcomer would, and runs the tests.

## Changing one

Keep the README's "Known limits" honest. Bump `version` on any change a consumer would notice; both sign-offs go
stale and are recorded again. A breaking change to a `ready` component is a major version, or a new directory with a
version suffix (`name-v2`) and a `deprecated` status on the old one, so consumers who copied it are not surprised.

## Style

Short files, docstrings that say why, one idea per module. Comments and docs in plain prose; no marketing. Names say
what a thing is, not what it hopes to be. Standard library first; a dependency has to earn its place in `requires`.
