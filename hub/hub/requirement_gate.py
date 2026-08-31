"""The gate: a task cannot be approved while a requirement it serves is unverified.

It lives inside the transition service rather than beside it. A second enforcement
point is a second thing to bypass, and the rule that no route assigns
`Task.status` directly is what makes one point sufficient.

**On `approved`, not `completed`.** `completed` is an agent reporting it finished
writing; `approved` records that the work is good, and is terminal. Evidence is
accepted after review and review follows completion, so refusing `completed`
would deadlock the ordinary path — the task could never reach the step that
produces the acceptance it is blocked for.

**Coverage comes from B3's single query.** If the gate computed its own answer, a
task could be refused while the document beside it showed everything green, and
nobody could say which was lying. One query, or two truths.

**A refusal has to be actionable.** This is the first thing in the product that
can stop the operator's own work, so the failure response is part of the feature:
each blocked requirement is named with its state and with what would change it.
An unactionable gate gets switched off, which is worse than never having built
one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import requirement_coverage, run_liveness, spec_rigor
from .db.models import SpecDocument, SpecRequirement, Task, TaskRequirementLink

# The state a `gate` requirement must be in. Deliberately one value: `verified` means the same at
# every rigor, because a word whose meaning shifts with context is worse than a strict one — and
# because promoting a document would otherwise silently un-verify requirements that were verified a
# moment before.
SATISFIED = requirement_coverage.VERIFIED

# What to do about each state that is not `verified`. The wording is the feature: "the gate refused"
# without it is unactionable.
REMEDY = {
    requirement_coverage.UNSERVED: "no task is linked to it — link the work that serves it",
    requirement_coverage.NOT_STARTED: "its linked work has not started",
    requirement_coverage.IN_PROGRESS: (
        "its linked work has produced no evidence — record what demonstrates it"
    ),
    requirement_coverage.REJECTED: (
        "the evidence recorded for it was reviewed and rejected — record evidence that satisfies "
        "the current wording"
    ),
    requirement_coverage.AWAITING_REVIEW: (
        "its evidence is waiting for someone to accept it — accept or reject it"
    ),
    requirement_coverage.STALE: (
        "its evidence was produced against an earlier wording — record evidence for what it "
        "says now"
    ),
    requirement_coverage.DRIFTING: (
        "the implementation changed after it was verified — resolve the drift candidate"
    ),
}


# What an entry in `reported`/`advisory` is about. Both lists are carried out of the transition on
# the same attribute, so each entry has to say which it is or a consumer cannot tell a `contract`
# rigor report from evidence nobody has judged.
REPORT_REQUIREMENT = "requirement"
REPORT_AWAITING_EVIDENCE = "awaiting_evidence"

# Named once because the refusal and the advisory say the same thing, and because the requirement is
# explicit that both ways out are named: accepting evidence is the operator's unless an agent has
# been granted it, and no agent is granted it by default. An agent reading this can take neither
# remedy itself, and saying so is what stops it retrying.
ACCEPT_OR_GRANT = (
    "accept the evidence, or grant an agent the capability to accept it — both are the "
    "operator's, so an agent reading this has to ask for one rather than take it"
)


@dataclass
class GateRefusal:
    """Why the gate refused, in a shape a surface can render without parsing prose."""

    blocking: List[Dict[str, str]] = field(default_factory=list)
    diagnostics: List[Dict[str, str]] = field(default_factory=list)
    # Work that cannot land where approval says it lands. Separate from `blocking` because it is a
    # different kind of claim: not "this is unproven" but "this cannot go in". An operator told the
    # requirement is unverified would go and record evidence, which would not help at all here.
    unmergeable: List[Dict[str, Any]] = field(default_factory=list)
    # Evidence that names a commit and is still waiting to be judged, where nothing accepted names
    # one. A third kind of claim again: not "this is unproven" and not "this cannot go in", but
    # "nothing would go in while something is waiting to be judged". Approving here would record
    # that the work is good and merge none of it, and the skip would read like an absence of work
    # rather than a queue of it.
    unaccepted: List[Dict[str, Any]] = field(default_factory=list)
    # `contract`-rigor requirements that are not verified, named the same way a `blocking` entry
    # is — identifier, state, remedy — but never inspected by `refuses`. This is `contract`'s whole
    # behaviour: report unmet and rejected requirements at the moment of approval, without ever
    # standing in the way of it. `sketch` never reaches here at all (task 5.5 of
    # `2026-08-13-a-gate-that-only-evidence-opens`).
    reported: List[Dict[str, str]] = field(default_factory=list)
    # A turn that is still producing the work. A fifth kind of claim: not "this is unproven", not
    # "this cannot go in", not "something is waiting to be judged", but **"what would go in is not
    # knowable yet"**. The agent recorded `completed` during its turn; the commit that holds its
    # edits is made when the turn ends, so until then the task's branch points at the commit it was
    # cut from and every answer to "which commit is this task's work?" names one containing none of
    # it. An operator told the requirement is unverified, or that the branch conflicts, would go
    # looking for something to fix; there is nothing to fix, only a moment to wait through.
    unfinished: List[Dict[str, str]] = field(default_factory=list)
    # Evidence still awaiting review on a task that *does* have accepted evidence naming a commit.
    # Approval succeeds there and merges what was accepted, so this is a report rather than a
    # refusal — deliberately absent from `refuses` and from `detail()`. Refusing would block work
    # that is genuinely ready because a second piece is still in review.
    advisory: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def refuses(self) -> bool:
        return bool(
            self.blocking
            or self.diagnostics
            or self.unmergeable
            or self.unaccepted
            or self.unfinished
        )

    def detail(self) -> str:
        """One sentence per category that has anything to say, composed explicitly.

        This used to return `_merge_detail()` from an early return when `unmergeable` was the only
        category set. A third category appended to the tail of the other branch would have been
        silently dropped in exactly the case that matters most — an otherwise-clean task whose only
        problem is the new one. Composition rather than a special case is what makes that
        impossible; the text for the two pre-existing shapes is unchanged.
        """
        return " ".join(
            sentence
            for sentence in (
                self._unverified_detail(),
                self._merge_detail(),
                self._unaccepted_detail(),
                self._unfinished_detail(),
            )
            if sentence
        )

    def _unverified_detail(self) -> str:
        parts: List[str] = []
        for entry in self.blocking:
            parts.append(f"{entry['identifier']} is {entry['state']}: {entry['remedy']}")
        for entry in self.diagnostics:
            parts.append(
                f"{entry['identifier'] or 'a requirement'} cannot be checked at all: "
                f"{entry['problem']}"
            )
        if not parts:
            return ""
        return (
            "This task serves requirements a gate is enforcing, and they are not verified: "
            + "; ".join(parts)
            + ". Satisfy them, or lower the document's rigor — which is recorded."
        )

    def _merge_detail(self) -> str:
        """The conflict, and a remedy that depends on where the judged commit came from (F155).

        Found live 2026-08-30: this said *"Resolve the conflict on the branch, then approve"* on
        every route. On the evidence route that instruction is false, not merely unhelpful — what
        approval merges is the commit the accepted evidence names, so a resolution commit no
        evidence names changes nothing and the answer cannot change however many times approval is
        retried. The reviewer who followed it and got the identical sentence back reached for
        `git reset --hard` on a branch holding the only copy of an agent's work.

        So the two routes get two sentences, grouped on the per-target `named_by_evidence`
        (design D1). A task cannot today carry both shapes at once — `merge_targets` returns one or
        the other — but the grouping does not rely on that, because it would be an invariant stated
        in another module and `evidence_governs` is exactly the kind of ladder that grows a sixth
        answer (design D5).
        """
        if not self.unmergeable:
            return ""
        named = [entry for entry in self.unmergeable if entry.get("named_by_evidence")]
        tips = [entry for entry in self.unmergeable if not entry.get("named_by_evidence")]
        return " ".join(
            sentence
            for sentence in (self._evidence_merge_detail(named), self._tip_merge_detail(tips))
            if sentence
        )

    @staticmethod
    def _conflict_opening(entries: List[Dict[str, Any]]) -> str:
        paths: List[str] = []
        target = ""
        for entry in entries:
            target = target or str(entry.get("target_branch") or "")
            paths.extend(str(path) for path in entry.get("paths", []))
        listed = ", ".join(sorted(set(paths))[:10])
        return (
            f"This task's work does not merge cleanly into {target or 'the main branch'}: {listed}."
        )

    def _tip_merge_detail(self, entries: List[Dict[str, Any]]) -> str:
        """The branch-tip route, whose wording is deliberately the one F155 was reported against.

        It is right *here*: where the target is the task's own branch tip, the commit judged is
        whatever the branch then points at, so resolving on the branch and approving again is
        exactly what clears it. Do not "fix" this into agreement with the sentence above — the two
        say different things because the two routes behave differently, which is the whole finding.
        """
        if not entries:
            return ""
        return (
            f"{self._conflict_opening(entries)} Resolve the conflict on the branch, then approve — "
            "approving is what merges it."
        )

    def _evidence_merge_detail(self, entries: List[Dict[str, Any]]) -> str:
        """The evidence route: name the commit, name its branch, and state a remedy that works.

        Every optional piece is guarded on its own (design D4). The producer always writes a
        `commit_sha` and a `source_branch`, but this body is also built by hand in fixtures, and a
        composition that assumes its producer is how the important half gets silently dropped.
        """
        if not entries:
            return ""
        parts = [self._conflict_opening(entries)]

        judged: List[str] = []
        for entry in entries:
            commit = str(entry.get("commit_sha") or "")[:12]
            branch = str(entry.get("source_branch") or "")
            if not commit and not branch:
                # Nothing knowable about this one. Say nothing rather than print "a commit", which
                # is a clause that costs the reader a sentence and tells them nothing (design D4).
                continue
            piece = commit or "an unnamed commit"
            if branch:
                piece += f", recorded on {branch}"
            if entry.get("recorded_by_another_task"):
                piece += f" by {entry.get('recorded_by_task')}"
            if entry.get("commit_left_its_branch") and branch:
                piece += ", and no longer present on that branch"
            judged.append(piece)
        if judged:
            parts.append("The commit judged is " + "; ".join(judged) + ".")

        branches = sorted({str(entry.get("source_branch") or "") for entry in entries} - {""})
        # Named distinctly from the branch the work merges into (design D8). Both are branches and
        # this sentence speaks about both; naming only one makes every clause after it ambiguous,
        # and it resolves the wrong way — towards the main branch, which is the one the reader must
        # *not* act on.
        on_it = branches[0] if len(branches) == 1 else "the branch it was recorded on"

        parts.append(
            f"Resolving the conflict on {on_it} and approving again will not clear this: what "
            f"approval merges is the commit the accepted evidence names, so this same answer comes "
            f"back however many times approval is retried."
        )
        parts.append(
            f"What does clear it is fresh accepted evidence naming the resolved commit — the "
            f"resolved commit on {on_it}, and the evidence recorded from a checkout of {on_it}. "
            f"The branch is read from the repository the recording is done in and is not a value "
            f"anyone supplies, so recording from anywhere else adds a second branch to what "
            f"approval merges instead of replacing this one; it does not take care of itself. The "
            f"fresh evidence need not be about the same requirement."
        )
        if any(entry.get("recorded_by_another_task") for entry in entries):
            # Named, not decided. Whether to ask the other task's holder or the operator is a
            # judgement this refusal is not in a position to make, and inventing a rule for it here
            # would be the guessing this whole change exists to remove (design D7).
            parts.append(
                "That branch is not this task's, so this may not be a remedy this task's holder "
                "can carry out."
            )
        parts.append(f"Then {ACCEPT_OR_GRANT}.")
        return " ".join(parts)

    def _unaccepted_detail(self) -> str:
        """Each waiting piece by name, and both ways out.

        Every piece is listed rather than counted, because a count tells the reader there is
        something to do and not what. Where the piece was recorded by a *different* task serving the
        same requirement, that task is named too: this task's integration is what would merge that
        commit, so without the attribution the reader is shown a fact with no route back to its
        cause.
        """
        if not self.unaccepted:
            return ""
        pieces: List[str] = []
        for entry in self.unaccepted:
            commit = str(entry.get("commit_sha") or "")[:12]
            piece = (
                f"{entry.get('identifier') or 'a requirement'} at {commit or 'an unnamed commit'}"
            )
            if entry.get("recorded_by_another_task"):
                piece += f", recorded by {entry.get('recorded_by_task')}"
            pieces.append(piece)
        return (
            "This task's work has been recorded and nobody has judged it: "
            + "; ".join(pieces)
            + f". Approving now would record that the work is good and merge none of it, because "
            f"only accepted evidence is merged. To land it, {ACCEPT_OR_GRANT}."
        )

    def _unfinished_detail(self) -> str:
        """Name the agent, say the turn is still running, and say the refusal clears itself.

        The remedy is **waiting**, and it has to be said, or an operator told only "refused" goes
        looking for a defect in work that has none (design D4). F155 is the standing warning: a
        refusal naming a remedy the refused party could not take drove a reviewer to
        `git reset --hard` on a branch holding the only copy of an agent's work. So this says what
        clears it, that it clears itself, and that the operator has a second lever if the turn is
        one they no longer want — `POST /agent/{agent}/stop` (`agent_trigger.stop_agent_run`).
        """
        if not self.unfinished:
            return ""
        agent = str(self.unfinished[0].get("agent") or "an agent")
        return (
            f"{agent} is still running the turn that produces this task's work, so what approving "
            f"would merge is not knowable yet — the task's branch still points at the commit the "
            f"turn started from. Nothing is wrong with the work. Approve once the turn has ended: "
            f"this clears itself, with nothing for anyone to do. Stopping the agent's run ends the "
            f"turn too."
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": "gate_unsatisfied",
            "blocking": list(self.blocking),
            "diagnostics": list(self.diagnostics),
            "unmergeable": list(self.unmergeable),
            "unaccepted": list(self.unaccepted),
            "unfinished": list(self.unfinished),
            "reported": list(self.reported),
            "message": self.detail(),
        }


async def _enforced_requirements(
    session: AsyncSession, task: Task
) -> tuple[List[SpecRequirement], Dict[str, str]]:
    """The task's linked requirements whose document is `gate` or `contract` — everything but
    `sketch`, which stays silent apart from the rejected-evidence signal it already carries on the
    task response regardless of rigor."""
    rows = (
        await session.execute(
            select(SpecRequirement, SpecDocument)
            .join(TaskRequirementLink, TaskRequirementLink.requirement_id == SpecRequirement.id)
            .join(SpecDocument, SpecDocument.id == SpecRequirement.document_id)
            .where(TaskRequirementLink.task_id == task.id)
        )
    ).all()
    enforced = [
        requirement
        for requirement, document in rows
        if (document.rigor or spec_rigor.SKETCH) != spec_rigor.SKETCH
    ]
    rigors = {document.id: (document.rigor or spec_rigor.SKETCH) for _, document in rows}
    return enforced, rigors


@dataclass
class _MergeSituation:
    """What a repository-aware check needs, resolved once for all of them.

    The two checks below ask different questions about the same four preconditions, and both are
    silent — never refusing — when any of them fails: no configured main branch, an unresolvable
    workspace, a directory that is not a repository, no branch by the configured name. Each is *a
    reason to not know, never a reason to refuse*, and they have to be the same four rather than two
    lists that can drift, because a refusal that fired where the merge would have been skipped
    anyway would block every task in such a project behind a remedy that changes nothing.

    Resolved once for a second reason found in round 2: `resolve_project_workspace` is not a pure
    read — it writes `project.directory_state` and `project.last_seen_at` — so asking twice per
    approval writes the same fields twice and runs the same two subprocess calls twice.

    `will_merge` is carried here because both checks need it and it is one resolution: the merge
    check tests each commit for conflicts, and the unaccepted check asks only whether the list is
    empty. It was called `accepted` while accepted evidence was the only thing that could ever
    merge; `task_integration.merge_targets` answers the same question for a task on a loop that
    declares its work needs no evidence, whose target is its own branch tip. The name states what
    the list is *for* rather than where it came from, because the two checks only ever cared that
    something would merge.
    """

    root: Path
    main_branch: str
    will_merge: List[Any]


async def _merge_situation(session: AsyncSession, task: Task) -> Optional["_MergeSituation"]:
    """The four preconditions, or `None` where integration could not be attempted at all."""
    from . import project_workspace, task_integration
    from .db.models import Project

    project = await session.get(Project, task.project_id)
    if project is None or not project.main_branch:
        return None

    try:
        workspace = await project_workspace.resolve_project_workspace(session, task.project_id)
    except Exception:
        # An unreachable workspace is a reason to not know, never a reason to refuse.
        return None

    root = workspace.root
    if not task_integration.is_repository(root):
        return None
    if not task_integration.branch_exists(root, project.main_branch):
        return None

    return _MergeSituation(
        root=root,
        main_branch=project.main_branch,
        will_merge=await task_integration.merge_targets(session, task, root),
    )


async def _check_mergeable(
    session: AsyncSession, task: Task, refusal: GateRefusal, situation: _MergeSituation
) -> None:
    """Add a refusal where the task's work would not merge into the project's main branch.

    Deliberately **not** conditional on rigor. Rigor is a claim about how well the work must be
    proven; this is a claim about whether it can go where approval puts it. A conflicting branch
    approved at `sketch` would record an approval that silently integrates nothing.

    Approval must never be blocked by the *absence* of an integration, only by one that would fail —
    so a task with nothing to merge produces nothing here, and `_merge_situation` has already
    returned `None` for every project where the question could not be asked.
    """
    from . import task_integration

    for target in situation.will_merge:
        paths = task_integration.would_conflict(
            situation.root, target.commit_sha, situation.main_branch
        )
        if not paths:
            continue
        refusal.unmergeable.append(
            {
                "commit_sha": target.commit_sha,
                "source_branch": target.branch,
                "target_branch": situation.main_branch,
                "paths": paths,
                # Which of `merge_targets`' two routes produced this commit (design D1).
                # `integration_targets` names a commit accepted evidence points at; the branch-tip
                # route names whatever the task's branch currently points at, and carries no
                # evidence row at all. The remedy differs between them — resolving on the branch
                # works on one and does nothing on the other — so the provenance is carried per
                # *target*, not per project. A project-level flag would say "approvals here are
                # governed by evidence", which is one inference away from what the sentence
                # asserts, and one inference is what produced F155.
                "named_by_evidence": bool(target.evidence_id),
                "evidence_id": target.evidence_id,
                # A requirement may be served by more than one task, so `_targets`' join through
                # `TaskRequirementLink` puts another task's footprint into this task's targets — and
                # this task's approval is what would merge it. Under per-task isolation the reader
                # has no checkout of that branch, so a remedy phrased as though it were theirs
                # cannot be followed (design D7). The same two keys `_check_unaccepted` carries,
                # from data already on the `Target`: no new query.
                "recorded_by_task": target.task_id,
                "recorded_by_another_task": bool(target.task_id and target.task_id != task.id),
                # `False` only — `None` says the branch does not resolve, which is a reason to say
                # nothing rather than to claim the commit has left it (design D3).
                "commit_left_its_branch": _left_its_branch(
                    situation.root, target.commit_sha, target.branch
                ),
            }
        )


def _left_its_branch(root: Path, commit_sha: str, branch: Optional[str]) -> bool:
    """Whether *commit_sha* is knowably absent from *branch*.

    Reached only on a path that has already run `merge-tree --write-tree` and is already refusing,
    so one `merge-base --is-ancestor` is not a cost worth avoiding. It fires only on the evidence
    route in practice: a branch-tip target's commit *is* that branch's tip by construction.

    The state it reports is the one the drive reached by rewriting the branch — the reasonable
    response to a remedy that appeared not to work — and it is the state in which a reader comparing
    the refusal against `git log` finds the two disagree with no way to tell which is stale.
    """
    from . import requirement_evidence

    if not commit_sha or not branch:
        return False
    return requirement_evidence.is_reachable_from(root, commit_sha, branch) is False


async def _check_unaccepted(
    session: AsyncSession, task: Task, refusal: GateRefusal, situation: _MergeSituation
) -> None:
    """Refuse where a commit has been recorded, nobody has judged it, and nothing else would merge.

    Rigor-independent for the same reason `_check_mergeable` is, and the reason is sharper here: the
    default rigor is `sketch`, `_enforced_requirements` filters `sketch` out entirely, and anything
    behind that filter is absent from a default project — which is exactly how this defect survived.

    **The mixed case is allowed, not refused.** Where accepted evidence already names a commit,
    integration will merge it and approval keeps its meaning; blocking there would hold up work that
    is genuinely ready because a second piece is still in review. The waiting rows are reported on
    the transition instead, and accepting them afterwards merges them
    (`task_integration.integrate_what_was_waiting_for_this_evidence`).
    """
    from . import task_integration

    awaiting = await task_integration.awaiting_targets(session, task)
    if not awaiting:
        return

    identifiers = await _identifiers_for(session, [row.requirement_id for row in awaiting])
    entries = [
        {
            "kind": REPORT_AWAITING_EVIDENCE,
            "evidence_id": target.evidence_id,
            "requirement_id": target.requirement_id,
            "identifier": identifiers.get(target.requirement_id or "", ""),
            "commit_sha": target.commit_sha,
            "source_branch": target.branch,
            "target_branch": situation.main_branch,
            "recorded_by_task": target.task_id,
            # A requirement may be served by more than one task, and this task's integration is what
            # would merge that other task's commit — so the refusal has to say whose it is.
            "recorded_by_another_task": bool(target.task_id and target.task_id != task.id),
            "remedy": ACCEPT_OR_GRANT,
        }
        for target in awaiting
    ]

    # "Something else would merge", which is exactly the right reading for a branch-tip target as
    # well as an accepted-evidence one — the mixed case is about whether approval still means
    # something, not about where the commit came from. That is why no second rule is needed for the
    # evidence-free route (design D8): a task whose merge its branch tip governs and which happens
    # to carry awaiting evidence gets the advisory, not the refusal, because its work does land.
    if situation.will_merge:
        refusal.advisory.extend(entries)
        return
    refusal.unaccepted.extend(entries)


async def _check_live_turn(
    session: AsyncSession, task: Task, refusal: GateRefusal, *, acting_run_id: Optional[str]
) -> None:
    """Refuse while a turn bound to this task is still running (F162).

    **Deliberately not nested under `_merge_situation`**, unlike the two checks above it, and that
    is a departure from a principle this module states in words. `_MergeSituation`'s docstring says
    of its four preconditions that each is *"a reason to not know, never a reason to refuse ...
    because a refusal that fired where the merge would have been skipped anyway would block every
    task in such a project behind a remedy that changes nothing"* (`:230-238`). Placing this check
    outside that block makes it fire in exactly those projects. Three reasons it is right anyway:

    1. **It is not one of the four.** That rule binds checks asking *what would merge*. This asks
       whether the work exists yet, which is answerable in a directory that is not a repository.
    2. **The remedy is not "a remedy that changes nothing".** The clause exists to prevent a
       refusal whose stated fix is unavailable; this one clears itself when the turn ends, without
       anybody doing anything.
    3. **`approved` is a judgement about work, not only an instruction to merge.** Where nothing
       can merge, approving mid-turn still records that unfinished work is good — a statement as
       false in a non-repository project as in a repository one.

    Rigor-independent for the reason `_check_mergeable` is, and the reason is sharper here: the
    default rigor is `sketch`, `_enforced_requirements` filters `sketch` out entirely, and the
    population this defect was measured on is a documentless loop, which has no requirements at all.

    `task-lifecycle-governance:720` — *"An integration that cannot proceed does not block
    approval"* — reads at first like a prohibition on this. It is not: `evaluate`'s
    enforced-requirements walk below is already unconditional on `situation`, so `blocking` and
    `diagnostics` have refused approval in unresolvable projects since the gate shipped. That
    requirement governs *integration* as a blocker of approval, and its scenarios speak about their
    own cause.
    """
    live = await run_liveness.live_turn_for_task(session, task, acting_run_id=acting_run_id)
    if live is None:
        return
    refusal.unfinished.append({"agent": live.agent, "run_id": live.run_id})


async def _identifiers_for(session: AsyncSession, requirement_ids: List[Any]) -> Dict[str, str]:
    """`{spec_requirements.id: identifier}` for the rows a sentence has to name.

    Resolved here rather than in `task_integration` (design D5, round 3): the identifier is a field
    only the sentence uses, and reaching it from the target query would add a join to the *merge*
    path for prose. This module already imports `SpecRequirement`.
    """
    wanted = [requirement_id for requirement_id in requirement_ids if requirement_id]
    if not wanted:
        return {}
    rows = (
        (await session.execute(select(SpecRequirement).where(SpecRequirement.id.in_(wanted))))
        .scalars()
        .all()
    )
    return {row.id: row.identifier for row in rows}


async def evaluate(
    session: AsyncSession, task: Task, *, acting_run_id: Optional[str] = None
) -> tuple[GateRefusal, str]:
    """`(refusal, policy_digest)` for moving this task to `approved`.

    A task linked to nothing is unaffected, and so is one whose documents are all
    sketches — the default blocks nothing, and it has to, or the change would
    arrive as a barrier nobody asked for.

    *acting_run_id* is the run performing the transition, `None` for the operator. It is excluded
    from the liveness check below: **a turn is never blocked by itself** (design D10). Widening the
    signature keeps no second surface in step — `task_transition_service.py:555` is the only caller,
    checked rather than assumed.
    """
    refusal = GateRefusal()
    # Both repository-aware checks, and both **above** the early return two statements down. That
    # return fires whenever no linked document is above `sketch`, which is every default project —
    # a check placed after it would be dead exactly where the defect it fixes lives.
    situation = await _merge_situation(session, task)
    if situation is not None:
        await _check_mergeable(session, task, refusal, situation)
        await _check_unaccepted(session, task, refusal, situation)

    # Beside that block rather than inside it, and above the early return for the same reason both
    # of the above are. Liveness is not a question about the repository — see `_check_live_turn`,
    # which argues the departure rather than leaving it to be re-derived.
    await _check_live_turn(session, task, refusal, acting_run_id=acting_run_id)

    enforced, rigors = await _enforced_requirements(session, task)
    if not enforced:
        return refusal, ""

    by_document: Dict[str, List[SpecRequirement]] = {}
    for requirement in enforced:
        by_document.setdefault(requirement.document_id, []).append(requirement)

    wanted = {requirement.id for requirement in enforced}
    policy: List[Dict[str, Any]] = []

    for document_id in by_document:
        rigor = rigors.get(document_id, spec_rigor.SKETCH)
        gates = rigor == spec_rigor.GATE
        report = await requirement_coverage.requirement_coverage(
            session, task.project_id, document_id=document_id, include_retired=True
        )
        for entry in report.requirements:
            if entry.requirement_id not in wanted:
                continue
            policy.append(
                {
                    "identifier": entry.identifier,
                    "state": entry.state,
                    "integration": entry.integration,
                    "rigor": rigor,
                }
            )
            if entry.state != SATISFIED:
                unmet = {
                    "identifier": entry.identifier,
                    "requirement_id": entry.requirement_id,
                    "state": entry.state,
                    "remedy": REMEDY.get(entry.state, "it is not verified"),
                }
                # `gate` refuses on it; `contract` reports it and lets the transition through — the
                # entire distinction between the two rigors lives in which list an entry lands in.
                if gates:
                    refusal.blocking.append(unmet)
                else:
                    # Stamped only on the reported copy: `reported` and `advisory` are carried out
                    # of the transition on one attribute, so an entry has to say which kind it is.
                    refusal.reported.append({**unmet, "kind": REPORT_REQUIREMENT})
        for entry in report.diagnostics:
            if entry.requirement_id not in wanted:
                continue
            diagnostic = {
                "identifier": entry.identifier,
                "requirement_id": entry.requirement_id,
                "problem": entry.problem,
            }
            if gates:
                # Broken, not unverified. A gate refuses on it separately, because "this requirement
                # is unverified" would send someone to record evidence for something that cannot
                # hold any.
                refusal.diagnostics.append(diagnostic)
            else:
                refusal.reported.append(
                    {
                        "kind": REPORT_REQUIREMENT,
                        "identifier": entry.identifier or "",
                        "requirement_id": entry.requirement_id,
                        "state": "invalid",
                        "remedy": entry.problem,
                    }
                )
            policy.append(
                {
                    "identifier": entry.identifier,
                    "state": "invalid",
                    "integration": "not_applicable",
                    "rigor": rigor,
                }
            )

    return refusal, spec_rigor.policy_digest(policy)
