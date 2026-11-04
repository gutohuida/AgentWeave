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
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, Field
from sqlalchemy import select

from . import project_workspace
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
from .worker import Initiator, run_worker

logger = logging.getLogger(__name__)

# Bumped whenever the prompt changes. Recorded on every `WorkerInvocation`, so a change in output
# quality is attributable to the prompt that produced it rather than guessed at.
CHECKPOINT_PROMPT_VERSION = "checkpoint/2"
# /2 (`every-checkpoint-findable-and-readable`, FR-11): the same call also writes a title and a
# summary, both required and both limited, so a checkpoint can be told apart without opening it.
# /2 (F360): the task rule asked for "every task the checkpoint says is assigned to this agent",
# while a loop checkpoint lists the loop's whole queue under a note saying so. A reader following
# the rule found no assignment stated and answered nothing, and `grade_probe` -- which compares
# against every listed item -- failed it: half of a flow's checkpoints marked failed for a question
# the Hub's own list does not answer. The rule now asks for what the grader checks.
PROBE_PROMPT_VERSION = "checkpoint-probe/2"

# How much transcript the generator sees. Anchoring already bounds this to the turns since the
# last checkpoint; the cap is for the first checkpoint on a long conversation, where there is no
# anchor and the whole thing would otherwise be paid for at full price.
_TRANSCRIPT_CHAR_LIMIT = 60_000
_ENTRY_CHAR_LIMIT = 4_000


class CheckpointTitle(BaseModel):
    """What tells one checkpoint from another. Asked for on its own only by the one-time fill of
    checkpoints taken before titles existed (`checkpoint_fill`); generation asks for it as part of
    `CheckpointBody`. Optional for the reason `CheckpointBody` gives."""

    title: Optional[str] = Field(
        default=None, description="What this checkpoint is about: at most 8 words, 60 characters."
    )
    summary: Optional[str] = Field(
        default=None, description="At most two sentences and 300 characters."
    )


