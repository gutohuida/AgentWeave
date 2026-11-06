"""The PR landing drive's nm-ac1 filter bans merges, approvals, base changes and protection
changes by operation, and lets the calls FR-12 allows (open, edit, draft, ready, read) through."""

import importlib.util
from pathlib import Path

import pytest

DRIVE = Path(__file__).resolve().parents[1] / "scripts" / "drive" / "pr_landing_drive.py"


@pytest.fixture(scope="module")
def is_banned():
    spec = importlib.util.spec_from_file_location("pr_landing_drive", DRIVE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.is_banned


ALLOWED = [
    "pr create --base master --draft --title t --body b",
    "pr ready 5",
    "pr ready 5 --undo",
    "pr edit 5 --body text",
    "pr view 5 --json state",
    "api repos/o/r/pulls/5",
    "api repos/o/r/pulls/5 --jq .merge_commit_sha",
    "api -X POST repos/o/r/pulls -f title=t -f head=b -f base=master",
    "api --method PATCH repos/o/r/pulls/5 -f body=text",
    "pr review 5 --comment --body hi",
]

BANNED = [
    "pr merge 5 --squash",
    "pr review 5 --approve",
    "pr edit 5 --base other",
    "api -X PUT repos/o/r/pulls/5/merge",
    "api repos/o/r/pulls/5/merge -X PUT",
    "api -X POST repos/o/r/pulls/5/reviews -f event=APPROVE",
    "api -X PATCH repos/o/r/pulls/5 -f base=other",
    "api -X PUT repos/o/r/branches/master/protection",
    "api repos/o/r/rulesets",
]


@pytest.mark.parametrize("call", ALLOWED)
def test_allowed(is_banned, call):
    assert not is_banned(call.split())


@pytest.mark.parametrize("call", BANNED)
def test_banned(is_banned, call):
    assert is_banned(call.split())
