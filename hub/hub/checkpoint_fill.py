"""The one-time fill: a title and summary for every checkpoint taken before they existed
(`every-checkpoint-findable-and-readable`, FR-12).

Started in `main.lifespan` with the Hub's other background work, off every request's path. Each
checkpoint whose `title` is NULL is sent its own existing body -- nothing else -- and asked for a
title and summary under the rules generation follows: the same limits, the same one further
asking naming what was wrong, the same first-words fallback after a second rejection. The asking
and the fallback are `ask_for_checkpoint` and `apply_title` themselves, so the fill and generation
cannot drift apart.

**Resumable by construction.** "Unfilled" is `title IS NULL`, and the fill writes a title whenever
a model answered at all -- the model's, or the Hub's from the body's first words. A checkpoint is
left NULL only when no model could be reached (no checkpoint runner, a spent budget, a CLI that
never answered), which is the spec's "returns to awaiting the fill": the next start tries it again
and sends nothing that already has a title. One checkpoint failing, however it fails, is logged
and the pass goes on to the next.

**One at a time.** About a hundred checkpoints on the operator's Hub; asking them in sequence keeps
the spend to one cheap call in flight and the database to one writer for this pass.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select

from .checkpoint_generation import (
    CheckpointTitle,
    GenerationAnswer,
    apply_title,
    ask_for_checkpoint,
    plain_text,
)
from .checkpoint_trigger import _resolve_runner
from .db.engine import async_session_factory
from .db.models import Checkpoint, Project

logger = logging.getLogger(__name__)

#: Bumped whenever the prompt changes, for the reason `CHECKPOINT_PROMPT_VERSION` is.
FILL_PROMPT_VERSION = "checkpoint-title-fill/1"
#: Recorded on each `WorkerInvocation`, so the fill's spend reads apart from generation's.
FILL_KIND = "checkpoint_title_fill"
#: The first pass waits this long, so it does not join the startup burst of reconciliation and
#: re-drained queues (the same reason as `db_maintenance.FIRST_PASS_DELAY_SECONDS`).
FIRST_PASS_DELAY_SECONDS = 60.0
#: A body longer than this is cut before it is sent; its opening is what a title is about.
_BODY_CHAR_LIMIT = 60_000

_FILL_PROMPT = """\
Below is a checkpoint describing a software conversation, written so that another agent could \
pick the work up. Give it a title and a summary, so that it can be told apart from others in a \
list.

Reply with a single JSON object and nothing else, matching exactly:
{{
  "title": string,
  "summary": string
}}

Rules:
- "title" is required: at most 8 words and 60 characters, saying what this conversation did.
- "summary" is required: at most two sentences and 300 characters.
- An answer without a title or a summary, or with either over its limit, is rejected; it is not \
shortened for you.
- Write only from the checkpoint below. Do not invent a fact you cannot see in it.
{rejection_section}
--- checkpoint ---
{body}
--- end ---"""

_REJECTION_SECTION = """
Your previous answer was rejected: {reason}. Reply again with the whole JSON object, correcting \
that.
"""


def build_fill_prompt(body: str, rejection: Optional[str] = None) -> str:
    section = _REJECTION_SECTION.format(reason=rejection) if rejection else ""
    return _FILL_PROMPT.format(rejection_section=section, body=body[:_BODY_CHAR_LIMIT])


@dataclass
class FillReport:
    """What one pass did, by outcome. `awaiting` were left for the next start."""

    filled: int = 0
    awaiting: int = 0
    failed: int = 0


async def _unfilled(started_at: datetime) -> List[str]:
    """The checkpoints awaiting the fill, oldest first. Only those taken before this pass began:
    a checkpoint generation is still writing has its title written by generation, not here."""
    async with async_session_factory() as db:
        rows = await db.execute(
            select(Checkpoint.id)
            .where(Checkpoint.title.is_(None), Checkpoint.created_at <= started_at)
            .order_by(Checkpoint.sequence)
        )
        return list(rows.scalars().all())


async def fill_one(checkpoint_id: str) -> bool:
    """Give one checkpoint its title and summary. True when it now has them; False when no model
    could be reached and it waits for the next start."""
    async with async_session_factory() as db:
        checkpoint = (
            await db.execute(select(Checkpoint).where(Checkpoint.id == checkpoint_id))
        ).scalar_one_or_none()
        if checkpoint is None or checkpoint.title is not None:
            return True
        body = checkpoint.body or ""
        text = plain_text(body)
        if not text:
            # Nothing written to read: the Hub's facts are all there is, and no model is asked.
            apply_title(
                checkpoint,
                GenerationAnswer(reason="the checkpoint has no written body to read"),
                fallback_text="",
            )
            await db.commit()
            return True
        project = await db.get(Project, checkpoint.project_id)
        cli, model, runner_id = (
            await _resolve_runner(db, project) if project is not None else (None, None, None)
        )
        project_id, conversation_id = checkpoint.project_id, checkpoint.conversation_id
        # Let go of the read transaction before spawning: F89, as `generate_checkpoint` explains.
        await db.commit()

    if cli is None:
        logger.info(
            "checkpoint %s awaits the title fill: project %s has no checkpoint runner",
            checkpoint_id,
            project_id,
        )
        return False

    answer = await ask_for_checkpoint(
        project_id=project_id,
        conversation_id=conversation_id,
        prompt_for=lambda rejection: build_fill_prompt(body, rejection),
        cli=cli,
        model=model,
        runner_id=runner_id,
        initiator="autonomous",
        kind=FILL_KIND,
        output_model=CheckpointTitle,
        prompt_version=FILL_PROMPT_VERSION,
    )
    if not answer.answered:
        logger.info(
            "checkpoint %s awaits the title fill: no model was reached (%s)",
            checkpoint_id,
            answer.reason,
        )
        return False

    async with async_session_factory() as db:
        checkpoint = (
            await db.execute(select(Checkpoint).where(Checkpoint.id == checkpoint_id))
        ).scalar_one_or_none()
        if checkpoint is None or checkpoint.title is not None:
            return True
        apply_title(checkpoint, answer, fallback_text=text)
        await db.commit()
    return True


async def fill_untitled_checkpoints() -> FillReport:
    """One pass over every checkpoint awaiting the fill. One failure never stops the rest."""
    report = FillReport()
    for checkpoint_id in await _unfilled(datetime.now(timezone.utc)):
        try:
            if await fill_one(checkpoint_id):
                report.filled += 1
            else:
                report.awaiting += 1
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- the next checkpoint, and the next start, try again
            report.failed += 1
            logger.warning("could not fill checkpoint %s's title", checkpoint_id, exc_info=True)
    if report.filled or report.awaiting or report.failed:
        # WARNING for the reason `main._log_database_before_opening` gives: INFO never reaches
        # the operator after `init_db()`'s logging configuration.
        logger.warning(
            "Checkpoint title fill: %d filled, %d awaiting a reachable model, %d failed",
            report.filled,
            report.awaiting,
            report.failed,
        )
    return report


async def run_fill() -> None:
    """What `main.lifespan` starts: one pass, after the startup burst."""
    await asyncio.sleep(FIRST_PASS_DELAY_SECONDS)
    try:
        await fill_untitled_checkpoints()
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 -- a background pass must never take the Hub down
        logger.warning(
            "The checkpoint title fill stopped; the next start resumes it", exc_info=True
        )
