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

import asyncio
import logging
import subprocess
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
#: F706: `in_progress` because every accepted piece says `covers: partial`, not for want of evidence.
REMEDY_PARTIAL_ONLY = (
    "its accepted evidence covers only part of it (partial evidence only) — record evidence that "
    "demonstrates all of it, with covers: full, and have it accepted"
)

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
    requirement_coverage.AMENDMENT_UNREVIEWED: (
        "a tester changed or removed one of its criteria, or reported it cannot be satisfied, and "
        "the operator has not reviewed that yet — the operator reviews the document's amendments"
    ),
    requirement_coverage.DRIFTING: (
        "the implementation changed after it was verified — the operator answers the drift "
        "candidate on the document, saying whether the specification or the implementation was "
        "wrong; an agent cannot answer it, so ask"
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


#: The conflict refusal's last sentence (F504). Two reviewers in a row met the refusal, retried, and
#: ended with the task still under review, so its author was never briefed to resolve anything.
REVIEWER_SENDS_BACK = (
    "If you are reviewing this task, resolving the conflict is its author's work, not yours: move "
    "the task to revision_needed with notes naming the conflict."
)

#: F681: commits on the task's branch that nothing approval merges holds. Recording evidence from the
#: task's checkout is the author's move; a reviewer's is to send it back, the operator's to ask.
REVIEWER_SENDS_BACK_UNLANDED = (
    "If you are reviewing this task, recording that evidence is its author's work, not yours: move "
    "the task to revision_needed with notes naming the commits."
)
OPERATOR_ON_UNLANDED = (
    "Ask the task's author to record it, accept it, and approve again; or send the task back "
    "(revision_needed) naming the commits."
)

#: A failing check is the author's to fix; a reviewer who meets it sends the work back
#: (`approval-runs-the-projects-checks` D6, as F504 and F497 did for the other two refusals).
REVIEWER_SENDS_BACK_CHECKS = (
    "If you are reviewing this task, fixing what the checks found is its author's work, not yours: "
    "move the task to revision_needed with notes quoting the failing output."
)

#: F731 (6): the same moment said to the operator, who lands rather than reviews.
OPERATOR_ON_FAILING_CHECKS = (
    "Send the task back to its author (revision_needed) with the failing output, or land it "
    "anyway with a reason if the failure is acceptable."
)

#: How much of a failing check's output a refusal quotes. Agents read only the message.
CHECK_TAIL_IN_MESSAGE = 1500
NEWLINE = chr(10)

#: K: what a `blocking` entry says of a requirement whose only current evidence a send-back held.
#: Not a coverage state (coverage reads it `in_progress`, reason `HELD_ONLY`); named here so the
#: refusal says what happened rather than "no evidence".
HELD = "held"
REMEDY_HELD = (
    "its evidence was held when the task was sent back, and a held piece is not accepted -- the "
    "author records it again at the new commit, for the next verdict to judge"
)
REVIEWER_SENDS_BACK_HELD = (
    "If you are reviewing this task, recording held evidence again is its author's work, not "
    "yours: move the task to revision_needed with notes naming the requirement."
)

#: The rejected refusal's remedy is the author's; a reviewer who meets it has its own move (F497).
REVIEWER_SENDS_BACK_REJECTED = (
    "If you are reviewing this task, replacing rejected evidence is its author's work, not yours: "
    "move the task to revision_needed with notes naming the rejected requirement."
)


@dataclass
class GateRefusal:
    """Why the gate refused, in a shape a surface can render without parsing prose."""

    blocking: List[Dict[str, str]] = field(default_factory=list)
    # F731 (6): who reads the refusal. The checks sentences end on what the reader does next, and a
    # reviewer's next step (send it back) is not the operator's (send it back or land anyway).
    for_operator: bool = False
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
    # The project's checks have not passed on the work approval would merge
    # (`approval-runs-the-projects-checks`). A sixth kind of claim: "this merges and breaks the
    # project", or "whether it does is not known yet". One entry, carrying the run's state.
    checks: List[Dict[str, Any]] = field(default_factory=list)
    # F681: the task's own branch holds commits that are on neither main nor inside anything approval
    # would merge. A seventh kind of claim: "approving records this work as good and lands none of
    # it". One entry, naming the branch and the commits.
    unlanded: List[Dict[str, Any]] = field(default_factory=list)
    # Accepted evidence this task recorded for a requirement it is not linked to, naming a commit
    # that is among the `unlanded` ones: approval merges only what a linked requirement's evidence
    # names, so the remedy is the link, not new evidence (`every-task-can-always-be-moved-on` FR-11).
    unlinked: List[Dict[str, Any]] = field(default_factory=list)
    # Set when the operator's stated reason cleared a failed or errored check result; the caller
    # records the reason on the transition.
    checks_overridden: bool = False
    # Set where every failure of the checks is provably not the task's -- the same test ids fail on
    # main too, or passed when rerun on their own -- and the project lets the Hub override them
    # (`a-red-main-does-not-hold-the-night`, D3): the approval lands, and the caller records the
    # Hub's override on the transition. Never a refusal: absent from `refuses`.
    automatic_override: Optional[Dict[str, Any]] = None
    # F695: an approved prerequisite's commit the task's branch does not contain -- its merge
    # conflicted and was left for the author. A seventh kind of claim: "this is missing work it
    # was built on". See `_check_prerequisites_merged`.
    unmerged_prerequisites: List[Dict[str, Any]] = field(default_factory=list)
    # F865: git could not be read in a project the Hub has worked in through git, so whether the
    # work merges is *unknown* -- an eighth kind of claim, and not "not checked, approve". One
    # entry, carrying git's own words.
    git_unreadable: List[Dict[str, str]] = field(default_factory=list)
    # What approval would merge, as the gate resolved it (`task_integration.Target`s), or `None`
    # where the question could not be asked (no main branch, no repository). Not a refusal: the
    # approval freezes these on its landing (`approved-work-merges-in-batches`, D3).
    will_merge: Optional[List[Any]] = None
    # Whether the task's per-task check run failed with a failure of its own on these targets and
    # the operator overrode it: that task lands alone, unchecked (`approved-work-merges-in-batches`,
    # D2).
    overrode_own_failure: bool = False

    @property
    def refuses(self) -> bool:
        return bool(
            self.blocking
            or self.diagnostics
            or self.unmergeable
            or self.unaccepted
            or self.unlanded
            or self.unfinished
            or self.checks
            or self.unmerged_prerequisites
            or self.git_unreadable
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
                self._unlinked_detail(),
                self._unlanded_detail(),
                self._unfinished_detail(),
                self._checks_detail(),
                self._prerequisites_detail(),
                self._git_unreadable_detail(),
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
        rejected = any(entry["state"] == requirement_coverage.REJECTED for entry in self.blocking)
        held = any(entry["state"] == HELD for entry in self.blocking)
        # F701: lowering the rigor relieves only what a gate enforces. A rejection blocks at every
        # rigor (D2), `sketch` included, so where every entry is a rejection the offer cannot work.
        # So does held evidence (K).
        relievable = self.diagnostics or any(
            entry["state"] not in (requirement_coverage.REJECTED, HELD) for entry in self.blocking
        )
        if relievable:
            sentence = (
                "This task serves requirements a gate is enforcing, and they are not verified: "
                + "; ".join(parts)
                + ". Satisfy them, or lower the document's rigor — which is recorded"
                + (
                    ", though a rejected requirement blocks approval at every rigor."
                    if rejected
                    else ", though held evidence blocks approval at every rigor." if held else "."
                )
            )
        elif not held:
            sentence = (
                "This task serves requirements that were rejected: "
                + "; ".join(parts)
                + ". A rejected requirement blocks approval at every rigor, so lowering the "
                "document's rigor does not clear it."
            )
        else:
            sentence = (
                "This task serves requirements whose evidence was rejected or held: "
                + "; ".join(parts)
                + ". Both block approval at every rigor, so lowering the document's rigor does "
                "not clear them."
            )
        if rejected:
            sentence += " " + REVIEWER_SENDS_BACK_REJECTED
        if held:
            sentence += " " + REVIEWER_SENDS_BACK_HELD
        return sentence

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
            for sentence in (
                self._evidence_merge_detail(named),
                self._tip_merge_detail(tips),
                REVIEWER_SENDS_BACK,
            )
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

    def _unlinked_detail(self) -> str:
        """Each unserved requirement by name, and the link that clears it."""
        if not self.unlinked:
            return ""
        pieces = [
            f"{entry.get('identifier') or 'a requirement'} at "
            f"{str(entry.get('commit_sha') or '')[:12] or 'an unnamed commit'}"
            for entry in self.unlinked
        ]
        return (
            "This task has accepted evidence that approving would not merge, because the task is "
            "not linked to the requirement it demonstrates: "
            + "; ".join(pieces)
            + ". Link the requirement to the task and approve again."
        )

    def _unlanded_detail(self) -> str:
        """Name the branch and its commits, say why approving would leave them, and what clears it.

        The remedy is evidence recorded from a checkout of the task's branch: a footprint's branch
        and commit are read from the repository the recording is done in, so evidence recorded
        anywhere else names a commit that does not hold this work (F681's sweep: task-less evidence
        at main's tip, approved, merged nothing).
        """
        if not self.unlanded:
            return ""
        entry = self.unlanded[0]
        # F772: where every one of these commits is named by a piece awaiting judgement, the author
        # has recorded exactly what is asked for here, and accepting it (the `unaccepted` sentence)
        # is the whole remedy. Asking them to record it again sends them after what exists.
        awaiting = {
            str(piece.get("commit_sha") or "") for piece in [*self.unaccepted, *self.unlinked]
        } - {""}
        commits = [str(sha) for sha in entry.get("commits") or [] if sha]
        if commits and all(sha in awaiting for sha in commits):
            return ""
        branch = str(entry.get("branch") or "the task's branch")
        target = str(entry.get("target_branch") or "the main branch")
        shas = [str(sha)[:12] for sha in entry.get("commits") or [] if sha]
        listed = ", ".join(shas[:10]) + (f" and {len(shas) - 10} more" if len(shas) > 10 else "")
        one = len(shas) == 1
        return (
            f"This task's branch {branch} holds work approving would not merge: "
            f"{'commit' if one else 'commits'} {listed} {'is' if one else 'are'} on neither "
            f"{target} nor inside any commit the accepted evidence names, so approving would record "
            f"the work as good and land none of it. What clears it is evidence recorded from the "
            f"task's own checkout (a checkout of {branch}), so it names the task's commit, and then "
            f"accepted. "
            + (OPERATOR_ON_UNLANDED if self.for_operator else REVIEWER_SENDS_BACK_UNLANDED)
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

    def _git_unreadable_detail(self) -> str:
        """Say git could not be read, quote it, and say a moment later it clears itself (F865)."""
        if not self.git_unreadable:
            return ""
        error = str(self.git_unreadable[0].get("error") or "git did not answer")
        return (
            "git could not be read in the project's folder, so whether this work merges is "
            f"unknown ({error}). Nothing is wrong with the work: try again in a moment."
        )

    def _checks_detail(self) -> str:
        """What the checks said, quoting the failing output, and who acts on it."""
        if not self.checks:
            return ""
        entry = self.checks[0]
        state = entry.get("state")
        if state in ("running", "started") and entry.get("previous_error"):
            # F613: a retry of an errored run is said with its error, so a run that keeps erroring
            # (a merge conflict, every time) is not read as "nothing is wrong" on each Land press.
            return (
                f"This task's checks could not run last time: {entry['previous_error']}. "
                "Approving started them again; approval can be retried when they finish, and if "
                "they error the same way, the cause above needs fixing first."
            )
        if state in ("running", "started"):
            return (
                "This task's checks are still running on the work approval would merge. Nothing is "
                "wrong yet; approval can be retried when they finish."
            )
        if state == "not_run":
            return (
                "This task's checks have not run on the work approval would merge yet; they start "
                "when its approval is requested."
            )
        if state == "error":
            return (
                f"This task's checks could not run: {entry.get('error') or 'an unknown error'}. "
                "Approval is refused until they run and pass."
            )
        parts = []
        for failure in entry.get("failing") or []:
            how = (
                "ran past its timeout"
                if failure.get("timed_out")
                else f"exited {failure.get('exit_code')}"
            )
            if failure.get("preexisting"):
                how += " (and fails on main too)"
            tail = str(failure.get("output_tail") or "")[-CHECK_TAIL_IN_MESSAGE:].strip()
            parts.append(f"`{failure.get('name')}` {how}:" + NEWLINE + tail)
        if state == "preexisting":
            # F605 (fix-D13): no send-back line; the failure is main's, and the hold is the operator's.
            return (
                "This task's checks fail, and they fail on main too, so the failure is not this "
                "task's work. "
                + (NEWLINE * 2).join(parts)
                + NEWLINE * 2
                + (
                    "Land it with an override reason, or fix main first."
                    if self.for_operator
                    else "Approval waits on the operator: land it with an override reason, or fix "
                    "main first. A reviewer should not send it back for this."
                )
            )
        return (
            "This task's checks failed on the work approval would merge, so approving would land "
            "work that breaks the project. "
            + (NEWLINE * 2).join(parts)
            + NEWLINE * 2
            + (OPERATOR_ON_FAILING_CHECKS if self.for_operator else REVIEWER_SENDS_BACK_CHECKS)
        )

    def _prerequisites_detail(self) -> str:
        """Each missing prerequisite commit by task and sha, and who merges it (F695)."""
        if not self.unmerged_prerequisites:
            return ""
        pieces = []
        commands = []
        for entry in self.unmerged_prerequisites:
            sha = str(entry.get("commit_sha") or "")
            piece = f"{entry.get('prerequisite_task')}'s commit {sha[:12]}"
            if entry.get("paths"):
                piece += " (conflicting in " + ", ".join(entry["paths"][:10]) + ")"
            pieces.append(piece)
            commands.append(f"`git merge --no-ff {sha}`")
        return (
            "This task's branch does not contain the approved work it depends on: "
            + "; ".join(pieces)
            + ". Merging it conflicted, so it was left for the task's author, whose turns are told "
            "to run "
            + " and ".join(commands)
            + " in the task's checkout, resolve the conflicts and commit; approve once that merge "
            "is on the branch. If you are reviewing this task, the merge is its author's work, not "
            "yours: move the task to revision_needed with notes naming the commit."
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": "gate_unsatisfied",
            "checks": list(self.checks),
            "blocking": list(self.blocking),
            "diagnostics": list(self.diagnostics),
            "unmergeable": list(self.unmergeable),
            "unaccepted": list(self.unaccepted),
            "unlanded": list(self.unlanded),
            "unlinked": list(self.unlinked),
            "unfinished": list(self.unfinished),
            "reported": list(self.reported),
            "unmerged_prerequisites": list(self.unmerged_prerequisites),
            "git_unreadable": list(self.git_unreadable),
            "message": self.detail(),
        }


async def _linked_requirements(session: AsyncSession, task: Task) -> List[Any]:
    """Every `(requirement, document)` pair the task links, at every rigor including `sketch` — the
    population D2's rejected check reads, before `_enforced_requirements` below filters `sketch` out
    for the unmet/diagnostic loop that follows it."""
    return (
        await session.execute(
            select(SpecRequirement, SpecDocument)
            .join(TaskRequirementLink, TaskRequirementLink.requirement_id == SpecRequirement.id)
            .join(SpecDocument, SpecDocument.id == SpecRequirement.document_id)
            .where(TaskRequirementLink.task_id == task.id)
        )
    ).all()


async def _enforced_requirements(
    session: AsyncSession, task: Task, *, rows: Optional[List[Any]] = None
) -> tuple[List[SpecRequirement], Dict[str, str]]:
    """The task's linked requirements whose document is `gate` or `contract` — everything but
    `sketch`, which stays silent apart from the rejected-evidence signal it already carries on the
    task response regardless of rigor (and, since D2, apart from a rejected requirement, which now
    blocks at `sketch` too — through the separate step in `evaluate`, not through this filter).

    *rows* lets `evaluate` pass the join it already ran for D2's step, so a task linking several
    requirements does not run the same query twice in one call.
    """
    if rows is None:
        rows = await _linked_requirements(session, task)
    # A task in a build is governed by its level's rule, not its documents' rigor
    # (`a-build-has-a-driver-a-level-and-its-people`, D1): Fast as `sketch`, Reviewed as `contract`,
    # Gated as `gate`. A task outside any build keeps its documents' rigor, exactly as before.
    from .builds import rigor_for_level

    by_level = rigor_for_level(task.level) if task.build_id else None

    def rule(document) -> str:
        return by_level or document.rigor or spec_rigor.SKETCH

    enforced = [
        requirement for requirement, document in rows if rule(document) != spec_rigor.SKETCH
    ]
    rigors = {document.id: rule(document) for _, document in rows}
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
    read — it can write `project.directory_state` (no longer `last_seen_at`, F349) — so asking twice
    per approval runs the same resolution and the same two subprocess calls twice.

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


async def merge_situation(session: AsyncSession, task: Task) -> Optional["_MergeSituation"]:
    """The four preconditions, or `None` where integration could not be attempted at all.

    `None` does not say why. `situation_or_fault` does, for the one caller (the gate) that must
    tell "the question does not apply here" from "git could not be asked" (F865).

    Public because the approval preview asks the same question, through this, before the operator
    presses Approve (`the-approval-preview-asks-the-gates-merge-question`, D1). Its git calls
    raise rather than answer `None`: here "unknown" must not read as "not checked -- approve"
    (F424's repair belongs in the gate's checks, which refuse)."""
    return (await situation_or_fault(session, task))[0]


async def situation_or_fault(
    session: AsyncSession, task: Task
) -> tuple[Optional["_MergeSituation"], Optional[str]]:
    """`(situation, fault)`: the situation, or why there is none.

    *fault* is git's own words and is set only where the Hub holds proof the project is a
    repository (`task_integration.repository_proof`) and git failed anyway: a `.git` moved aside, a
    lock, a git off the PATH for a moment. That is *unknown*, which the gate must not read as "not
    checked -- approve" (F865: Land approved a task whose commit conflicts with main, and every
    retry then failed on the conflict). A folder that never was a repository still gives
    `(None, None)`, and approves unchanged.
    """
    from . import project_workspace, task_integration
    from .db.models import Project

    project = await session.get(Project, task.project_id)
    if project is None or not project.main_branch:
        return None, None

    try:
        workspace = await project_workspace.resolve_project_workspace(session, task.project_id)
    except Exception:
        # An unreachable workspace is a reason to not know, never a reason to refuse.
        return None, None

    root = workspace.root
    # Off the event loop: a hung git must delay the request that asked, not the Hub (the four git
    # call sites `approval_held_for_operator` reaches). None of them touches the session.
    fault = await asyncio.to_thread(task_integration.repository_fault, root)
    if fault is not None:
        if await task_integration.repository_proof(session, task, root):
            return None, fault
        return None, None
    if not await asyncio.to_thread(task_integration.branch_exists, root, project.main_branch):
        return None, None

    return (
        _MergeSituation(
            root=root,
            main_branch=project.main_branch,
            will_merge=await task_integration.merge_targets(session, task, root),
        ),
        None,
    )


async def _check_mergeable(
    session: AsyncSession, task: Task, refusal: GateRefusal, situation: _MergeSituation
) -> None:
    """Add a refusal where the task's work would not merge into the project's main branch.

    Deliberately **not** conditional on rigor. Rigor is a claim about how well the work must be
    proven; this is a claim about whether it can go where approval puts it. A conflicting branch
    approved at `sketch` would record an approval that silently integrates nothing.

    Approval must never be blocked by the *absence* of an integration, only by one that would fail —
    so a task with nothing to merge produces nothing here, and `merge_situation` has already
    returned `None` for every project where the question could not be asked.
    """
    from . import task_integration

    for target in situation.will_merge:
        paths = await asyncio.to_thread(
            task_integration.would_conflict,
            situation.root,
            target.commit_sha,
            situation.main_branch,
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
    # "Would merge" means a commit that is not in the main branch already (F499): `_targets` reaches
    # another task's accepted commit through a shared requirement, and once that task's approval
    # has merged it, counting it here let this approval merge nothing while its own work waited.
    if await asyncio.to_thread(_merges_something_new, situation):
        refusal.advisory.extend(entries)
        return
    refusal.unaccepted.extend(entries)


def _merges_something_new(situation: _MergeSituation) -> bool:
    """Whether any commit approval would merge is not already in the main branch.

    An unanswerable probe counts as new, which is how this read before F499: an unknown is not a
    reason to refuse.
    """
    from . import requirement_evidence

    return any(
        requirement_evidence.is_reachable_from(
            situation.root, target.commit_sha, situation.main_branch
        )
        is not True
        for target in situation.will_merge
    )


async def _check_unlanded(
    session: AsyncSession, task: Task, refusal: GateRefusal, situation: _MergeSituation
) -> None:
    """Refuse where the task's own branch holds commits approval would leave behind (F681).

    Rigor-independent, as `_check_mergeable` is: this is not a claim that the work is unproven but
    that approving would not land it. Silent where the task has no branch, where every commit on it
    is already in main or inside a merge target (the branch-tip route's target *is* the tip), and
    where git cannot answer; an unknown is not a reason to refuse.
    """
    from . import task_integration

    branch, commits = await asyncio.to_thread(
        task_integration.task_commits_nothing_merges,
        situation.root,
        task.id,
        situation.main_branch,
        [target.commit_sha for target in situation.will_merge],
    )
    if not commits:
        return
    refusal.unlanded.append(
        {"branch": branch, "target_branch": situation.main_branch, "commits": commits}
    )
    await _check_unlinked(session, task, refusal, commits)


async def _check_unlinked(
    session: AsyncSession, task: Task, refusal: GateRefusal, commits: List[str]
) -> None:
    """Name the accepted evidence this task recorded for a requirement it does not serve.

    Asked only once commits are left behind: it is the cause of that, where the evidence naming
    them exists and is accepted but reaches no link. Evidence recorded since
    `_serve_requirement_of_own_document` is linked as it is recorded; this is for what predates it.
    """
    from .db.models import EvidenceFootprint, RequirementEvidence

    rows = (
        await session.execute(
            select(RequirementEvidence, EvidenceFootprint.commit_sha, SpecRequirement.identifier)
            .join(EvidenceFootprint, EvidenceFootprint.evidence_id == RequirementEvidence.id)
            .join(SpecRequirement, SpecRequirement.id == RequirementEvidence.requirement_id)
            .where(
                RequirementEvidence.task_id == task.id,
                RequirementEvidence.review_state == "accepted",
                EvidenceFootprint.kind == "git",
                EvidenceFootprint.commit_sha.in_(commits),
                ~RequirementEvidence.requirement_id.in_(
                    select(TaskRequirementLink.requirement_id).where(
                        TaskRequirementLink.task_id == task.id
                    )
                ),
            )
            .order_by(EvidenceFootprint.observed_at.asc())
        )
    ).all()
    for evidence, commit_sha, identifier in rows:
        refusal.unlinked.append(
            {
                "evidence_id": evidence.id,
                "requirement_id": evidence.requirement_id,
                "identifier": identifier,
                "commit_sha": commit_sha,
                "remedy": f"link {identifier} to the task",
            }
        )


async def _check_prerequisites_merged(
    session: AsyncSession, task: Task, refusal: GateRefusal, situation: _MergeSituation
) -> None:
    """Refuse while an approved prerequisite's commit is not on this task's branch (F695).

    A turn on the task tops its checkout up with that work (`worktrees._catch_up_prerequisites`);
    one whose merge conflicts is left for the author, who is told in the turn's prompt. Until the
    author has merged it the branch is missing work it was built on, and approving would land it
    without. Asked of the branch with the prompt's own function (`worktrees.unmerged_prerequisites`),
    so the two cannot disagree. Silent for a task with no checkout of its own or no branch yet.
    """
    from . import task_integration, task_workspace, worktrees

    approved = await task_workspace.approved_prerequisite_commits(session, task, situation.root)
    if not approved:
        return
    branch = worktrees.task_branch_name(task.id)
    if not await asyncio.to_thread(task_integration.branch_exists, situation.root, branch):
        return
    pending = await asyncio.to_thread(
        worktrees.unmerged_prerequisites, situation.root, approved, branch
    )
    refusal.unmerged_prerequisites.extend(
        {
            "prerequisite_task": entry.prerequisite_id,
            "commit_sha": entry.commit_sha,
            "branch": branch,
            "paths": list(entry.paths),
        }
        for entry in pending
    )


async def _check_live_turn(
    session: AsyncSession, task: Task, refusal: GateRefusal, *, acting_run_id: Optional[str]
) -> None:
    """Refuse while a turn bound to this task is still running (F162).

    **Deliberately not nested under `merge_situation`**, unlike the two checks above it, and that
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


async def _coverage_by_document(
    session: AsyncSession, task: Task, rows: List[Any]
) -> tuple[Dict[str, List[SpecRequirement]], Dict[str, requirement_coverage.CoverageReport]]:
    """The task's linked requirements grouped by document, and each document's coverage report."""
    by_document: Dict[str, List[SpecRequirement]] = {}
    for requirement, document in rows:
        by_document.setdefault(document.id, []).append(requirement)
    reports: Dict[str, requirement_coverage.CoverageReport] = {}
    for document_id in by_document:
        reports[document_id] = await requirement_coverage.requirement_coverage(
            session, task.project_id, document_id=document_id, include_retired=True
        )
    return by_document, reports


def _rejected_entries(
    by_document: Dict[str, List[SpecRequirement]],
    reports: Dict[str, requirement_coverage.CoverageReport],
    *,
    held: bool = False,
) -> List[Any]:
    """The coverage entries of the task's requirements that are `rejected` -- D2's refusal -- or,
    with *held*, whose only current evidence was held by a send-back (K)."""

    def refused(entry) -> bool:
        if held:
            return entry.reason == requirement_coverage.HELD_ONLY
        return entry.state == requirement_coverage.REJECTED

    rejected: List[Any] = []
    for document_id, requirements in by_document.items():
        wanted_ids = {requirement.id for requirement in requirements}
        rejected.extend(
            entry
            for entry in reports[document_id].requirements
            if entry.requirement_id in wanted_ids and refused(entry)
        )
    return rejected


async def rejected_identifiers(session: AsyncSession, task: Task) -> List[str]:
    """The requirements this task serves whose evidence is all rejected: each refuses `approved`
    at every rigor (D2). The review briefing reads this (F497), so it says exactly what
    `evaluate` will refuse."""
    rows = await _linked_requirements(session, task)
    if not rows:
        return []
    entries = _rejected_entries(*await _coverage_by_document(session, task, rows))
    return [entry.identifier or "a requirement" for entry in entries]


async def held_identifiers(session: AsyncSession, task: Task) -> List[str]:
    """The requirements this task serves whose only current evidence a send-back held (K): each
    refuses `approved` at every rigor too, until its author records it again. Beside
    `rejected_identifiers`, so the review briefing names everything `evaluate` will refuse."""
    rows = await _linked_requirements(session, task)
    if not rows:
        return []
    entries = _rejected_entries(*await _coverage_by_document(session, task, rows), held=True)
    return [entry.identifier or "a requirement" for entry in entries]


async def _check_checks(
    session: AsyncSession,
    task: Task,
    refusal: GateRefusal,
    situation: "_MergeSituation",
    *,
    override_checks_reason: Optional[str],
) -> None:
    """The task's own check result on the work approval would merge.

    `approved-work-merges-in-batches` (D2, D6): the landing gate is the batch's one check run on
    main with the queued work merged, so approval no longer waits for a per-task result. A missing,
    running, errored, interrupted or stale result refuses nothing and starts nothing, and a pass on
    any earlier main tip counts. What still refuses is the task's own confirmed failure on these
    same merge targets, whatever main tip it ran on. A failure main shares, or a flake, refuses
    nothing either: the batch applies slice M's rule to it. Reads only; never runs a check.

    The operator's reason over a failed result lands that task alone, unchecked
    (`overrode_own_failure`), as approving over failing checks always has.
    """
    from . import project_checks

    targets = [target.commit_sha for target in situation.will_merge]
    view = await project_checks.view(session, task, situation.root, situation.main_branch, targets)
    if view is None:
        return
    run = view.run
    if view.state == "passed":
        # A pass that holds a flake of a named test still lands, as before; it is recorded as the
        # Hub's override naming the test (`flake-recorded-on-approval`).
        refusal.automatic_override = await automatic_override(session, task, view)
        return
    failed_here = view.state == "failed"
    if not failed_here and run is not None and run.state == "failed" and view.state == "stale":
        # A verdict on these same targets from an earlier main tip still says what the work does.
        tip = await asyncio.to_thread(
            project_checks.main_tip, situation.root, situation.main_branch
        )
        if tip is not None:
            now = await asyncio.to_thread(project_checks.unmerged, situation.root, tip, targets)
            failed_here = bool(now) and list(run.target_shas or []) == list(now)
    if not failed_here or run is None:
        return
    if (override_checks_reason or "").strip():
        refusal.checks_overridden = True  # the operator's typed reason wins over the Hub's
        refusal.overrode_own_failure = True
        return
    if not project_checks.own_failure(run.results):
        # Main's failure or a flake: the Hub's override where M allows it (recorded on the
        # approval, as before); otherwise the batch holds the landing for the operator.
        refusal.automatic_override = await automatic_override(session, task, view)
        return
    results = list(run.results or [])
    failing = [r for r in results if project_checks.failed(r)]
    refusal.checks.append(
        {
            "state": "failed",
            "run_id": run.id,
            "failing": failing,
            "error": "",
            "previous_error": "",
        }
    )


async def automatic_override_allowed(session: AsyncSession, task: Task) -> bool:
    """Whether the Hub may land *task* over failures that are not its own, and file their fix task
    (`a-red-main-does-not-hold-the-night`, FR-5): the project's `checks_auto_override`, on by
    default. **The one place this policy is asked**: slice D adds its per-level rule here
    (`builds.allows_automatic_override(level)`, never at Gated). Never raises."""
    from .builds import allows_automatic_override
    from .db.models import Project

    # A task in a Gated build is never landed over its checks by the Hub: the operator chose Gated
    # to judge every landing (`a-build-has-a-driver-a-level-and-its-people`, D5).
    if task.build_id and not allows_automatic_override(task.level):
        return False
    try:
        project = await session.get(Project, task.project_id)
    except Exception:  # noqa: BLE001 -- no answer is no override
        logger.warning("could not read the override setting of %s", task.project_id, exc_info=True)
        return False
    return project is not None and bool(getattr(project, "checks_auto_override", True))


async def automatic_override(
    session: AsyncSession, task: Task, view: Any
) -> Optional[Dict[str, Any]]:
    """The Hub's override for approving *task* over its checks' *view*, or `None` where there is none
    to make (`a-red-main-does-not-hold-the-night`, D3): every failure and flake must be provably not
    the task's (`project_checks.not_the_tasks`, which excludes, among others, the ids a Hub-filed
    fix task was filed for), and the project must allow it (`automatic_override_allowed`).

    `{"run_id", "main_sha", "failures": [{"check", "test", "kind"}], "fix_tasks": {test: task}}`;
    `override_reason_for` words it for the transition. Reads only."""
    from . import flaky_tests, project_checks
    from .db.models import TaskCheckRun

    run = view.run
    results = view.reused if view.state == "passed" and view.reused is not None else None
    if results is None:
        if run is None:
            return None
        results = list(run.results or [])
    if not await automatic_override_allowed(session, task):
        return None
    found = project_checks.not_the_tasks(
        results, excluded=await flaky_tests.filed_for(session, task)
    )
    if not found:
        return None
    source = run
    if view.reused is not None and view.state == "passed":
        # A pass of the same tree reused from another run: that run found the flake.
        reused_from = next(
            (r.get("reused_from") for r in results if isinstance(r, dict) and r.get("flaky")),
            None,
        )
        source = await session.get(TaskCheckRun, reused_from) if reused_from else run
    by_test = await flaky_tests.fix_tasks_by_test(session, task.project_id, open_only=False)
    return {
        "run_id": source.id if source is not None else None,
        "main_sha": source.main_sha if source is not None else None,
        "failures": found,
        "fix_tasks": {
            entry["test"]: by_test[flaky_tests._key(entry["test"])]
            for entry in found
            if flaky_tests._key(entry["test"]) in by_test
        },
    }


def override_reason_for(decided: Dict[str, Any]) -> str:
    """The `override_reason` the approval transition records for the Hub's override: each check
    and test id and why it is not the task's, the check run, the main commit and the fix task."""
    main = str(decided.get("main_sha") or "")[:12] or "the main branch"
    parts = []
    for entry in decided.get("failures") or []:
        why = (
            f"fails on main at {main} too"
            if entry["kind"] == "fails on main"
            else "passed when rerun on its own"
        )
        parts.append(f"`{entry['check']}` {entry['test']} {why}")
    fixes = sorted(set((decided.get("fix_tasks") or {}).values()))
    fix = f"; fix task {', '.join(fixes)}" if fixes else "; no fix task was filed for them yet"
    return (
        "The Hub approved over failures that were not this task's: "
        + "; ".join(parts)
        + f" (check run {decided.get('run_id')}, main {main}{fix})."
    )


async def evaluate(
    session: AsyncSession,
    task: Task,
    *,
    acting_run_id: Optional[str] = None,
    override_checks_reason: Optional[str] = None,
) -> tuple[GateRefusal, str]:
    """`(refusal, policy_digest)` for moving this task to `approved`.

    A task linked to nothing is unaffected, and so is one whose documents are all
    sketches — the default blocks nothing, and it has to, or the change would
    arrive as a barrier nobody asked for.

    *acting_run_id* is the run performing the transition, `None` for the operator. It is excluded
    from the liveness check below: **a turn is never blocked by itself** (design D10). Widening the
    signature keeps no second surface in step — `task_transition_service.py:555` is the only caller,
    checked rather than assumed.

    *override_checks_reason* is passed only by the operator's approval. No caller starts a check
    run through the gate (`approved-work-merges-in-batches`, D2). See `_check_checks`.
    """
    refusal = GateRefusal()
    # Both repository-aware checks, and both **above** the early return two statements down. That
    # return fires whenever no linked document is above `sketch`, which is every default project —
    # a check placed after it would be dead exactly where the defect it fixes lives.
    situation, fault = await situation_or_fault(session, task)
    if fault is not None:
        refusal.git_unreadable.append({"error": fault})
    if situation is not None:
        refusal.will_merge = list(situation.will_merge)
        await _check_mergeable(session, task, refusal, situation)
        await _check_unaccepted(session, task, refusal, situation)
        await _check_unlanded(session, task, refusal, situation)
        await _check_checks(
            session,
            task,
            refusal,
            situation,
            override_checks_reason=override_checks_reason,
        )
        await _check_prerequisites_merged(session, task, refusal, situation)

    # Beside that block rather than inside it, and above the early return for the same reason both
    # of the above are. Liveness is not a question about the repository — see `_check_live_turn`,
    # which argues the departure rather than leaving it to be re-derived.
    await _check_live_turn(session, task, refusal, acting_run_id=acting_run_id)

    # D2: a rejected requirement blocks approval at every rigor, `sketch` included — above the
    # early return two statements down for the same reason the repository checks are (`:628-630`
    # above): that return fires on every default project, and a check placed after it would be dead
    # exactly where the defect it fixes lives. Reads every linked document, not only the enforced
    # ones, and caches each document's report so the enforced loop below does not ask twice.
    rows = await _linked_requirements(session, task)
    by_all_document, reports_by_document = await _coverage_by_document(session, task, rows)
    rejected_requirement_ids: set = set()
    for entry in _rejected_entries(by_all_document, reports_by_document):
        refusal.blocking.append(
            {
                "identifier": entry.identifier,
                "requirement_id": entry.requirement_id,
                "state": entry.state,
                "remedy": REMEDY[requirement_coverage.REJECTED],
            }
        )
        rejected_requirement_ids.add(entry.requirement_id)
    # K (`each-piece-of-evidence-is-judged-on-its-own`): a requirement whose only current evidence a
    # send-back held is refused at every rigor too. Before K that send-back rejected the piece, and
    # this step refused it; a held piece counts for no more, and needs a new one at the next commit.
    for entry in _rejected_entries(by_all_document, reports_by_document, held=True):
        refusal.blocking.append(
            {
                "identifier": entry.identifier,
                "requirement_id": entry.requirement_id,
                "state": HELD,
                "remedy": REMEDY_HELD,
            }
        )
        rejected_requirement_ids.add(entry.requirement_id)

    if not rows:
        # Nothing governed this transition at all — a null digest is the honest answer, not a gap
        # (D3). A task linking only `sketch` documents still falls through to the loop below: the
        # rejected step above already read their coverage, so recording it here costs nothing.
        return refusal, ""

    _, rigors = await _enforced_requirements(session, task, rows=rows)

    policy: List[Dict[str, Any]] = []

    for document_id, requirements in by_all_document.items():
        rigor = rigors.get(document_id, spec_rigor.SKETCH)
        gates = rigor == spec_rigor.GATE
        # D3: a `sketch` document still contributes to the digest — every requirement the task
        # serves governed the transition, `sketch` included — but it stays silent the way
        # `_enforced_requirements` always has: no `blocking`/`reported`/`diagnostics` entry below
        # the rejected step two blocks up, which already covers `sketch`'s one way of refusing.
        enforces = rigor != spec_rigor.SKETCH
        report = reports_by_document[document_id]
        wanted_ids = {requirement.id for requirement in requirements}
        for entry in report.requirements:
            if entry.requirement_id not in wanted_ids:
                continue
            policy.append(
                {
                    "identifier": entry.identifier,
                    "state": entry.state,
                    "integration": entry.integration,
                    "rigor": rigor,
                }
            )
            if not enforces or entry.requirement_id in rejected_requirement_ids:
                # Already in `blocking` from the step above, or `sketch`'s refusal stops there —
                # the loop's own job is `contract` and `gate`'s unmet-but-not-rejected states, so it
                # must not add a second `blocking` entry here, or a `reported` copy of one
                # `contract` no longer gets to report.
                continue
            if entry.state != SATISFIED:
                unmet = {
                    "identifier": entry.identifier,
                    "requirement_id": entry.requirement_id,
                    "state": entry.state,
                    "remedy": (
                        REMEDY_PARTIAL_ONLY
                        if entry.reason == requirement_coverage.PARTIAL_ONLY
                        else REMEDY.get(entry.state, "it is not verified")
                    ),
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
            if entry.requirement_id not in wanted_ids:
                continue
            policy.append(
                {
                    "identifier": entry.identifier,
                    "state": "invalid",
                    "integration": "not_applicable",
                    "rigor": rigor,
                }
            )
            if not enforces:
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

    return refusal, spec_rigor.policy_digest(policy)


# --------------------------------------------------------------------------------------
# Approval held for the operator (`a-review-no-reviewer-can-approve-goes-to-the-operator`, D1)
# --------------------------------------------------------------------------------------

logger = logging.getLogger(__name__)

EVIDENCE_HOLD_REMEDY = (
    "accept or reject the evidence waiting on it, or grant an agent the decision on evidence"
)
DIAGNOSTIC_HOLD_REMEDY = (
    "a requirement it serves cannot be satisfied as written; correct the document"
)
DRIFT_HOLD_REMEDY = "resolve the drift candidate on a requirement it serves"
#: F605 (fix-D13): a check that fails on main too is nobody's to fix on this task.
PREEXISTING_CHECKS_HOLD_REMEDY = (
    "its checks fail on main too, so the failure is not its own; land it with an override "
    "reason, or fix main first"
)


@dataclass(frozen=True)
class ApprovalHold:
    """A refusal of approval that no reviewer can remove — only the operator can."""

    detail: str  # the gate's own `refusal.detail()`, or the could-not-ask-git sentence
    remedy: str  # the remedy clause for the category that holds it
    refusal: Optional[GateRefusal]  # None only for the could-not-ask-git hold


def _could_not_ask_git(reason: str) -> ApprovalHold:
    return ApprovalHold(
        detail=("the Hub could not ask git whether this task's work would merge: " f"{reason}"),
        remedy=(
            f"the Hub could not ask git whether its work would merge ({reason}); check the "
            "project's repository, then approve it yourself or send it back"
        ),
        refusal=None,
    )


def _operator_only_remedy(refusal: GateRefusal, *, may_accept: bool, task_id: str) -> Optional[str]:
    """The remedy of the first category of *refusal* the candidate cannot remove, else `None`."""
    if refusal.diagnostics:
        return DIAGNOSTIC_HOLD_REMEDY
    for entry in refusal.blocking:
        if entry.get("state") == requirement_coverage.DRIFTING:
            return DRIFT_HOLD_REMEDY
    if any(entry.get("state") == "preexisting" for entry in refusal.checks):
        return PREEXISTING_CHECKS_HOLD_REMEDY
    if may_accept:
        return None
    # The task's own evidence is decided by the verdict on it (vis-D4), so it is never the
    # operator's to hold; a piece another task or an unbound run recorded still is.
    if any(entry.get("recorded_by_task") != task_id for entry in refusal.unaccepted):
        return EVIDENCE_HOLD_REMEDY
    return None


async def approval_held_for_operator(
    session: AsyncSession,
    task: Task,
    *,
    candidate: Optional[str],
    acting_run_id: Optional[str] = None,
) -> Optional[ApprovalHold]:
    """A hold where approval of *task* is refused for a reason only the operator can remove.

    *acting_run_id* is the run whose end is being judged, if any (F458): it is still in the live set
    when its end is evaluated, and counting it would add "still running the turn ... this clears
    itself" to the reason for a turn that has just ended.

    Asks `evaluate`, the function the transition asks, so the two cannot disagree. Read-only, run
    inside a savepoint, and bounded: each git spawn on its path is capped at
    `DIAGNOSTIC_GIT_TIMEOUT_SECONDS` and runs off the event loop. Answers `None` without calling
    `evaluate` where nothing could hold it — no evidence awaiting, no `gate`-rigor document.

    Three answers to a raise: git could not be asked (`TimeoutExpired`, `OSError`) is held for the
    operator whatever the candidate is granted; anything else is logged at warning and is "not
    held", so no caller fails because a diagnostic could not be computed.
    """
    from . import project_checks, requirement_evidence, task_integration
    from .spec_lifecycle import Actor

    try:
        awaiting = await task_integration.awaiting_targets(session, task)
        _, rigors = await _enforced_requirements(session, task)
        if (
            not awaiting
            and spec_rigor.GATE not in rigors.values()
            # F605: a check failing on main too holds approval for the operator.
            and not await project_checks.configured_for(session, task.project_id)
        ):
            return None

        token = task_integration.GIT_TIMEOUT_SECONDS.set(
            task_integration.DIAGNOSTIC_GIT_TIMEOUT_SECONDS
        )
        try:
            async with session.begin_nested():
                refusal, _ = await evaluate(session, task, acting_run_id=acting_run_id)
        finally:
            task_integration.GIT_TIMEOUT_SECONDS.reset(token)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return _could_not_ask_git(f"{type(exc).__name__}: {exc}")
    except Exception:
        logger.warning("approval hold for task %s could not be computed", task.id, exc_info=True)
        return None

    if not refusal.refuses:
        return None
    granted = bool(candidate) and await requirement_evidence.may_accept(
        session, task.project_id, Actor(kind="agent", name=candidate or "")
    )
    remedy = _operator_only_remedy(refusal, may_accept=granted, task_id=task.id)
    if remedy is None:
        return None
    return ApprovalHold(detail=refusal.detail(), remedy=remedy, refusal=refusal)
