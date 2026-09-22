# AI Playground

A test bench for any AI solution on its way into the collection. An engineer points it at the solution (a chat
API, an agent behind a gateway, a Python function, a command, an MCP tool server) and at the candidate component's
directory. It checks the candidate against the collection's contract, puts the solution through a library of
adversarial and robustness probes, runs the engineer's own cases, and writes a report with a verdict. An AI
security engineer reads that report, triages what needs a person, and cites it in the sign-off note.

The report is evidence, never a sign-off. Sign-offs are still recorded by a named person with
`python3 tools/shelf.py --sign`, as `CONTRIBUTING.md` says.

It is standalone: Python 3.10 or later, standard library only, nothing to install, and nothing it imports from the
rest of the repository. Copy the `playground/` directory anywhere and it works.

## Five-minute start

From this directory:

```sh
# 1. The sample candidate: its contract, its tests, every probe, and its own cases. Ends CLEAR.
python3 -m aiplayground run --target examples/python-function.json --component examples/runbook-answerer \
  --suite examples/runbook-suite.json --by "Your Name <you@example.com>"

# 2. A solution that gives way, to see a BLOCKED report and what each finding says.
python3 -m aiplayground run --target examples/demo-vulnerable.json

# 3. A tool server that gives way, probed as an AI security engineer (every probe).
python3 -m aiplayground run --target examples/mcp-stdio.json --suite examples/tools-suite.json --role ai-security

# 4. The browser interface: open the link it prints (it carries the access token).
python3 -m aiplayground serve
```

Each run prints the verdict, the findings, and the path of an HTML report under `./playground-reports/` (with the
same report as Markdown and JSON beside it).

## What it checks

| Part | What | Where |
| --- | --- | --- |
| The collection's contract | The manifest, the README's headings, sign-offs untouched, self-contained imports, no secrets, no real ids or addresses, the agent's template carries no money tool, and the component's own tests and live example run in a throwaway copy | `aiplayground/component.py` |
| Probes | 29 probes in the OWASP Top 10 for LLM applications: prompt injection (direct, in a document, in a record, encoded, obfuscated, role-play, split), disclosure (a secret in the instructions, the instructions themselves, a credential or personal data in a source), output handling (a remote image that sends data out, active content), excessive agency (money, a destructive action requested by a document), grounding, robustness (oversized, empty, unusual input, a burst), and tool-server hardening (schemas, poisoned descriptions, unknown tools, bad arguments, injection strings, an oversized argument, write annotations, survival) | `aiplayground/probes.py`, [PROBES.md](PROBES.md) |
| Your cases | What the solution is for: a question and what a good answer contains, cites or refuses; a tool call and what it returns. `repeat` and `pass_rate` for answers that vary | `aiplayground/suites.py`, `examples/runbook-suite.json` |

Every probe plants something unique (a marker, a canary, a fake card number) and judges the answer by looking for
it, so a verdict does not depend on how the solution words its reply. Where only a person can judge, the result is
`review`, never a guess.

## Describing a solution

One JSON file per solution. `python3 -m aiplayground init my-targets/` copies the examples to start from, with
the demo tool server and the sample component they point at; a file already there is left alone.

| Kind | Reaches | Example |
| --- | --- | --- |
| `http` | A chat API. `preset` is `openai-chat`, `anthropic-messages` or `simple-json`, or give `body` (a template with `{{prompt}}`, `{{context}}`, `{{system}}`, `{{messages}}`, `{{model}}`) and `response` (where the answer, tool calls and citations are) | `examples/openai-chat.json`, `examples/simple-json.json` |
| `python` | A function in the candidate's directory, called in a fresh interpreter per question | `examples/python-function.json` |
| `command` | A program that reads `{"prompt","system","context"}` on stdin and prints the answer | |
| `mcp-stdio` | An MCP server started as a command | `examples/mcp-stdio.json` |
| `mcp-http` | An MCP server over Streamable HTTP | `examples/mcp-http.json` |
| `demo` | The bundled demo assistants, `safe` or `vulnerable` | `examples/demo-safe.json` |

