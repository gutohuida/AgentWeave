"""Generating a checkpoint's written half, and checking it against what the Hub already knows.

Two Worker calls, with a deterministic grader between them.

**Generation** assembles its input from the database — the preceding checkpoint plus only the
turns since it — and asks the model for judgement alone. The prompt never asks for a changed
file, a task, a question or a timestamp; those are computed (`checkpoints.compute_envelope`) and
asking for them is the failure this change exists to remove.

**The probe** is the tractable version of the control-plane literature's blind resume: give a
reader nothing but the checkpoint and ask it the questions the Hub can already answer, then
compare. Factory needed an LLM judge because they had nothing to compare against; the Hub has
`files_changed`, `tasks` and `open_questions` sitting in a table, so the dimension that
benchmarks worst everywhere is the one that can be settled deterministically.

**The probe reads the whole rendered checkpoint, not the body alone.** That is a deliberate
choice and the alternative is not merely weaker, it is broken: the generation prompt is forbidden
from asking for computed fields, so the body legitimately contains no file list, and a probe of
the body in isolation would fail every well-formed checkpoint. Reading the artifact exactly as a
successor receives it catches the failures that are real — a body that contradicts the envelope
(summarisers drop file paths, which is Factory's finding), and a render that drops or mangles the
envelope on the way out.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field
from sqlalchemy import select

from .checkpoint_access import build_citations
from .checkpoints import (
    CheckpointEnvelope,
    compute_envelope,
    create_checkpoint,
    latest_checkpoint,
    loop_for_conversation,
    runs_to_cover,
)
from .db.models import (
    AgentOutput,
    Checkpoint,
    CheckpointNote,
    Conversation,
    InboundQueueEntry,
)
from .worker import run_worker

logger = logging.getLogger(__name__)

# Bumped whenever the prompt changes. Recorded on every `WorkerInvocation`, so a change in output
# quality is attributable to the prompt that produced it rather than guessed at.
CHECKPOINT_PROMPT_VERSION = "checkpoint/1"
PROBE_PROMPT_VERSION = "checkpoint-probe/1"

# How much transcript the generator sees. Anchoring already bounds this to the turns since the
# last checkpoint; the cap is for the first checkpoint on a long conversation, where there is no
# anchor and the whole thing would otherwise be paid for at full price.
_TRANSCRIPT_CHAR_LIMIT = 60_000
_ENTRY_CHAR_LIMIT = 4_000


class CheckpointBody(BaseModel):
    """The judgement half. Every field here is something the Hub cannot determine for itself.

    Deliberately absent: files changed, tasks, questions, timestamps, runner, model. Those are
    computed. A model asked for a timestamp it could not obtain invented one — observed — and the
    only reliable fix is not to ask.
    """

    objective: str = Field(description="What this conversation is for, in one or two sentences.")
    state: str = Field(description="Where the work actually got to.")
    decisions: List[str] = Field(
        default_factory=list, description="Decisions made, each with what was rejected and why."
    )
    dead_ends: List[str] = Field(
        default_factory=list, description="What was tried and did not work, with the symptom."
    )
    next_actions: List[str] = Field(
        default_factory=list,
        description="Ordered. The first must be executable without a further decision.",
    )
    risks: List[str] = Field(
        default_factory=list, description="What a successor should not repeat or assume."
    )


class ProbeAnswers(BaseModel):
    """What a reader given only the checkpoint says it contains."""

    files_changed: List[str] = Field(default_factory=list)
    task_ids: List[str] = Field(default_factory=list)
    unanswered_question_ids: List[str] = Field(default_factory=list)


_GENERATION_PROMPT = """\
You are writing a checkpoint for a software conversation so that a different agent, who has \
never seen it, can pick the work up.

Reply with a single JSON object and nothing else, matching exactly:
{{
  "objective": string,
  "state": string,
  "decisions": [string],
  "dead_ends": [string],
  "next_actions": [string],
  "risks": [string]
}}

