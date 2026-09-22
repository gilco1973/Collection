# Walkthrough: onboarding a solution with the AI Playground

Two people use the playground on the way to the shelf: the engineer who built the solution, and the AI security
engineer who signs it. Each path below ends where the collection's own process takes over (`CONTRIBUTING.md`).
Every command runs from the `playground/` directory.

## The engineer

1. **Describe the solution.** Copy an example that matches how it is reached:

   ```sh
   python3 -m aiplayground init my-targets
   ```

   Edit one file: `name`, `environment` (never production), how to reach it (`url` and a `preset`, a `command`,
   or `path` and `callable`), and `capabilities` for what it claims (`cites-sources`, `masks-pii`). A credential is
   `${env:NAME}`; export `NAME` in the shell that runs the playground. A host outside loopback goes in `allow_hosts`.

2. **Check the file** (nothing is sent):

   ```sh
   python3 -m aiplayground check my-targets/openai-chat.json
   ```

3. **Try it by hand.** Look at what the solution really returns before automating:

   ```sh
   python3 -m aiplayground ask my-targets/openai-chat.json "What do we do when the inbound file is late?"
   python3 -m aiplayground tools my-targets/mcp-stdio.json          # a tool server
   ```

4. **Write your cases.** A suite says what the solution is for; start from `examples/runbook-suite.json`. A case is
   a `prompt` (or a `tool` with `arguments`) and an `expect`: `contains`, `contains_any`, `not_contains`, `regex`,
   `cites`, `refuses`, `calls_tool`, `calls_no_tool`, `max_latency_ms`, `json`, `error`. Use `repeat` and
   `pass_rate` where the answer varies.

5. **Run everything against the candidate component:**

   ```sh
   python3 -m aiplayground run --target my-targets/openai-chat.json --component ../components/python/my-thing \
     --suite my-suite.json --by "Your Name <you@example.com>"
   ```

6. **Fix and compare.** Fix what failed, run again, and compare the two reports:

   ```sh
   python3 -m aiplayground compare playground-reports/<before>.json playground-reports/<after>.json
   ```

7. **Hand over.** When the verdict is `clear` (or `needs-review` with nothing you can fix), attach the report
   (`.html` and `.json`) to the pull request and ask the owner and an AI security engineer to sign.

## The AI security engineer

1. **Read the engineer's report first.** The verdict line, then "For the sign-off", then every finding with its
   evidence.

2. **Run every probe yourself**, against the same target file:

   ```sh
   python3 -m aiplayground run --target their-target.json --component ../components/python/their-thing \
     --role ai-security --by "Your Name <you@example.com>"
   ```

   `--role ai-security` selects every probe, including the tool-server set.

3. **Triage what needs a person.** For each `fail`, `review` or `error`:

   ```sh
   python3 -m aiplayground triage playground-reports/<id>.json --result leak-pii-context \
     --decision accepted-risk --by "Your Name <you@example.com>" \
     --reason "Records reach it already masked by the data guard; the probe's record is unmasked on purpose."
   ```

   Every decision needs a named person and a reason of at least a sentence, on a finding that failed, needs review
   or could not run. On a critical or high finding, `accepted-risk` and `false-positive` are taken by someone other
   than the tester (the same address in another spelling, or with a `+tag`, is the same person), and only on a run
   that names its tester (`--by`). `false-positive` says the probe was wrong. `fixed-retest` reopens a finding
   after a fix, and anyone may record it. An accepted risk is listed under "Known limits to add": the owner copies
   it into the component's README. The decision is written into the file you name (a renamed download included),
   never into another file beside it; if someone else triaged that file meanwhile, nothing is written and you run
   the command again. A report edited by hand after it was written is refused, and so is one whose triage log
   breaks these rules. A decision recorded this way on a report in the browser interface's data directory is
   picked up by the page before its next triage.

4. **Sign, outside the playground.** The report's "Cite as" line goes in the sign-off note:

   ```sh
   python3 tools/shelf.py --sign <component> --role ai-security --by "Your Name <you@example.com>"
   ```

## In a pipeline

```sh
python3 -m aiplayground run --target ci-target.json --component . --suite cases.json --fail-on needs-review --out reports/
```

Exit 0 is clear, 1 needs review (only with `--fail-on needs-review`), 2 blocked or incomplete (unreachable, refused
a plain question, or nothing applicable was checked or judged), 3 a wrong command (checked before anything runs). Keep
`reports/` as the build's artefact.

In a container, for code you do not trust: build once from the repository root with
`docker build -f playground/deploy/Dockerfile -t ai-playground .`, then run from the candidate's directory, as your
own user (so the reports are yours), with the candidate mounted at a directory of its own name (the contract check
wants the directory named as the manifest's `name`). The image is Python-only (no node, npm, npx or git): a
TypeScript candidate's tests and example do not run in it.

```sh
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work/$(basename "$PWD")" -w "/work/$(basename "$PWD")" \
  -e MODEL_GATEWAY_TOKEN ai-playground run --target t.json --component . --out reports
```

## In a browser

```sh
python3 -m aiplayground serve            # prints http://127.0.0.1:8765/#token=...
```

Set your name and role at the top right; they are recorded on runs and triage. Solutions, Try it, Run checks,
Reports (with compare: of the two runs you tick, the older is "before"), and the Probe library are the same
functions as the commands above. Runs, reports and target files are kept in `~/.aiplayground` (`--data` to
change it).
