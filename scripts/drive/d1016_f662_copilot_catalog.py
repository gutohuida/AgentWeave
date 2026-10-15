"""Acceptance drive for F662 (fix-D5): the Copilot catalog tracks the CLI (1.0.94-3).

Before: a Copilot runner on `claude-haiku-5.5` or `grok-4.7` (both offered by the CLI) was refused
400, and one on the retired `claude-opus-4.7` was accepted. After: the reverse.

  py -3.11 scripts/drive/d1016_f662_copilot_catalog.py <project-name>

Drives the Hub `e2e.py hub-up` started (never :8000 or :8010). No agent turns (Copilot is driven on
the work PC). Exit 1 on any fail.
"""

import importlib.util
import pathlib
import sys

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def runner(project, model):
    return e2e.request(
        "POST",
        f"/projects/{project}/runners",
        {"name": f"copilot {model}", "cli": "copilot", "model": model},
    )


def main(name):
    project = e2e.cmd_setup(name)
    for model in ("claude-haiku-5.5", "grok-4.7"):
        status, res = runner(project, model)
        check(f"a Copilot runner on {model} is created", status == 201, f"{status} {str(res)[:200]}")
    status, res = runner(project, "claude-opus-4.7")
    check(
        "a Copilot runner on the retired claude-opus-4.7 is refused",
        status == 400 and "copilot" in str(res),
        f"{status} {str(res)[:200]}",
    )


if __name__ == "__main__":
    main(*sys.argv[1:])
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