class CheckpointBody(CheckpointTitle):
    """The judgement half. Every field here is something the Hub cannot determine for itself.

    Deliberately absent: files changed, tasks, questions, timestamps, runner, model. Those are
    computed. A model asked for a timestamp it could not obtain invented one — observed — and the
    only reliable fix is not to ask.

    `title` and `summary` are required by the prompt but optional here, on purpose: an answer
    that omits them must still *parse*, so that its readable sections survive a rejection
    (FR-13). Whether they are present and within the limits is `title_problem`'s judgement, not
    the schema's — a schema violation would discard the whole answer.
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
  "title": string,
  "summary": string,
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
- "title" is required: at most 8 words and 60 characters, saying what this conversation did, so it can be told apart from others in a list.
- "summary" is required: at most two sentences and 300 characters.
- An answer without a title or a summary, or with either over its limit, is rejected; it is not shortened for you.
{rejection_section}{anchor_section}{notes_section}
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

_REJECTION_SECTION = """
Your previous answer was rejected: {reason}. Reply again with the whole JSON object, correcting that.
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
- List the id of every task listed under the checkpoint's Tasks heading, whatever its status.
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
    *,
    transcript: str,
    anchor_body: Optional[str] = None,
    notes: Optional[str] = None,
    rejection: Optional[str] = None,
) -> str:
    """The generation prompt. *rejection* is what was wrong with the previous answer, when this
    is the second asking (FR-13)."""
    anchor_section = _ANCHOR_SECTION.format(anchor_body=anchor_body) if anchor_body else ""
    notes_section = _NOTES_SECTION.format(notes=notes) if notes else ""
    rejection_section = _REJECTION_SECTION.format(reason=rejection) if rejection else ""
    return _GENERATION_PROMPT.format(
        rejection_section=rejection_section,
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


# --------------------------------------------------------------------------- title and summary
#
# Limits agreed with the operator on 2026-11-02. Going over is a rejection, never a cut: a title
# shortened by the Hub mid-thought reads as the model's own and says less than either.
TITLE_MAX_WORDS = 8
TITLE_MAX_CHARS = 60
SUMMARY_MAX_SENTENCES = 2
SUMMARY_MAX_CHARS = 300

# Who wrote a checkpoint's title and summary (`Checkpoint.title_made_by`).
MADE_BY_MODEL = "model"
MADE_BY_HUB_FROM_BODY = "hub_from_body"
MADE_BY_HUB_FROM_FACTS = "hub_from_facts"

# Outcomes a second asking cannot change: the call is refused before any model is reached, the
# same way, every time -- a spent budget, a CLI or model the Hub cannot run, a runner whose record
# or provider is damaged. Asking again would only record a second identical refusal. A timeout or
# a CLI that exited non-zero did reach for a model and may not fail twice, so it is asked again.
_NOT_WORTH_ASKING_AGAIN = frozenset(
    {"budget_exhausted", "unsupported_cli", "unknown_model", "spawn_failed"}
)
# Outcomes where a model answered at all, so there is something to tell it was wrong.
_ANSWERED = frozenset({"unparseable", "schema_invalid"})

# A sentence ends at terminal punctuation followed by whitespace. Deliberately simple: an
# abbreviation miscounted makes a valid summary read as three sentences, which costs one more
# asking, never a wrong record.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Plain words for the triggers a facts title names. An unknown one is spelled out from its id.
_TRIGGER_WORDS = {
    "task_completion": "task finished",
    "operator": "operator asked",
    "context_pressure": "context grew long",
    "delegation": "delegated",
    "run_failure": "run failed",
}


def _words(text: str) -> List[str]:
    return re.findall(r"\S+", text or "")


def _sentences(text: str) -> List[str]:
    return [part for part in _SENTENCE_END.split((text or "").strip()) if part.strip()]


def title_problem(title: Optional[str], summary: Optional[str]) -> Optional[str]:
    """What is wrong with an answer's title and summary, in words the model is told on the second
    asking, or None when both are present and within the limits (FR-13)."""
    problems: List[str] = []
    title = (title or "").strip()
    summary = (summary or "").strip()
    if not title:
        problems.append("the title was missing")
    else:
        words = len(_words(title))
        if words > TITLE_MAX_WORDS:
            problems.append(f"the title has {words} words; at most {TITLE_MAX_WORDS} are allowed")
        if len(title) > TITLE_MAX_CHARS:
            problems.append(
                f"the title has {len(title)} characters; at most {TITLE_MAX_CHARS} are allowed"
            )
    if not summary:
        problems.append("the summary was missing")
    else:
        sentences = len(_sentences(summary))
        if sentences > SUMMARY_MAX_SENTENCES:
            problems.append(
                f"the summary has {sentences} sentences; at most {SUMMARY_MAX_SENTENCES} are "
                "allowed"
            )
        if len(summary) > SUMMARY_MAX_CHARS:
            problems.append(
                f"the summary has {len(summary)} characters; at most {SUMMARY_MAX_CHARS} are "
                "allowed"
            )
    return "; ".join(problems) if problems else None


def plain_text(body: str) -> str:
    """A rendered checkpoint body without its markdown scaffolding: no headings, no bullet marks,
    no `_None recorded._` placeholders. What "the first words of its body" are read from."""
    kept: List[str] = []
    for line in (body or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("_") and stripped.endswith("_"):
            continue  # an italic placeholder the renderer wrote, not the model
        stripped = re.sub(r"^[-*+]\s+|^\d+\.\s+", "", stripped)
        kept.append(stripped.replace("**", "").replace("`", ""))
    return " ".join(kept)


def title_from_text(text: str) -> Optional[str]:
    """The first words of *text*, within both title limits, or None when it has no words.

    Taken from its first sentence only, so a short opening sentence is not run into the next.
    """
    sentences = _sentences(text)
    text = sentences[0] if sentences else text
    words = _words(text)[:TITLE_MAX_WORDS]
    while words and len(" ".join(words)) > TITLE_MAX_CHARS:
        words.pop()
    if not words:
        first = _words(text)[:1]
        return first[0][:TITLE_MAX_CHARS] if first else None
    title = " ".join(words).rstrip(".,;:!?-—")
    return title or " ".join(words)


def summary_from_text(text: str) -> Optional[str]:
    """The opening sentences of *text*, within both summary limits, or None when it is empty.

    A first sentence longer than the whole limit is cut at a word and marked with an ellipsis:
    the summary is the Hub's own, marked as such, and something is better than nothing.
    """
    sentences = _sentences(text)
    if not sentences:
        return None
    kept: List[str] = []
    for sentence in sentences[:SUMMARY_MAX_SENTENCES]:
        candidate = " ".join(kept + [sentence.strip()])
        if len(candidate) > SUMMARY_MAX_CHARS:
            break
        kept.append(sentence.strip())
    if kept:
        return " ".join(kept)
    cut = sentences[0][: SUMMARY_MAX_CHARS - 1]
    if " " in cut:
        cut = cut[: cut.rindex(" ")]
    return cut.rstrip() + "…"


def trigger_words(trigger: str) -> str:
    return _TRIGGER_WORDS.get(trigger) or (trigger or "unknown trigger").replace("_", " ")


def title_from_facts(agent: str, trigger: str, when: datetime) -> str:
    """A title made from what the Hub knows when no answer could be read: agent, trigger, date."""
    title = f"{agent}: {trigger_words(trigger)}, {when.date().isoformat()}"
    return title if len(title) <= TITLE_MAX_CHARS else title[:TITLE_MAX_CHARS]


def summary_from_facts(checkpoint: Checkpoint) -> str:
    """What the Hub recorded itself, counted, for a checkpoint with no readable answer."""
    files = len(checkpoint.files_changed or [])
    tasks = len((checkpoint.tasks or {}).get("items") or [])
    questions = len(checkpoint.open_questions or [])
    citations = len(checkpoint.citations or [])
    return (
        "No written summary: the model's answers could not be read. "
        f"The Hub recorded {files} changed file(s), {tasks} task(s), {questions} open "
        f"question(s) and {citations} citation(s)."
    )


def unreadable_reason(outcome: str, error: Optional[str]) -> str:
    """Why an answer could not be read, as the operator and the second asking read it."""
    if outcome in _ANSWERED:
        return f"the answer could not be read ({error or outcome})"
    return f"no answer was returned ({outcome}: {error or 'no detail'})"


def _rejection_record(reasons: List[str]) -> str:
    labels = ("first answer", "second answer")
    return "; ".join(f"{labels[i] if i < 2 else 'answer'}: {r}" for i, r in enumerate(reasons))


def _task_name(item: Dict) -> str:
    """What a checkpoint calls a task, and so what the probe expects its reader to answer. A
    checkpoint written before `readable_id` holds the stored id alone."""
    return str(item.get("readable_id") or item.get("id"))


def render_checkpoint(checkpoint: Checkpoint) -> str:
    """The whole artifact, exactly as a successor receives it — computed half then written half.

    This is also what the probe reads, which is the point: a render that drops the envelope is a
    real defect and probing the stored columns directly would never see it.
    """
    tasks_payload = checkpoint.tasks or {}
    lines: List[str] = [f"# Checkpoint {checkpoint.id}", ""]
    if checkpoint.title:
        made_by_hub = checkpoint.title_made_by not in (None, MADE_BY_MODEL)
        lines.append(f"Title: {checkpoint.title}" + (" (made by the Hub)" if made_by_hub else ""))
    if checkpoint.summary:
        lines.append(f"Summary: {checkpoint.summary}")
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
            f"- {_task_name(item)} — {item.get('title')} ({item.get('status')})" for item in items
        )
    else:
        lines.append("_No tasks assigned._")
    lines.append("")

    lines.append("## Open questions")
    lines.append("")
    if checkpoint.open_questions:
        lines.extend(
            f"- {q.get('id')} — {q.get('question')}"
            + (
                " (wait ended: the asker stopped waiting for an answer)"
                if q.get("wait_ended")
                else ""
            )
            for q in checkpoint.open_questions
        )
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
    # `re.sub` drops the separator a Windows-style or escaped at-sign leaves ahead of it, so
    # `node_modules\@types` and `packages/\@scope` meet the plain `@` form (F409, D7).
    return {
        re.sub(r"/+@", "@", str(value).strip().replace("\\", "/")).lstrip("./")
        for value in values
        if str(value).strip()
    }


def grade_probe(answers: ProbeAnswers, envelope: CheckpointEnvelope) -> Tuple[str, List[Dict]]:
    """Compare a blind reader's answers to the Hub's own records.

    Returns ("passed" | "failed", findings). A finding names the dimension, what was missed, and
    what was invented — "it disagreed" is not actionable, and the two failure directions mean
    different things: a missing path is information the checkpoint lost, an invented one is
    information it made up.
    """
    expected_files = _normalise(envelope.files_changed)
    expected_tasks = {_task_name(item) for item in (envelope.tasks or {}).get("items", [])}
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


async def consume_note(db, note: CheckpointNote, checkpoint_id: str) -> None:
    """Mark *note* taken by *checkpoint_id*, and retire the older notes it was chosen over.

    Only the newest unconsumed note feeds a checkpoint. The ones before it described moments this
    checkpoint now covers, so they are marked with it too (F236): left unconsumed, each resurfaced
    in a later checkpoint as though it had been written for that one. A note written after
    *note* stays pending — it may have arrived while this checkpoint was being generated. Does not
    commit.
    """
    note.consumed_by_checkpoint_id = checkpoint_id
    passed_over = (
        (
            await db.execute(
                select(CheckpointNote).where(
                    CheckpointNote.conversation_id == note.conversation_id,
                    CheckpointNote.consumed_by_checkpoint_id.is_(None),
                    CheckpointNote.id != note.id,
                    CheckpointNote.created_at <= note.created_at,
                )
            )
        )
        .scalars()
        .all()
    )
    for older in passed_over:
        older.consumed_by_checkpoint_id = checkpoint_id


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


async def _repo_root_for(db, conversation: Conversation) -> Optional[Path]:
    """This conversation's project directory, or None if it cannot be resolved.

    Best-effort, matching everything else this module computes: a project whose workspace is
    unavailable yields a checkpoint with no file list, never a failed checkpoint. That is the same
    rule `_files_from_runs` already follows for a commit that cannot be read.
    """
    try:
        workspace = await project_workspace.resolve_project_workspace(db, conversation.project_id)
    except project_workspace.ProjectWorkspaceError:
        logger.debug(
            "no project workspace for conversation %s; checkpoint reports no files",
            conversation.id,
            exc_info=True,
        )
        return None
    return workspace.root


@dataclass
class GenerationAnswer:
    """What asking for a checkpoint came to, over at most two askings (FR-13).

    `accepted` is an answer whose title and summary passed; `readable` the last answer that parsed
    but was rejected; neither, when nothing could be read. `reason` says what was wrong with each
    asking, for the record; `unreadable_answer` is the raw text of an answer that could not be
    read, kept for "show what the model returned" and never used as the body. `answered` is
    whether a model was reached at all, by either asking: the one-time fill leaves a checkpoint
    for its next start when it was not.
    """

    accepted: Optional[CheckpointTitle] = None
    readable: Optional[CheckpointTitle] = None
    answered: bool = False
    reason: Optional[str] = None
    unreadable_answer: Optional[str] = None
    invocation_id: Optional[str] = None
    askings: int = 0


async def ask_for_checkpoint(
    *,
    project_id: str,
    conversation_id: Optional[str],
    prompt_for: Callable[[Optional[str]], str],
    cli: str,
    model: Optional[str],
    runner_id: Optional[str],
    initiator: Initiator,
    kind: str = "checkpoint",
    output_model: Type[CheckpointTitle] = CheckpointBody,
    prompt_version: str = CHECKPOINT_PROMPT_VERSION,
) -> GenerationAnswer:
    """Ask the model for a checkpoint, and once more if its answer is rejected.

    *prompt_for* builds the prompt given what was wrong with the previous answer (None on the
    first asking), so the second asking names it. An answer is accepted only with a title and a
    summary within the limits; one that parses without them is kept as `readable`, so its sections
    survive a second rejection. A refusal no second asking can change (a spent budget, a CLI or
    model the Hub cannot run) is not asked again.
    """
    answer = GenerationAnswer()
    reasons: List[str] = []
    rejection: Optional[str] = None
    for _ in range(2):
        result = await run_worker(
            project_id=project_id,
            kind=kind,
            prompt=prompt_for(rejection),
            prompt_version=prompt_version,
            output_model=output_model,
            cli=cli,
            model=model,
            runner_id=runner_id,
            conversation_id=conversation_id,
            initiator=initiator,
        )
        answer.askings += 1
        answer.invocation_id = result.invocation_id
        answer.answered = answer.answered or result.ok or result.outcome in _ANSWERED
        if result.ok and isinstance(result.parsed, output_model):
            problem = title_problem(result.parsed.title, result.parsed.summary)
            if problem is None:
                answer.accepted = result.parsed
                answer.reason = None
                return answer
            answer.readable = result.parsed
            rejection = problem
        else:
            problem = unreadable_reason(result.outcome, result.error)
            if (result.answer_text or "").strip():
                answer.unreadable_answer = result.answer_text
            # Only a model that answered is told what was wrong; one never reached is simply
            # asked again, with nothing to correct.
            rejection = problem if result.outcome in _ANSWERED else None
        reasons.append(problem)
        answer.reason = _rejection_record(reasons)
        if result.outcome in _NOT_WORTH_ASKING_AGAIN:
            break
    return answer


def apply_title(checkpoint: Checkpoint, answer: GenerationAnswer, *, fallback_text: str) -> None:
    """Give *checkpoint* its title and summary from *answer*, or make them (FR-13).

    The model's when an answer was accepted. Otherwise the Hub's: from *fallback_text* (the body's
    first words and opening sentences) when it has any -- generation's body exists only when an
    answer could be read; the fill's existed before it asked -- else from the agent, trigger and
    date, keeping any unreadable raw text aside. Always leaves a title — a checkpoint never
    ends with no information. Does not commit.
    """
    if answer.accepted is not None:
        checkpoint.title = (answer.accepted.title or "").strip()
        checkpoint.summary = (answer.accepted.summary or "").strip()
        checkpoint.title_made_by = MADE_BY_MODEL
        checkpoint.title_reason = None
        checkpoint.unreadable_answer = None
        return
    title = title_from_text(fallback_text)
    if title is not None:
        checkpoint.title = title
        checkpoint.summary = summary_from_text(fallback_text) or title
        checkpoint.title_made_by = MADE_BY_HUB_FROM_BODY
        # The body is the readable answer; a raw text kept beside it would be a second, junk one.
        checkpoint.unreadable_answer = None
    else:
        checkpoint.title = title_from_facts(
            checkpoint.agent,
            checkpoint.trigger,
            checkpoint.created_at or datetime.now(timezone.utc),
        )
        checkpoint.summary = summary_from_facts(checkpoint)
        checkpoint.title_made_by = MADE_BY_HUB_FROM_FACTS
        checkpoint.unreadable_answer = answer.unreadable_answer
    checkpoint.title_reason = answer.reason


async def generate_checkpoint(
    db,
    conversation: Conversation,
    *,
    trigger: str,
    cli: str,
    model: Optional[str] = None,
    runner_id: Optional[str] = None,
    notes: Optional[str] = None,
    probe: bool = True,
) -> Checkpoint:
    """Produce a checkpoint for *conversation*. Always returns a record.

    Generation failing does not prevent a checkpoint; it produces an `unwritten` one carrying the
    computed half. That inversion — the Hub authoritative, the model contributing — is the whole
    change: the previous design made the agent authoritative and the Hub hopeful, and it was
    observed producing nothing while reporting success.

    **The repository is resolved here, not passed in — task 6.6.** It used to be a `worktree`
    parameter defaulting to `None`, and all three callers omitted it, so `files_changed` was empty
    in every checkpoint this product has ever produced. The unit tests passed a worktree straight
    into `compute_envelope` and so could not see it. Resolving in the one place that always has a
    conversation removes the way to forget: a caller cannot omit an argument that no longer exists.

    Only the operator's own press is operator work; a context-pressure or task-completion
    checkpoint is autonomous, and so is its probe, so neither spends past a spent budget (F240).
    """
    initiator: Initiator = "operator" if trigger == "operator" else "autonomous"
    anchor = await latest_checkpoint(db, conversation.id)
    loop = await loop_for_conversation(db, conversation.id)
    repo_root = await _repo_root_for(db, conversation)
    envelope = await compute_envelope(
        db, conversation, repo_root=repo_root, anchor=anchor, loop=loop
    )
    transcript = await _transcript_since(db, conversation, anchor)
    covered_runs = await runs_to_cover(db, conversation.id, anchor)

    # An explicit `notes=` argument wins, so a caller can generate without them deliberately.
    note = None if notes is not None else await pending_notes(db, conversation.id)
    if note is not None:
        notes = format_notes(note)

    # Let go of the transaction before spawning, and this is not a tidiness point — it is the
    # whole of F89. Everything above is reads, and on SQLite a read transaction holds a SHARED
    # lock that no other connection can write past. `run_worker` then blocks for ~20s on a CLI,
    # every other connection's write waits out the 5s busy timeout and raises `database is
    # locked`, and the live turn that triggered this checkpoint dies mid-stream without ever
    # finalising — measured twice on 2026-08-28, both runs left `running` forever with no
    # `run_completed`, and the checkpoint's own `WorkerInvocation` lost to the same lock.
    #
    # `run_worker`'s docstring already states the rule this restores: "Callers pass primitives
    # rather than a `Runner` row so the spawn does not hold a session open across a call that can
    # take minutes." Passing primitives is not enough on its own if the caller's own transaction
    # is still open around it.
    #
    # `expire_on_commit=False` on the session factory, so `conversation`, `anchor` and `loop` stay
    # usable below rather than re-loading on next access.
    await db.commit()

    answer = await ask_for_checkpoint(
        project_id=conversation.project_id,
        conversation_id=conversation.id,
        prompt_for=lambda rejection: build_generation_prompt(
            transcript=transcript,
            anchor_body=anchor.body if anchor else None,
            notes=notes,
            rejection=rejection,
        ),
        cli=cli,
        model=model,
        runner_id=runner_id,
        initiator=initiator,
    )

    readable = answer.accepted or answer.readable
    body = render_body(readable, notes_incorporated=bool(notes)) if readable else None
    if body is None:
        logger.info("checkpoint for %s has no written half: %s", conversation.id, answer.reason)

    checkpoint = await create_checkpoint(
        db,
        conversation,
        trigger=trigger,
        envelope=envelope,
        body=body,
        anchor=anchor,
        worker_invocation_id=answer.invocation_id,
        runner=cli,
        model=model,
        loop=loop,
    )

    # Citations are attached whether or not a body was written: they point at what exists in
    # `agent_outputs`, so an `unwritten` checkpoint still gives a reader an exact way in.
    checkpoint.citations = await build_citations(
        db, conversation.id, [run.id for run in covered_runs]
    )
    apply_title(checkpoint, answer, fallback_text=plain_text(body or ""))

    if note is not None:
        # Marked consumed even when generation failed. The notes described a moment that has now
        # passed; carrying them into a later checkpoint would present stale intent as current.
        await consume_note(db, note, checkpoint.id)
    await db.commit()

    if probe and checkpoint.status == "ready":
        await probe_checkpoint(
            db,
            checkpoint,
            envelope=envelope,
            cli=cli,
            model=model,
            runner_id=runner_id,
            initiator=initiator,
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
    initiator: Initiator,
) -> Checkpoint:
    """Read the checkpoint blind, answer what the Hub can already verify, and grade it.

    A probe that cannot run leaves `probe_status` NULL and the checkpoint `ready`. That is the
    deliberate choice: an unrunnable probe is the Hub's failure, not the checkpoint's, and
    failing a checkpoint because the grader was unavailable would recreate — in the other
    direction — the very thing this change removes, a status that reports something other than
    what it names.
    """
    # Rendered first and committed second, for F89's reason again: rendering reads the row, and
    # doing it inside the `run_worker` call would open a transaction that then stays open across
    # the spawn. The caller has already committed; this keeps that true for callers who have not.
    prompt = _PROBE_PROMPT.format(rendered=render_checkpoint(checkpoint))
    await db.commit()

    result = await run_worker(
        project_id=checkpoint.project_id,
        kind="checkpoint_probe",
        prompt=prompt,
        prompt_version=PROBE_PROMPT_VERSION,
        output_model=ProbeAnswers,
        cli=cli,
        model=model,
        runner_id=runner_id,
        conversation_id=checkpoint.conversation_id,
        initiator=initiator,
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
