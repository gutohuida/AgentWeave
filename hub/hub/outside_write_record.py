"""What a run wrote outside its own workspace: recorded once per destination, as it happens.

`workspace_writes` answers *where a declared path landed*. This module answers *what the Hub does
about it* — one durable record on the `Run` row, one activity event for the operator, and neither
of them ever able to end the turn that produced them.

**One recorder, two sinks.** `_flush_line` (Claude, and Codex over `exec`) and `_on_event` (the
Codex app-server transport, which never reaches `_flush_line`) both hand their events here. That
is why this is a module rather than logic inside either sink: two sinks classifying for themselves
would grow two opinions about what counts as outside, and only one of the two would be the one
anybody tested.

**Written on first sight, never swept at the run boundary** (design D5, round 3). The precedent
this change's own design cites — `turn_produced_nothing` — is emitted from `evaluate_run_end`, and
copying that *timing* would lose the entire record for a run that is killed or whose Hub restarts,
which is exactly the population of runs whose stray writes matter most. So each destination is
written the moment it is first seen, in one transaction with its event. The only thing a killed run
loses is the exact per-destination call count, which `flush` refreshes best-effort at the end.

**`NULL` and `[]` mean different things, and `watch` is what makes that true.** `Run
.outside_workspace_writes` is documented as `NULL` = *not observed* and `[]` = *observed, and
nothing left the workspace*. Recording only on first sight would leave every clean run `NULL` and
make `[]` unreachable, so `watch` writes `[]` at the start of a run the classifier can actually
answer for. A run it cannot answer for — no recorded workspace directory, or one that will not
resolve — is deliberately left `NULL`, because nobody *was* looking.

Nothing here is allowed to raise into a turn (task 4.6). A run that dies because a path could not
be classified is a worse outcome than one that wrote outside unnoticed, so every entry point
swallows and logs, on the same explicit terms `mcp_server._report_decision` sets out.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Set

from .db.engine import async_session_factory
from .db.models import Run
from .utils import persist_event
from .workspace_writes import WriteLocation, can_classify, classify

logger = logging.getLogger(__name__)

#: The operator's notice, once per distinct destination per run (design D5, task 4.5). Not a
#: refusal and not required to be one: `persist_event` carries 44 distinct event types in the
#: shipped Hub and exactly one of them is a refusal, so `agent-run-sandboxing`'s *"Only refusals
#: SHALL be recorded"* was never a constraint on this event (design D9).
EVENT_TYPE = "agent_wrote_outside_workspace"

#: At most this many distinct destinations are listed; beyond it the list ends with one overflow
#: record rather than growing (task 4.4). An unbounded column on a run that writes in a loop is a
#: column nobody can read.
MAX_DESTINATIONS = 20

#: The classifications that are not a report.
#:
#: `inside` is the ordinary case. `unknown` is the classifier saying *nobody could tell* — and an
#: entry in a column whose entries mean "this left the workspace", under an event whose name
#: asserts it, would turn that into an accusation. A run whose workspace will not resolve is left
#: unwatched by `watch` for the same reason, so `unknown` should not arrive here at all; it is
#: excluded anyway, because `classify` can also return it for an individual path.
_NOT_RECORDED = frozenset({"inside", "unknown"})


class OutsideWriteRecorder:
    """The per-run accumulator behind `Run.outside_workspace_writes`.

    One instance per run, held by whichever of the two execution paths is driving it, and used
    from that path's event sink only — which is what makes the unsynchronised dict below safe:
    each sink is awaited serially within a run, and only one of the two runs for any given run.
    This is the same shape, with the same argument, that `sequence` and `accounting_sample`
    already have as `nonlocal`s in both functions.

    **The column's JSON shape is decided here** (task 4.4), because this is the only thing that
    writes it. It is a **list**, not an object, because `[]` is load-bearing: design D5, design
    D12 and the column's own comment all spell the observed-and-clean case `[]`, and an object
    holding a list beside a count would spell it `{"writes": [], "total": 0}` and stop that being
    literally true. Each element is one destination::

        {"kind": "agent", "name": "builder", "tool": "Write",
         "path": "C:/checkouts/builder/x.py", "calls": 3}

    `kind` and `name` are `WriteLocation`'s own two fields, so a task id never reads as an oddly
    named agent. `tool` and `path` are the **first** call into that destination, raw and exactly
    as the tool declared it — the event names the same pair, so the durable record and the notice
    cannot describe different writes. `calls` is how many calls into that destination the run had
    made when this row was last written.

    "20 entries **plus a total count**" is then satisfied by a final element of a different
    shape, present only when there were more than `MAX_DESTINATIONS` of them::

        {"kind": "overflow", "destinations": 7}

    Every element carries `kind`, so there is one way to read the list and the sentinel cannot be
    mistaken for a destination.
    """

    def __init__(
        self,
        *,
        project_id: str,
        agent: str,
        run_id: str,
        workspace_dir: Optional[str],
        project_root: Optional[str],
    ) -> None:
        self._project_id = project_id
        self._agent = agent
        self._run_id = run_id
        self._workspace_dir = workspace_dir
        self._project_root = project_root
        #: Whether `classify` can answer anything but `unknown` for this run at all. Decided once,
        #: here, rather than per tool call: it is a property of the run's workspace, and a run
        #: whose workspace does not resolve would otherwise pay for a `realpath` per call to be
        #: told the same thing every time.
        self._watching = can_classify(workspace_dir)
        self._destinations: "OrderedDict[WriteLocation, Dict[str, Any]]" = OrderedDict()
        self._overflow: Set[WriteLocation] = set()

    @property
    def watching(self) -> bool:
        """Whether this run is being watched at all — `False` leaves the column `NULL`."""
        return self._watching

    async def watch(self) -> None:
        """Say on the row that this run is being watched: write `[]`.

        Called once, where the run is announced as started, so that a run which writes nothing
        outside still ends distinguishable from a run that predates the detector. See the module
        docstring — without this, `[]` is unreachable and the column's documented distinction is
        a claim nothing can satisfy.
        """
        if not self._watching:
            return
        try:
            await self._store()
        except Exception:  # noqa: BLE001 — observational; see the module docstring
            logger.warning(
                "could not mark run %s as watched for outside writes", self._run_id, exc_info=True
            )

    async def note(self, event: Any) -> None:
        """Classify one run event's declared write paths and record the ones that left.

        Takes the whole `RunEvent` rather than its paths so that both sinks pass the same thing
        and neither has to know that `write_paths` is empty for every kind but `tool_use`.
        """
        if not self._watching:
            return
        paths = getattr(event, "write_paths", ()) or ()
        if not paths:
            return
        try:
            await self._note(event, paths)
        except Exception:  # noqa: BLE001 — observational; see the module docstring
            logger.warning(
                "could not record an outside write for run %s", self._run_id, exc_info=True
            )

    async def flush(self) -> None:
        """Refresh the per-destination call counts once, as the run ends. Best-effort by design.

        Every *destination* is already on the row, written when it was first seen; this only makes
        `calls` exact. A run that is killed, or whose Hub restarts, keeps every destination it
        reached and the first path into each — the whole of the operator-facing fact — and loses
        only this. That is the one field it is safe to lose (design D5).
        """
        if not self._watching or not self._destinations:
            return
        try:
            await self._store()
        except Exception:  # noqa: BLE001 — observational; see the module docstring
            logger.warning(
                "could not finalise outside-write counts for run %s", self._run_id, exc_info=True
            )

    async def _note(self, event: Any, paths: Any) -> None:
        tool = ""
        payload = getattr(event, "payload", None)
        if isinstance(payload, dict):
            tool = str(payload.get("tool") or "")
        for path in paths:
            location = classify(
                path, workspace_dir=self._workspace_dir, project_root=self._project_root
            )
            if location.kind in _NOT_RECORDED:
                continue
            already = self._destinations.get(location)
            if already is not None:
                already["calls"] += 1
                continue
            if len(self._destinations) >= MAX_DESTINATIONS:
                # Past the bound the destination is counted and not described. No event either:
                # the twenty-first distinct destination of one run is not a fact an operator can
                # act on that the first twenty did not already tell them.
                if location in self._overflow:
                    continue
                self._overflow.add(location)
                await self._store()
                continue
            self._destinations[location] = {
                "kind": location.kind,
                "name": location.name,
                "tool": tool,
                "path": path,
                "calls": 1,
            }
            await self._store_and_announce(location, tool, path)

    def _value(self) -> List[Dict[str, Any]]:
        """The column's value as it stands. A fresh list every time, deliberately.

        `sa.JSON` does not track mutation of a value already assigned, so handing the ORM the
        same list object back after mutating it in place would write nothing.
        """
        entries = [dict(entry) for entry in self._destinations.values()]
        if self._overflow:
            entries.append({"kind": "overflow", "destinations": len(self._overflow)})
        return entries

    async def _store(self) -> None:
        async with async_session_factory() as db:
            run = await db.get(Run, self._run_id)
            if run is None:
                return
            run.outside_workspace_writes = self._value()
            await db.commit()

    async def _store_and_announce(self, location: WriteLocation, tool: str, path: str) -> None:
        """The first sighting of a destination: the durable record and the notice, together.

        One transaction for both (task 4.4b). They are two writes and not one record in two
        places — the column is the fact later reads consult, the event is what the operator sees
        — but a run row saying a write escaped while the activity log says nothing, or the
        reverse, is a disagreement about the same instant that nothing downstream could resolve.
        """
        async with async_session_factory() as db:
            run = await db.get(Run, self._run_id)
            if run is not None:
                run.outside_workspace_writes = self._value()
            await persist_event(
                db,
                self._project_id,
                EVENT_TYPE,
                {
                    "run_id": self._run_id,
                    "agent": self._agent,
                    "tool": tool,
                    "path": path,
                    "destination_kind": location.kind,
                    "destination_name": location.name,
                    "workspace_dir": self._workspace_dir,
                },
                agent=self._agent,
                severity="warn",
            )