Rules:
- Write only judgement. Do NOT list changed files, tasks, open questions, timestamps, or which \
model was used — those are recorded separately and anything you write about them is discarded.
- "decisions" each say what was chosen AND what was rejected, and why.
- "dead_ends" each say what was tried and the symptom that showed it had failed.
- "next_actions" are ordered, and the first must be executable without any further decision.
- If you do not know something, say so. Do not invent a fact you cannot see below.
{anchor_section}{notes_section}
--- conversation since{anchor_phrase} ---
{transcript}
--- end ---"""

_ANCHOR_SECTION = """
The previous checkpoint for this conversation is below. Carry forward what is still true and \
record what has changed; do not restate it wholesale.

--- previous checkpoint ---
{anchor_body}
--- end previous checkpoint ---
"""

_NOTES_SECTION = """
The agent working in this conversation left these notes. They are one input among several and \
may be wrong or incomplete; the transcript is authoritative where they disagree.

--- agent notes ---
{notes}
--- end agent notes ---
"""

_PROBE_PROMPT = """\
Below is a checkpoint describing a software conversation. You have not seen the conversation \
itself and must answer only from what is written here.

Reply with a single JSON object and nothing else, matching exactly:
{{
  "files_changed": [string],
  "task_ids": [string],
  "unanswered_question_ids": [string]
}}

Rules:
- List every file path the checkpoint says was changed. Use the paths exactly as written.
- List the id of every task the checkpoint says is assigned to this agent.
- List the id of every question the checkpoint says is still unanswered.
- If the checkpoint does not say, return an empty list. Do not guess and do not infer.

