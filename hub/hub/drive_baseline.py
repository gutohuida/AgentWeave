"""An acceptance drive is approved only on a baseline showing each check reached and failing.

`evidence-review-sends-work-back-only-for-what-is-wrong-with-it`, task `baseline-gate`. A change's
first task is its acceptance drive (`spec_completeness.acceptance_drive_key`), written and failing
before the build. Approval used to check only that the drive came first, not that it failed for
the right reason, so a drive that stopped at a 404 before its assertion, or passed on no-op code,
was found only after the whole build.

FR-6: the drive task is not approved without accepted evidence of kind `drive_baseline`, listing
each check the drive covers, one line per check:

    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>

FR-7: a baseline in which a check was not reached, or did not fail at its own assertion, is not
accepted: an agent's acceptance of it is refused, and so is an approval that would accept it, with
the checks named so the reviewer sends the drive back naming them. Whether a check failed for the
*right* reason stays the reviewer's judgement (D4); the Hub reads only what the baseline states.

The operator is held only to FR-6: what they may do with evidence is unchanged (a non-goal), so a
baseline they accepted is theirs to have judged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import blocking
from .db.models import RequirementEvidence, SpecDocument, Task

KIND = "drive_baseline"
MISSING = "drive_baseline_missing"
NOT_FAILING = "drive_baseline_checks_not_failing"

LINE_FORMAT = "check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>"

_LINE = re.compile(
    r"^\s*check\s+(?P<key>[^\s:]+)\s*(?:\([^)]*\))?\s*:\s*reached\s*=\s*(?P<reached>yes|no)\s+"
    r"failed_at_assertion\s*=\s*(?P<failed>yes|no)\b(?:\s*--\s*(?P<detail>.*))?$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class Check:
    key: str
    reached: bool
    failed_at_assertion: bool
    detail: str
    evidence_id: str

    @property
    def bad(self) -> bool:
        return not (self.reached and self.failed_at_assertion)

    def why(self) -> str:
        if not self.reached:
            return "was not reached (it stopped before its assertion)"
        return "did not fail at its own assertion on the pre-build code"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check": self.key,
            "reached": self.reached,
            "failed_at_assertion": self.failed_at_assertion,
            "detail": self.detail,
            "evidence_id": self.evidence_id,
        }


def is_baseline(evidence: RequirementEvidence) -> bool:
    return (evidence.kind or "").strip().lower() == KIND


def checks_of(evidence: RequirementEvidence) -> List[Check]:
    """The checks a baseline row lists, from its output and its summary, one per key: a key
    stated twice counts as its worse statement."""
    found: Dict[str, Check] = {}
    for text in (evidence.output or "", evidence.summary or ""):
        for match in _LINE.finditer(text):
            check = Check(
                key=match["key"],
                reached=match["reached"].lower() == "yes",
                failed_at_assertion=match["failed"].lower() == "yes",
                detail=(match["detail"] or "").strip()[:300],
                evidence_id=evidence.id,
            )
            if check.key not in found or (check.bad and not found[check.key].bad):
                found[check.key] = check
    return list(found.values())


def bad_checks(evidence: RequirementEvidence) -> List[Check]:
    return [check for check in checks_of(evidence) if check.bad]


def _document_tasks(workspace, path: str) -> Optional[list]:
    from .spec_documents import read_payload

    payload = read_payload(workspace, path)
    tasks = (payload or {}).get("tasks")
    return tasks if isinstance(tasks, list) else None


async def is_acceptance_drive(session: AsyncSession, task: Task) -> bool:
    """Whether *task* is its change document's acceptance drive. A document that cannot be read
    is no evidence that it is one: the gate is not invented from a missing file."""
    from .project_workspace import ProjectWorkspaceError, resolve_project_workspace
    from .spec_completeness import acceptance_drive_key
    from .spec_manifest import SpecPathError

    if not task.spec_document_id or not task.spec_task_key:
        return False
    document = await session.get(SpecDocument, task.spec_document_id)
    if document is None or document.kind != "change-spec":
        return False
    try:
        workspace = await resolve_project_workspace(session, task.project_id)
        tasks = await blocking.run(_document_tasks, workspace, document.path)
    except (ProjectWorkspaceError, SpecPathError, OSError, ValueError):
        return False
    if not tasks:
        return False
    shape = [
        (
            str(entry.get("key") or ""),
            bool(entry.get("from")),
            [str(dep) for dep in (entry.get("depends_on") or [])],
        )
        for entry in tasks
        if isinstance(entry, dict)
    ]
    return acceptance_drive_key(shape) == task.spec_task_key


class DriveBaselineRefusal:
    """The structured body of an approval refused over the drive baseline (main.py's handler
    sends `to_dict()`; the MCP adapter returns its `message`)."""

    def __init__(self, code: str, message: str, checks: List[Check]) -> None:
        self.code, self.message, self.checks = code, message, checks

    def detail(self) -> str:
        return self.message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "checks": [check.to_dict() for check in self.checks],
        }


def _named(checks: List[Check]) -> str:
    return "; ".join(f"`{check.key}` {check.why()}" for check in checks)


def not_failing_sentence(task_id: str, checks: List[Check]) -> str:
    pieces = sorted({check.evidence_id for check in checks})
    failing = ", ".join(
        f'{{"piece": "{piece}", "reason": "<each check named, and why>"}}' for piece in pieces
    )
    return (
        f"{task_id} is its document's acceptance drive, and its drive baseline lists checks that "
        f"do not fail at their own assertion on the pre-build code: {_named(checks)}. A drive "
        "whose check stops before its assertion can never pass, and one that passes before the "
        "build tests nothing, so it is not accepted. Move the task to revision_needed with "
        "reason_class `broken-check`, notes naming each of these checks, and "
        f"failing_pieces [{failing}], so its builder fixes the drive before anything is built "
        "on it."
    )


async def approval_refusal(
    session: AsyncSession, task: Task, *, is_operator: bool
) -> Optional[DriveBaselineRefusal]:
    """Why approving the acceptance-drive *task* is refused, read after the verdict has accepted
    its evidence in the same savepoint, or None. The caller has established it is the drive."""
    rows = list(
        (
            await session.execute(
                select(RequirementEvidence)
                .where(
                    RequirementEvidence.task_id == task.id,
                    RequirementEvidence.review_state == "accepted",
                )
                .order_by(RequirementEvidence.produced_at, RequirementEvidence.id)
            )
        )
        .scalars()
        .all()
    )
    baselines = [row for row in rows if is_baseline(row)]
    listed = [row for row in baselines if checks_of(row)]
    if not listed:
        said = (
            "it has no accepted evidence of kind `drive_baseline`"
            if not baselines
            else "its accepted `drive_baseline` evidence lists no check in the baseline's format"
        )
        return DriveBaselineRefusal(
            MISSING,
            f"{task.id} is its document's acceptance drive and cannot be approved: {said}. The "
            "drive's builder records it (record_evidence with kind `drive_baseline`), its output "
            f"one line per check the drive covers, `{LINE_FORMAT}`, from running the drive on the "
            "pre-build code. Where it is missing, send the task back to its builder naming the "
            "missing baseline (reason_class `evidence-only`).",
            [],
        )
    if is_operator:
        return None
    bad = [check for row in listed for check in bad_checks(row)]
    if bad:
        return DriveBaselineRefusal(NOT_FAILING, not_failing_sentence(task.id, bad), bad)
    return None


async def review_sentence(session: AsyncSession, task: Task) -> Optional[str]:
    """The per-check rule, for the reviewer of an acceptance-drive task (FR-7). None otherwise."""
    if not await is_acceptance_drive(session, task):
        return None
    return (
        f"**{task.id} is its document's acceptance drive.** It is approved only on accepted "
        "evidence of kind `drive_baseline` listing each check the drive covers, one line per "
        f"check: `{LINE_FORMAT}`. Judge each check: it must have been reached on the pre-build "
        "code (not stopped at setup, a 404 or 409, or a crash) and have failed at its own "
        "assertion. Where any check was not reached, or passed on the pre-build code, do not "
        "approve: send the task back (`revision_needed`, reason_class `broken-check`) with notes "
        "naming every such check and the baseline piece in failing_pieces. Where the baseline is "
        "missing, send it back naming the missing baseline. Running the drive yourself on the "
        "pre-build code is how you tell whether a check fails for the right reason."
    )
