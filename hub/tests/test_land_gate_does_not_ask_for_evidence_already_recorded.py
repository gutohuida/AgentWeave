"""F772: the Land gate does not ask the author to record evidence they already recorded.

Found on the 2026-10-19 tasks sweep. A completed task's evidence `ev-...` was awaiting, naming the
commit `24638934...` on the task's branch. Land answered 409 with two paragraphs: `unaccepted`
("nobody has judged it ... accept the evidence") and `unlanded` ("commit 24638934ec1a is on neither
master nor inside any commit the accepted evidence names ... Ask the task's author to record it").
The first is the whole remedy: accepting the piece clears both. The second sends the reader off to
record what already exists.
"""

from hub.requirement_gate import GateRefusal

TIP = "24638934ec1a" + "0" * 28
OTHER = "b" * 40


def _awaiting(commit: str) -> dict:
    return {"identifier": "FR-2", "commit_sha": commit}


def _unlanded(*commits: str) -> list:
    return [
        {"branch": "agentweave/task/task-1", "target_branch": "master", "commits": list(commits)}
    ]


def test_an_awaiting_piece_naming_every_unlanded_commit_leaves_the_unlanded_paragraph_out():
    for for_operator in (True, False):
        refusal = GateRefusal(
            unaccepted=[_awaiting(TIP)], unlanded=_unlanded(TIP), for_operator=for_operator
        )
        detail = refusal.detail()
        assert "nobody has judged it: FR-2 at 24638934ec1a" in detail
        assert "on neither" not in detail
        assert "record it" not in detail
        assert "task's author" not in detail


def test_the_refusal_still_refuses_and_reports_the_unlanded_commits_in_the_body():
    refusal = GateRefusal(unaccepted=[_awaiting(TIP)], unlanded=_unlanded(TIP))
    assert refusal.refuses
    assert refusal.to_dict()["unlanded"][0]["commits"] == [TIP]


def test_a_commit_no_awaiting_piece_names_keeps_the_unlanded_paragraph():
    refusal = GateRefusal(unaccepted=[_awaiting(TIP)], unlanded=_unlanded(TIP, OTHER))
    detail = refusal.detail()
    assert "nobody has judged it" in detail
    assert "on neither" in detail
    assert "bbbbbbbbbbbb" in detail


def test_with_nothing_awaiting_the_unlanded_paragraph_stands():
    refusal = GateRefusal(unlanded=_unlanded(TIP))
    assert "on neither" in refusal.detail()