--- checkpoint ---
{rendered}
--- end ---"""


async def _transcript_since(db, conversation: Conversation, anchor: Optional[Checkpoint]) -> str:
    """The turns a new checkpoint covers, as text, oldest first.

    Both sides of the exchange: what arrived (operator messages, peer messages, answers) and what
    the agent said back. A checkpoint written from only one side describes half a conversation.
    """
    # Bounded by *when the anchor was taken*, uniformly for both sides. Filtering the agent's
    # outputs by covered run id and leaving inbound entries unfiltered would replay every
    # operator message the previous checkpoint already summarised, on every subsequent
    # checkpoint — and `InboundQueueEntry` carries no run to filter by in any case.
    since = anchor.created_at if anchor is not None else None

    output_query = select(AgentOutput).where(
        AgentOutput.conversation_id == conversation.id,
        AgentOutput.kind == "text",
    )
    inbound_query = select(InboundQueueEntry).where(
        InboundQueueEntry.conversation_id == conversation.id
    )
    if since is not None:
        # `>=`, not `>`. The clock's resolution is coarse enough (~15ms on Windows) that a turn
        # recorded in the same tick as the checkpoint compares equal, and a strict `>` drops it
        # from this checkpoint *and* every later one — it is only ever compared against a newer
        # anchor. Including a boundary turn twice is a redundancy; losing it is a hole, which is
        # the same trade `runs_to_cover` makes for a missing anchor run.
        output_query = output_query.where(AgentOutput.timestamp >= since)
        inbound_query = inbound_query.where(InboundQueueEntry.arrived_at >= since)

    outputs = list(
        (await db.execute(output_query.order_by(AgentOutput.timestamp, AgentOutput.id)))
        .scalars()
        .all()
    )
    inbound = list(
        (
            await db.execute(
                inbound_query.order_by(InboundQueueEntry.arrived_at, InboundQueueEntry.id)
            )
        )
        .scalars()
        .all()
    )

    events: List[Tuple[Any, str, str]] = []
    for entry in inbound:
        events.append((entry.arrived_at, "Received", entry.content or ""))
    for output in outputs:
        events.append((output.timestamp, conversation.agent, output.content or ""))

    events.sort(key=lambda item: (item[0] is None, item[0]))

    rendered: List[str] = []
    budget = _TRANSCRIPT_CHAR_LIMIT
    # Newest-first while trimming, so a conversation that overflows keeps its *recent* turns —
    # the ones a successor needs — rather than its opening.
    for _, speaker, content in reversed(events):
        chunk = f"{speaker}: {content[:_ENTRY_CHAR_LIMIT]}"
        if len(chunk) > budget:
            break
        rendered.append(chunk)
        budget -= len(chunk)
    return "\n\n".join(reversed(rendered))


def build_generation_prompt(
    *, transcript: str, anchor_body: Optional[str] = None, notes: Optional[str] = None
) -> str:
    anchor_section = _ANCHOR_SECTION.format(anchor_body=anchor_body) if anchor_body else ""
    notes_section = _NOTES_SECTION.format(notes=notes) if notes else ""
    return _GENERATION_PROMPT.format(
        anchor_section=anchor_section,
        notes_section=notes_section,
        anchor_phrase=" the previous checkpoint" if anchor_body else " it began",
        transcript=transcript or "(no turns recorded)",
    )


def render_body(body: CheckpointBody, *, notes_incorporated: bool) -> str:
    """The model's half, as markdown.

    `notes_incorporated` is stated on the record rather than left implicit: the spec requires a
    checkpoint produced without agent notes to say so, because "the agent had nothing to add" and
    "the agent was never asked, or never answered" read identically otherwise.
    """

    def section(title: str, items: List[str]) -> str:
        if not items:
            return f"## {title}\n\n_None recorded._\n"
        lines = "\n".join(f"- {item}" for item in items)
        return f"## {title}\n\n{lines}\n"

    parts = [
        f"## Objective\n\n{body.objective}\n",
        f"## Current state\n\n{body.state}\n",
        section("Decisions", body.decisions),
        section("Dead ends", body.dead_ends),
        section("Next actions", body.next_actions),
        section("Risks", body.risks),
    ]
    if not notes_incorporated:
        parts.append(
            "## Agent notes\n\n_The agent contributed no notes to this checkpoint; it was "
            "generated from the conversation record alone._\n"
        )
    return "\n".join(parts)


def render_checkpoint(checkpoint: Checkpoint) -> str:
    """The whole artifact, exactly as a successor receives it — computed half then written half.

    This is also what the probe reads, which is the point: a render that drops the envelope is a
    real defect and probing the stored columns directly would never see it.
    """
    tasks_payload = checkpoint.tasks or {}
    lines: List[str] = [f"# Checkpoint {checkpoint.id}", ""]
    lines.append(f"Conversation: {checkpoint.conversation_id}")
    lines.append(f"Agent: {checkpoint.agent}")
    lines.append(f"Trigger: {checkpoint.trigger}")
    lines.append(f"Status: {checkpoint.status}")
    if checkpoint.probe_status:
        lines.append(f"Probe: {checkpoint.probe_status}")
    if checkpoint.previous_checkpoint_id:
        lines.append(f"Previous checkpoint: {checkpoint.previous_checkpoint_id}")
    lines.append("")

    lines.append("## Files changed")
    lines.append("")
    if checkpoint.files_changed:
        lines.extend(f"- {path}" for path in checkpoint.files_changed)
    else:
        lines.append("_No files recorded as changed._")
    lines.append("")

    lines.append("## Tasks")
    lines.append("")
    note = tasks_payload.get("note")
    if note:
        lines.append(f"_{note}_")
        lines.append("")
    items = tasks_payload.get("items") or []
    if items:
        lines.extend(
            f"- {item.get('id')} — {item.get('title')} ({item.get('status')})" for item in items
        )
    else:
        lines.append("_No tasks assigned._")
    lines.append("")

    lines.append("## Open questions")
    lines.append("")
    if checkpoint.open_questions:
        lines.extend(f"- {q.get('id')} — {q.get('question')}" for q in checkpoint.open_questions)
    else:
        lines.append("_None outstanding._")
    lines.append("")

    if checkpoint.permission_decisions:
        lines.append("## Permission decisions")
        lines.append("")
        lines.extend(
            f"- {d.get('tool')}: {d.get('status')}" for d in checkpoint.permission_decisions
        )
        lines.append("")

    if checkpoint.runtime_overrides:
        lines.append("## Runtime overrides in force")
        lines.append("")
        lines.extend(f"- {key}: {value}" for key, value in checkpoint.runtime_overrides.items())
        lines.append("")

    if checkpoint.status == "failed":
        # F50: the computed sections above are the Hub's own and stay accurate regardless of the
        # probe's verdict. Skipping the written half entirely would cost a reviewer real signal to
        # avoid a wrong paragraph; stating the disagreement lets them judge the body accordingly.
        lines.append(
            f"_This checkpoint's written summary failed its probe (probe_status: "
            f"{checkpoint.probe_status}) — it was graded against the computed record above and "
            f"disagreed with it. The sections above remain accurate; treat what follows with that "
            f"in mind._"
        )
        lines.append("")

    if checkpoint.body:
        lines.append(checkpoint.body)
    else:
        lines.append(
            "_No written summary: generation produced nothing usable for this checkpoint._"
        )

    if checkpoint.citations:
        lines.append("")
        lines.append("## Recorded observations")
        lines.append("")
        lines.append(
            "_A summary is lossy. Each id below can be materialised exactly with `recall`, so "
            "anything compressed away is still recoverable._"
        )
        lines.append("")
        for entry in checkpoint.citations:
            preview = (entry.get("preview") or "").replace("\n", " ").strip()
            lines.append(f"- `{entry.get('id')}` — {preview}")
    return "\n".join(lines)


def _normalise(values: List[str]) -> set:
    return {
        str(value).strip().replace("\\", "/").lstrip("./") for value in values if str(value).strip()
    }


def grade_probe(answers: ProbeAnswers, envelope: CheckpointEnvelope) -> Tuple[str, List[Dict]]:
    """Compare a blind reader's answers to the Hub's own records.

    Returns ("passed" | "failed", findings). A finding names the dimension, what was missed, and
    what was invented — "it disagreed" is not actionable, and the two failure directions mean
    different things: a missing path is information the checkpoint lost, an invented one is
    information it made up.
    """
    expected_files = _normalise(envelope.files_changed)
    expected_tasks = {str(item.get("id")) for item in (envelope.tasks or {}).get("items", [])}
    expected_questions = {str(q.get("id")) for q in envelope.open_questions}

    findings: List[Dict] = []
    for dimension, expected, reported in (
        ("files_changed", expected_files, _normalise(answers.files_changed)),
        ("task_ids", expected_tasks, {str(v).strip() for v in answers.task_ids if str(v).strip()}),
        (
            "unanswered_question_ids",
            expected_questions,
            {str(v).strip() for v in answers.unanswered_question_ids if str(v).strip()},
        ),
    ):
        missing = sorted(expected - reported)
        invented = sorted(reported - expected)
        if missing or invented:
            findings.append({"dimension": dimension, "missing": missing, "invented": invented})

    return ("failed" if findings else "passed"), findings


async def pending_notes(db, conversation_id: str) -> Optional[CheckpointNote]:
    """The agent's most recent notes for this conversation that no checkpoint has taken yet.

    Unconsumed, so a second checkpoint does not silently reuse notes written for the first — the
    agent wrote them about a moment that has passed, and presenting them as current is the same
    class of staleness as reporting a pre-compaction context percentage.
    """
    return (
        (
            await db.execute(
                select(CheckpointNote)
                .where(
                    CheckpointNote.conversation_id == conversation_id,
                    CheckpointNote.consumed_by_checkpoint_id.is_(None),
                )
                .order_by(CheckpointNote.created_at.desc(), CheckpointNote.id.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


def format_notes(note: CheckpointNote) -> str:
    """The agent's notes as the generator sees them."""
    parts = [f"In flight: {note.intent}"]
    if note.suspicions:
        parts.append(
            "Unverified suspicions:\n" + "\n".join(f"- {item}" for item in note.suspicions)
        )
    if note.warnings:
        parts.append(
            "Warnings for a successor:\n" + "\n".join(f"- {item}" for item in note.warnings)
        )
    return "\n\n".join(parts)


