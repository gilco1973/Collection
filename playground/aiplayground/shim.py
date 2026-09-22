"""Calls one Python function of the solution under test, in its own interpreter.

    python3 shim.py <directory> <module:function>      # reads {"prompt","system","context"} from stdin

The function is called with the keyword arguments it accepts out of prompt, system and context (a function that
takes one positional argument gets the prompt). It may return a string, or a dict with `output` (or `text`),
`tool_calls` and `citations`. The answer is one JSON line on stdout; the function's own printing goes to stderr so
it cannot be mistaken for the answer.
"""
import contextlib
import importlib
import inspect
import json
import sys


def main() -> int:
    directory, target = sys.argv[1], sys.argv[2]
    module_name, _, func_name = target.partition(":")
    sys.path.insert(0, directory)
    request = json.loads(sys.stdin.readline() or "{}")
    with contextlib.redirect_stdout(sys.stderr):
        fn = getattr(importlib.import_module(module_name), func_name)
        params = inspect.signature(fn).parameters
        kwargs = {k: request.get(k, "") for k in ("system", "context") if k in params}
        if "prompt" in params:
            result = fn(prompt=request.get("prompt", ""), **kwargs)
        else:
            result = fn(request.get("prompt", ""), **kwargs)
    if isinstance(result, str):
        result = {"output": result}
    elif not isinstance(result, dict):
        result = {"output": json.dumps(result, default=str)}
    sys.stdout.write(json.dumps(result, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
