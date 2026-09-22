#!/bin/sh
# Every gate the repository has, in one command that any runner can call (GitHub Actions, Azure Pipelines, a laptop).
#   scripts/verify.sh            # everything
#   scripts/verify.sh python     # the shelf, the vendoring, every Python component and service (no Node needed)
#   scripts/verify.sh hub        # the hub only (Node 22, pnpm 10)
#   scripts/verify.sh playground # the AI Playground only (Python; its browser check needs Node and Chromium)
# Exit code: the first gate that fails. Output: one line per gate.
set -eu
cd "$(dirname "$0")/.."
what="${1:-all}"
gate() { printf '== %s\n' "$1"; }

if [ "$what" = all ] || [ "$what" = python ]; then
  gate "shelf: manifests, vendored copies, exports current";   python3 tools/shelf.py --check
  gate "tools: unit tests";                                     python3 -m unittest discover -s tools/tests -t .
  if python3 -c "import PIL" 2>/dev/null; then
    gate "teaching guide: confluence pages current, uploader tests"; python3 docs/teaching/build_confluence.py --check && python3 -W ignore::ResourceWarning -m unittest discover -s docs/teaching/tests -t .
  fi
  gate "services: vendored files identical";                    python3 services/vendor.py --check
  gate "components: python tests";                              python3 tools/shelf.py --test --only python
  gate "components: skills";                                    python3 tools/shelf.py --test --only skills
  gate "components: python live examples";                      python3 tools/shelf.py --examples --only python
  gate "components: skills live examples";                      python3 tools/shelf.py --examples --only skills
  gate "hub-api: tests";                                        (cd services/hub-api && python3 -m unittest discover -s tests -t .)
  gate "agent-runtime: tests";                                  (cd services/agent-runtime && python3 -m unittest discover -s tests -t .)
  gate "hub-api: check-config refuses fakes in production";     (cd services/hub-api && ! HUB_ENV=production HUB_AUTH=mock python3 -m hubapi check-config >/dev/null)
  gate "agent-runtime: check-config refuses fakes in production"; (cd services/agent-runtime && ! AGENT_ENV=production python3 -m agentrt check-config >/dev/null)
  if [ -d hub/dist ]; then gate "container trees: assemble, start, health, refuse fakes"; scripts/smoke-container-tree.sh >/dev/null; fi
fi
if [ "$what" = all ] || [ "$what" = python ] || [ "$what" = playground ]; then
  gate "playground: tests";                                     (cd playground && python3 -m unittest discover -s tests -t .)
  gate "playground: the five-minute start ends clear";          (cd playground && out="$(mktemp -d)" && code=0 && { python3 -m aiplayground run --target examples/python-function.json --component examples/runbook-answerer --suite examples/runbook-suite.json --out "$out" --fail-on needs-review >/dev/null || code=$?; } && rm -rf "$out" && [ "$code" = 0 ])
  gate "playground: the vulnerable demo is blocked";            (cd playground && out="$(mktemp -d)" && code=0 && { python3 -m aiplayground run --target examples/demo-vulnerable.json --out "$out" >/dev/null || code=$?; } && rm -rf "$out" && [ "$code" = 2 ])
fi
if [ "$what" = all ] || [ "$what" = playground ]; then
  if [ -d hub/node_modules/playwright-core ] && { [ -n "${CHROMIUM_PATH:-}" ] || [ -d "${PLAYWRIGHT_BROWSERS_PATH:-/nonexistent}" ] || [ -d "${HOME:-/nonexistent}/.cache/ms-playwright" ]; }; then
    gate "playground: the page in a browser";                   scripts/smoke-playground-browser.sh >/dev/null
  fi
fi
if [ "$what" = all ] || [ "$what" = typescript ]; then
  gate "components: typescript tests and examples";             python3 tools/shelf.py --test --only typescript && python3 tools/shelf.py --examples --only typescript
fi
if [ "$what" = all ] || [ "$what" = hub ]; then
  gate "hub: typecheck, lint, tests, build";                    (cd hub && pnpm install --frozen-lockfile --prefer-offline >/dev/null && pnpm verify)
  # The browser proof runs wherever a Chromium is: CHROMIUM_PATH, a PLAYWRIGHT_BROWSERS_PATH directory, or Playwright's default cache (CI installs one there).
  if [ -n "${CHROMIUM_PATH:-}" ] || [ -d "${PLAYWRIGHT_BROWSERS_PATH:-/nonexistent}" ] || [ -d "${HOME:-/nonexistent}/.cache/ms-playwright" ]; then
    gate "hub + hub-api: real sign-in end to end (OIDC, PKCE, JWKS, silent renew, refusals)"; scripts/smoke-oidc.sh >/dev/null
    gate "hub: pixel guard against the artboards and the browser flows"; scripts/smoke-hub-browser.sh >/dev/null
  fi
fi
printf 'ok: every gate passed (%s)\n' "$what"