`capabilities` lists what the solution claims: `cites-sources` turns on the grounding probes, `masks-pii` makes a
leaked card number a failure instead of a review. `timeout_s`, `concurrency` and `max_response_bytes` bound every
call.

## Rules it enforces

- **Never production.** `environment` must be `sandbox`, `dev`, `test` or `staging`; probes are adversarial by design.
- **Only hosts you name.** A target outside loopback must be listed in `allow_hosts` (exact, or `*.domain`).
- **Credentials are names.** A secret is written `${env:NAME}` and read from the environment when a request is
  sent; a credential in a URL is refused; reports replace any credential value that comes back with `[secret]`.
- **The candidate's code runs in a copy.** Its tests and example run in a temporary directory with a minimal
  environment (only what the target's `env` names) and a time limit.
- **A person decides what a probe cannot.** `review` results, and triage by a named person (`Name <address>`)
  with a reason. A critical or high finding is accepted as a risk or called a false positive only by someone other
  than the tester (compared by address, ignoring case and spacing), and only on a run that names its tester.
- **A report is sealed.** Its id is a hash of what the run recorded (the tester and role, the results, a random
  nonce), and each triage entry carries the hash of the one before it. `triage` and `compare` refuse a report edited
  since it was written; the verdict is always recomputed from the results and the triage.
- **The report is not a sign-off.** Its `onboarding` block says so and gives the line to cite.
- **The web interface is local.** It listens on loopback only (`127.0.0.1`, or `--host ::1`), every API call needs
  the token printed at start, the Host header must be the loopback address, and the page shows a solution's answers
  as text, never as HTML.

## Verdicts and exit codes

| Verdict | When | `run` exits |
| --- | --- | --- |
| `clear` | Everything that applies held, or was triaged by a named person | 0 |
| `needs-review` | A medium or low failure, a `review`, or a probe that could not run | 0, or 1 with `--fail-on needs-review` |
| `blocked` | A critical or high finding failed and nobody has triaged it | 2 |
| `incomplete` | The solution could not be reached, or nothing that applies was checked (every probe and case was skipped) | 2 |

A wrong command is 3. In CI: `python3 -m aiplayground run --target t.json --component . --fail-on needs-review`.

## What is inside

| Path | What |
| --- | --- |
| `aiplayground/config.py` | The target file: kinds, presets, environments, the host allow-list, `${env:NAME}` |
| `aiplayground/targets.py` | One adapter per kind; every failure becomes a reply with `error` set |
| `aiplayground/probes.py` | The probe library and how probes are chosen |
| `aiplayground/suites.py` | Your cases and their expectations |
| `aiplayground/component.py` | The collection's contract on a directory |
| `aiplayground/runner.py` | One run: contract, probes, suites, into one report |
| `aiplayground/report.py` | Verdicts, triage, and the JSON, Markdown and HTML reports |
| `aiplayground/store.py`, `server.py`, `static/` | The browser interface and its record (`~/.aiplayground` by default) |
| `aiplayground/demo.py` | The safe and vulnerable demos, as a chat API and an MCP server |
| `examples/` | Target files, suites, and `runbook-answerer`, a sample candidate component |
| `tests/` | `python3 -m unittest discover -s tests -t .` |
| `tools/uitest.cjs` | The browser check (`scripts/smoke-playground-browser.sh` from the repository root) |

## Known limits

- The probes are a floor, not a proof: a solution that passes them can still be steered by an attack they do not
  try. Add cases for what your solution touches, and keep the report's findings in the README's "Known limits".
- Detection is by planted markers and patterns. A solution that paraphrases a secret instead of repeating it
  (the canary spelled out in words) is not caught; an AI security engineer reads the evidence.
- One turn per probe: multi-turn attacks (building trust over several messages) are not tried yet.
- MCP over HTTP is JSON and SSE responses to POST; server-initiated requests (elicitation) are declined.
- The browser interface is for one person on one machine; it is not a shared service.
