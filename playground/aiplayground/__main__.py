"""The AI Playground's command line.

    python3 -m aiplayground init DIR                        example target files and a suite to start from
    python3 -m aiplayground check TARGET.json               is the target file usable (no request is sent)
    python3 -m aiplayground ask TARGET.json "question"      one question, the answer as received
    python3 -m aiplayground tools TARGET.json               a tool server's tools
    python3 -m aiplayground probes [--markdown]             the probe library
    python3 -m aiplayground run --target T.json [--component DIR] [--suite S.json] [--probes all|security|...]
                                [--by "Name <address>"] [--role engineer|ai-security] [--out DIR] [--fail-on blocked|needs-review]
    python3 -m aiplayground check-component DIR [--no-run] [--out DIR]
    python3 -m aiplayground triage REPORT.json --result ID --decision accepted-risk --by "Name <address>" --reason "..."
    python3 -m aiplayground compare BEFORE.json AFTER.json
    python3 -m aiplayground serve [--port 8765] [--data DIR]
    python3 -m aiplayground demo-server [--port 8099] [--vulnerable]
    python3 -m aiplayground demo-mcp [--vulnerable]

Exit codes of `run` and `check-component`: 0 clear, 1 needs review, 2 blocked or incomplete, 3 the command itself
was wrong. `--fail-on needs-review` makes 1 a failure in CI; the default fails only on blocked.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from . import __version__
from . import config as C
from . import probes as P
from . import report as Rp
from . import runner
from . import suites as S
from .targets import open_target

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = os.path.join(os.path.dirname(HERE), "examples")
EXIT = {"clear": 0, "needs-review": 1, "blocked": 2, "incomplete": 2}


def say(*a):
    print(*a, flush=True)


def cmd_init(a):
    os.makedirs(a.dir, exist_ok=True)
    copied = []
    for f in sorted(os.listdir(EXAMPLES)):
        if f.endswith(".json"):
            dest = os.path.join(a.dir, f)
            if os.path.exists(dest):
                continue
            shutil.copyfile(os.path.join(EXAMPLES, f), dest)
            copied.append(f)
    say(f"wrote {len(copied)} file(s) to {a.dir}: {', '.join(copied) or 'nothing new'}")
    say("next: edit a target file, then  python3 -m aiplayground check <target.json>")
    return 0


def cmd_check(a):
    t = C.load(a.target)
    say(json.dumps(t.describe(), indent=2))
    missing = [n for n in t.secret_names() + list(t.env) if n not in os.environ]
    if missing:
        say(f"note: not set in this shell: {', '.join(missing)} (needed when the target is called)")
    say("ok: the target file is usable")
    return 0


def cmd_ask(a):
    t = C.load(a.target)
    ad = open_target(t)
    try:
        r = ad.ask(a.question, system=a.system or "", context=a.context or "")
    finally:
        ad.close()
    out = Rp.scrub(r.to_json(), C.secret_values(t))
    say(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if r.ok() else 1


def cmd_tools(a):
    t = C.load(a.target)
    ad = open_target(t)
    try:
        if not ad.tool_server:
            say(f"{t.name} is a {t.kind} target: it answers questions, it lists no tools")
            return 3
        for tool in ad.tools():
            say(f"- {tool.get('name')}: {(tool.get('description') or '')[:120]}")
    finally:
        ad.close()
    return 0


def cmd_probes(a):
    cat = P.catalog()
    if a.markdown:
        say("| Id | Probe | Category | Severity | Applies to | Suite | Why it matters |")
        say("| --- | --- | --- | --- | --- | --- | --- |")
        for p in cat:
            applies = "tool servers" if p["applies"] == "tool" else "question-answering solutions"
            if p["needs"]:
                applies += f" claiming `{p['needs']}`"
            say(f"| `{p['id']}` | {p['title']} | {p['category']} {p['category_name']} | {p['severity']} | {applies} | {p['suite']} | {p['why']} |")
        return 0
    for p in cat:
        say(f"{p['id']:26s} {p['severity']:8s} {p['category']:5s} {p['suite']:10s} {p['title']}")
    return 0


def finish(rep, a) -> int:
    out = a.out or os.path.join(os.getcwd(), "playground-reports")
    paths = Rp.save(rep, out)
    s = rep["summary"]["by_status"]
    say(f"{rep['verdict'].upper()}: {rep['verdict_reason']}")
    say("  " + ", ".join(f"{k} {v}" for k, v in s.items() if v))
    for r in rep["results"]:
        if r["status"] in ("fail", "review", "error"):
            say(f"  {r['status']:6s} {r['severity']:8s} {r['id']:30s} {r['summary'][:110]}")
    say(f"report {rep['id']}: {paths['html']}")
    code = EXIT[rep["verdict"]]
    if code == 1 and a.fail_on != "needs-review":
        return 0
    return code


def progress(done, total, label):
    if sys.stderr.isatty():
        sys.stderr.write(f"\r  {done}/{total} {label[:50]:50s}")
        sys.stderr.flush()
        if done == total:
            sys.stderr.write("\n")


def cmd_run(a):
    t = C.load(a.target) if a.target else None
    rep = runner.run(t, probes=a.probes, suites=a.suite or [], component_dir=a.component, run_component=not a.no_run,
                     by=a.by or "", role=a.role, progress=progress)
    return finish(rep, a)


def cmd_check_component(a):
    rep = runner.run(None, component_dir=a.dir, run_component=not a.no_run, by=a.by or "", role=a.role)
    return finish(rep, a)


def cmd_triage(a):
    rep = Rp.load(a.report)
    Rp.triage(rep, a.result, a.decision, a.by, a.reason)
    paths = Rp.save(rep, os.path.dirname(os.path.abspath(a.report)))
    say(f"recorded: {a.decision} on {a.result} by {a.by}; verdict now {rep['verdict']}")
    say(f"report: {paths['html']}")
    return 0


def cmd_compare(a):
    before, after = Rp.load(a.before), Rp.load(a.after)
    rows = Rp.compare(before, after)
    say(f"{before['id']} ({before['verdict']}) -> {after['id']} ({after['verdict']})")
    if not rows:
        say("no result changed")
    for r in rows:
        say(f"  {r['change']:7s} {r['id']:32s} {r['before']} -> {r['after']}")
    return 2 if any(r["change"] == "worse" for r in rows) else 0


def cmd_serve(a):
    from . import server
    return server.main(a.port, a.data, a.host)


def cmd_demo_server(a):
    from . import demo
    httpd = demo.make_server(a.port, a.vulnerable)
    say(f"demo {'vulnerable' if a.vulnerable else 'safe'} solution on http://127.0.0.1:{httpd.server_address[1]}  "
        "(/v1/chat/completions, /chat, /mcp; Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_demo_mcp(a):
    from . import demo
    demo.serve_mcp_stdio(a.vulnerable)
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python3 -m aiplayground", description="The AI Playground: test an AI solution before it joins the collection.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init", help="example target files and a suite")
    s.add_argument("dir")
    s.set_defaults(fn=cmd_init)
    s = sub.add_parser("check", help="validate a target file; nothing is sent")
    s.add_argument("target")
    s.set_defaults(fn=cmd_check)
    s = sub.add_parser("ask", help="one question to a target")
    s.add_argument("target")
    s.add_argument("question")
    s.add_argument("--system")
    s.add_argument("--context")
    s.set_defaults(fn=cmd_ask)
    s = sub.add_parser("tools", help="list a tool server's tools")
    s.add_argument("target")
    s.set_defaults(fn=cmd_tools)
    s = sub.add_parser("probes", help="the probe library")
    s.add_argument("--markdown", action="store_true")
    s.set_defaults(fn=cmd_probes)
    for name, fn in (("run", cmd_run), ("check-component", cmd_check_component)):
        s = sub.add_parser(name, help="probe a target and check a component" if name == "run" else "the collection's contract on a directory")
        if name == "run":
            s.add_argument("--target", help="the target file")
            s.add_argument("--component", help="the candidate component's directory: its contract is checked too")
            s.add_argument("--suite", action="append", help="a suite file; repeatable")
            s.add_argument("--probes", help="all, security, robustness, quality, none, or probe ids (comma separated); default by role")
        else:
            s.add_argument("dir")
        s.add_argument("--no-run", action="store_true", help="do not run the component's tests and example")
        s.add_argument("--by", help='the tester, "Name <address>"')
        s.add_argument("--role", default="engineer", choices=runner.ROLES)
        s.add_argument("--out", help="where the report goes (default ./playground-reports)")
        s.add_argument("--fail-on", default="blocked", choices=("blocked", "needs-review"))
        s.set_defaults(fn=fn)
    s = sub.add_parser("triage", help="record a named person's decision on a finding")
    s.add_argument("report")
    s.add_argument("--result", required=True)
    s.add_argument("--decision", required=True, choices=Rp.DECISIONS)
    s.add_argument("--by", required=True)
    s.add_argument("--reason", required=True)
    s.set_defaults(fn=cmd_triage)
    s = sub.add_parser("compare", help="what changed between two reports")
    s.add_argument("before")
    s.add_argument("after")
    s.set_defaults(fn=cmd_compare)
    s = sub.add_parser("serve", help="the web interface")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--data", default=os.path.join(os.path.expanduser("~"), ".aiplayground"))
    s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("demo-server", help="a demo solution over HTTP")
    s.add_argument("--port", type=int, default=8099)
    s.add_argument("--vulnerable", action="store_true")
    s.set_defaults(fn=cmd_demo_server)
    s = sub.add_parser("demo-mcp", help="a demo MCP server on stdio")
    s.add_argument("--vulnerable", action="store_true")
    s.set_defaults(fn=cmd_demo_mcp)
    return ap


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    if a.cmd == "run" and not a.target and not a.component:
        print("run: name --target, --component, or both", file=sys.stderr)
        return 3
    try:
        return a.fn(a)
    except (C.ConfigError, S.SuiteError, ValueError, FileNotFoundError) as e:
        print(f"{a.cmd}: {e}", file=sys.stderr)
        return 3
    except RuntimeError as e:
        print(f"{a.cmd}: {e}", file=sys.stderr)
        return 2
    except BrokenPipeError:   # the output went to a pager or head that closed early
        try:
            sys.stdout = open(os.devnull, "w")
        except OSError:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
