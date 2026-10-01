"""No Hub module outside the runner adapters branches on a runner's name (task 4.4).

`each-runner-cli-is-one-adapter` moves every per-runner decision onto `hub.runner_adapters`
(design D5): a caller asks `get_adapter(cli)` and reads a member, so adding a runner is one adapter,
not a hunt through the Hub for `== "claude"`. This scan is what keeps it that way. It reads source
text, not behaviour, so it is deliberately narrow: a comparison or a membership test against the
literal `"claude"` or `"codex"`, in either quote style and either operand order.

Exempt, per the task: `runner_adapters/` (where the names belong), `migrations/` (frozen history),
and `db/models.py` (column defaults). `model_catalog.py`'s `CATALOG` keys are dict keys, which the
pattern does not match, so that file is scanned like any other.
"""

from __future__ import annotations

import re
from pathlib import Path

HUB_PACKAGE = Path(__file__).resolve().parent.parent / "hub"

_NAME = r"[\"'](?:claude|codex)[\"']"
RUNNER_LITERAL = re.compile(
    rf"(?:==|!=)\s*{_NAME}"  # runner == "claude"
    rf"|{_NAME}\s*(?:==|!=)"  # "claude" == runner
    rf"|\bin\s*[\(\[\{{]\s*{_NAME}"  # runner in ("claude", ...)
)

EXEMPT_DIRS = ("runner_adapters", "migrations")
EXEMPT_FILES = (Path("db") / "models.py",)


def _scanned_files():
    for path in sorted(HUB_PACKAGE.rglob("*.py")):
        rel = path.relative_to(HUB_PACKAGE)
        if rel.parts[0] in EXEMPT_DIRS or rel in EXEMPT_FILES:
            continue
        yield rel, path


def test_the_scan_reaches_the_modules_it_guards():
    """A scan over nothing passes vacuously: the files that used to carry these branches must be in
    the set it reads."""
    scanned = {rel.as_posix() for rel, _ in _scanned_files()}
    for expected in (
        "api/v1/agent_trigger.py",
        "api/v1/agents.py",
        "runner_commands.py",
        "codex_appserver.py",
        "model_catalog.py",
    ):
        assert expected in scanned


def test_the_pattern_finds_each_form_it_names():
    for line in (
        'if runner == "claude":',
        "if runner_cli != 'codex':",
        'if "codex" == cli:',
        'if cli in ("claude", "claude_proxy"):',
        'if cli in {"codex"}:',
    ):
        assert RUNNER_LITERAL.search(line), line
    for line in ('CATALOG = {"claude": spec}', 'get_adapter("claude")', 'binary = "codex"'):
        assert not RUNNER_LITERAL.search(line), line


def test_no_hub_module_outside_the_adapters_branches_on_a_runner_name():
    hits = [
        f"{rel.as_posix()}:{lineno}: {line.strip()}"
        for rel, path in _scanned_files()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if RUNNER_LITERAL.search(line)
    ]
    assert hits == [], "\n".join(hits)