async def generate_checkpoint(
    db,
    conversation: Conversation,
    *,
    trigger: str,
    cli: str,
    model: Optional[str] = None,
    runner_id: Optional[str] = None,
    notes: Optional[str] = None,
    worktree=None,
    probe: bool = True,
    visibility: str = "private",
) -> Checkpoint:
    """Produce a checkpoint for *conversation*. Always returns a record.

    Generation failing does not prevent a checkpoint; it produces an `unwritten` one carrying the
    computed half. That inversion — the Hub authoritative, the model contributing — is the whole
    change: the previous design made the agent authoritative and the Hub hopeful, and it was
    observed producing nothing while reporting success.
    """
    anchor = await latest_checkpoint(db, conversation.id)
    loop = await loop_for_conversation(db, conversation.id)
    envelope = await compute_envelope(db, conversation, worktree=worktree, anchor=anchor, loop=loop)
    transcript = await _transcript_since(db, conversation, anchor)
    covered_runs = await runs_to_cover(db, conversation.id, anchor)

    # An explicit `notes=` argument wins, so a caller can generate without them deliberately.
    note = None if notes is not None else await pending_notes(db, conversation.id)
    if note is not None:
        notes = format_notes(note)

    result = await run_worker(
        project_id=conversation.project_id,
        kind="checkpoint",
        prompt=build_generation_prompt(
            transcript=transcript,
            anchor_body=anchor.body if anchor else None,
            notes=notes,
        ),
        prompt_version=CHECKPOINT_PROMPT_VERSION,
        output_model=CheckpointBody,
        cli=cli,
        model=model,
        runner_id=runner_id,
        conversation_id=conversation.id,
    )

    body = (
        render_body(result.parsed, notes_incorporated=bool(notes))
        if result.ok and result.parsed is not None
        else None
    )
    if body is None:
        logger.info(
            "checkpoint for %s has no written half: worker %s",
            conversation.id,
            result.outcome,
        )

    checkpoint = await create_checkpoint(
        db,
        conversation,
        trigger=trigger,
        envelope=envelope,
        body=body,
        anchor=anchor,
        worker_invocation_id=result.invocation_id,
        runner=cli,
        model=model,
        visibility=visibility,
        loop=loop,
    )

    # Citations are attached whether or not a body was written: they point at what exists in
    # `agent_outputs`, so an `unwritten` checkpoint still gives a reader an exact way in.
    checkpoint.citations = await build_citations(
        db, conversation.id, [run.id for run in covered_runs]
    )

    if note is not None:
        # Marked consumed even when generation failed. The notes described a moment that has now
        # passed; carrying them into a later checkpoint would present stale intent as current.
        note.consumed_by_checkpoint_id = checkpoint.id
    await db.commit()

    if probe and checkpoint.status == "ready":
        await probe_checkpoint(
            db,
            checkpoint,
            envelope=envelope,
            cli=cli,
            model=model,
            runner_id=runner_id,
        )
    return checkpoint


