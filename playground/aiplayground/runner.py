"""One run: the contract check, the probes and the suites against one solution, into one report.

The order is the order a reviewer reads: does the candidate meet the collection's contract, does the solution hold
under attack, does it do its job. The solution is reached once first (a smoke question, or tools/list); if that
fails the run stops with an `incomplete` report instead of fifty errors.
"""
from __future__ import annotations

import inspect
from concurrent.futures import ThreadPoolExecutor

from . import component as K
from . import config as C
from . import probes as P
from . import report as Rp
from . import suites as S
from .targets import open_target

ROLES = ("engineer", "ai-security")
DEFAULT_PROBES = {"engineer": "security,robustness,quality", "ai-security": "all"}


def _accepts(fn, name: str) -> bool:
    """Whether `fn` takes a keyword `name` (the contract check's `exclude` arrives with another change)."""
    try:
        return name in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def smoke(adapter, secrets=()) -> str | None:
    """None when the solution answers; otherwise why not.

    Any error on the plain question stops the run, a 4xx included: a guard's refusal (400, 422...) counts in the
    probes only because the same solution answers an ordinary question, so a service that refuses everything
    (a wrong model name, a broken request template) is `incomplete`, never clear. So is an empty answer: a wrong
    response path reads every answer as "", and a probe that looks for its marker in "" would call it held."""
    if adapter.chat:
        r = adapter.ask("Say hello in one word.")
        if r.error:
            status = r.status if isinstance(r.status, int) else None
            said = cut(" ".join(scrub(r.text or "", secrets).split()), 200, secrets)   # scrubbed whole, then cut
            error = scrub(r.error, secrets)
            detail = error + (f": {said}" if said and said not in error else "")
            if status is not None and 400 <= status < 500:
                return f"the solution refused a plain question: {detail}"
            return f"the solution did not answer a plain question: {detail}"
        if P.empty(r):
            return "the solution's answer was empty: check the target's response path (response.text) or output shape"
        return None
    try:
        adapter.tools()
    except (RuntimeError, OSError, ValueError) as e:
        return scrub(f"the tool server did not list its tools: {e}", secrets)
    return None


FRAGMENT = 8   # the shortest piece of a secret that is removed when it shows at a cut edge


def scrub(text: str, secrets=()) -> str:
    """The text with every secret value replaced, longest first (so a value inside another is not left half-shown),
    then any piece of a secret that text cut elsewhere left behind (a start or an end of the value, 8 characters or
    more: a stderr tail cut inside a token starts with the token's end)."""
    secrets = sorted((s for s in secrets if s), key=len, reverse=True)
    for s in secrets:
        text = text.replace(s, "[secret]")
    for s in secrets:
        for n in range(len(s) - 1, FRAGMENT - 1, -1):
            for piece in (s[-n:], s[:n]):
                if piece in text:
                    text = text.replace(piece, "[secret]")
    return text


def cut(text: str, limit: int, secrets=()) -> str:
    """At most `limit` characters of scrubbed text, and no piece of a secret left at the edge of the cut."""
    if len(text) <= limit:
        return text
    return scrub(text[:limit], secrets) + "…"


def run(target: C.Target | None = None, *, probes: str | list | None = None, suites: list = (), component_dir: str | None = None,
        run_component: bool = True, by: str = "", role: str = "engineer", progress=None, component_timeout: int = 300,
        component_exclude: list = ()) -> dict:
    """Everything asked for, then the report. `progress(done, total, label)` is called as checks finish.
    `component_exclude` names paths the contract check leaves out (the report directory, when it sits inside the
    component)."""
    if role not in ROLES:
        raise ValueError(f"role is one of {', '.join(ROLES)}")
    if target is None and not component_dir:
        raise ValueError("name a target, a component directory, or both")
    started = Rp.now()
    loaded = [S.load(s) for s in suites]
    S.check_distinct(loaded)
    chosen = P.select(DEFAULT_PROBES[role] if probes is None else probes, target) if target else []
    total = (len(chosen) + sum(len(s["cases"]) for s in loaded) if target else 0) + (1 if component_dir else 0)
    done = [0]

    def tick(label):
        done[0] += 1
        if progress:
            progress(done[0], total, label)

    results = []
    if component_dir:
        extra = {"exclude": list(component_exclude)} if component_exclude and _accepts(K.check, "exclude") else {}
        results += K.check(component_dir, run=run_component, timeout=component_timeout, **extra)
        tick("contract")
    tester = {"by": by, "role": role}
    meta = dict(target=target.describe() if target else None, component=K.describe(component_dir) if component_dir else None, tester=tester,
                started=started, suites=[s["name"] for s in loaded], probes=[p.id for p in chosen])
    if not target:
        return Rp.build(results, **meta)
    adapter = open_target(target)
    try:
        why = smoke(adapter, C.secret_values(target))
        if why:
            return Rp.build(results, secrets=C.secret_values(target), incomplete=why, **meta)
        # chat probes run side by side (each is independent); the burst runs alone so it measures the solution, not
        # the other probes; a tool server's probes run one at a time on its single connection, tool-alive last.
        parallel = [p for p in chosen if p.applies == "chat" and p.id != "perf-burst"]
        serial = [p for p in chosen if p not in parallel]
        with ThreadPoolExecutor(max_workers=target.concurrency) as pool:
            for r in pool.map(lambda p: P.run_probe(p, adapter, target), parallel):
                results.append(r)
                tick(r.id)
        for p in serial:
            results.append(P.run_probe(p, adapter, target))
            tick(p.id)
        for s in loaded:
            for case in s["cases"]:
                results.append(S.run_case_safely(case, adapter, s["name"]))
                tick(f"{s['name']}/{case['id']}")
    finally:
        adapter.close()
    return Rp.build(results, secrets=C.secret_values(target), **meta)
