# playground/

The AI Playground: a standalone test bench for AI solutions before they join the collection. `README.md` is the
overview, `WALKTHROUGH.md` the two people's paths, `PROBES.md` the generated probe list.

## Working here

- Standard library only, Python 3.10+. Nothing here imports from `components/`, `services/` or `tools/`: the
  directory must work when copied on its own. The contract check reads `tools/kb-taxonomy.json` only when the
  candidate sits in a checkout of the collection.
- Tests: `python3 -m unittest discover -s tests -t .` from this directory. The browser check:
  `scripts/smoke-playground-browser.sh` from the repository root (needs Chromium and the hub's node_modules).
- A new probe: add it to `aiplayground/probes.py` with `@probe(...)`, make the safe demo hold it and the
  vulnerable demo fail it (`aiplayground/demo.py`), add it to the tests, then regenerate `PROBES.md`
  (`python3 -m aiplayground probes --markdown`, pasted under the page's first paragraph); a test refuses a stale page.
- A probe judges by something it planted (a marker, a canary, a fake card); where only a person can judge, the
  status is `review`. Never make a probe pass or fail on wording alone.
- The page (`aiplayground/static/`) shows a solution's answers with `textContent` only; keep it that way.
- The contract check must agree with `tools/shelf.py`: a component on the shelf must not fail the manifest check.
- Never put a secret, a real id or a real address in an example or a test; build secret-shaped fixtures at runtime.