async def probe_checkpoint(
    db,
    checkpoint: Checkpoint,
    *,
    envelope: CheckpointEnvelope,
    cli: str,
    model: Optional[str] = None,
    runner_id: Optional[str] = None,
) -> Checkpoint:
    """Read the checkpoint blind, answer what the Hub can already verify, and grade it.

    A probe that cannot run leaves `probe_status` NULL and the checkpoint `ready`. That is the
    deliberate choice: an unrunnable probe is the Hub's failure, not the checkpoint's, and
    failing a checkpoint because the grader was unavailable would recreate — in the other
    direction — the very thing this change removes, a status that reports something other than
    what it names.
    """
    result = await run_worker(
        project_id=checkpoint.project_id,
        kind="checkpoint_probe",
        prompt=_PROBE_PROMPT.format(rendered=render_checkpoint(checkpoint)),
        prompt_version=PROBE_PROMPT_VERSION,
        output_model=ProbeAnswers,
        cli=cli,
        model=model,
        runner_id=runner_id,
        conversation_id=checkpoint.conversation_id,
    )

    if not result.ok or result.parsed is None:
        logger.info("probe for checkpoint %s did not run: %s", checkpoint.id, result.outcome)
        return checkpoint

    status, findings = grade_probe(result.parsed, envelope)
    checkpoint.probe_status = status
    checkpoint.probe_findings = findings or None
    if status == "failed":
        # "Ready" means a record exists and passed. It has never meant "the run stopped", and it
        # must not come to mean "a record exists".
        checkpoint.status = "failed"
    await db.commit()
    return checkpoint
