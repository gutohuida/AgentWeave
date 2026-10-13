"""What an agent may do, as a set that can only ever be narrowed.

**Why a set and not more columns.** `can_read_checkpoints`, `can_recall` and `can_accept_evidence`
are the right idea and the reasoning beside them (`models.py:245-252`, on why checkpoint access and
recall are two flags rather than one) is the reason this module exists rather than replaces it: the
question "how finely can an operator withhold this?" has been asked three times and there are more
than three things to ask it about. Fourteen of the twenty-two agent-callable tools mutate state
today with no per-agent grant at all.

**Why an intersection.** `resolve` is the whole authority model. An agent's own set may only narrow
the project's floor, and it does so by `&`, which cannot introduce a member. So "an agent may not
widen its own authority" is not a rule anything checks — there is no arrangement of stored rows that
expresses a widened grant, because the effective set is computed at every call and never written
down. Widening is unrepresentable rather than refused.

**Why this module is pure.** No session, no models, no I/O. The seam that reads the database and
decides whether to refuse or record belongs beside the services that already refuse; this is the
vocabulary and the law, which are worth testing without a database and worth reading without one.

**Why refusals are loud, and the one case where they are not.** A capability that only refuses makes
agents worse: a bare refusal gets retried in three phrasings and then worked around. So `remedy`
names the capability, says that retrying will not help, and names `ask_user`. The exception is a
capability gating a lookup by identifier — `checkpoint_access.py:119,145` deliberately makes a denied
recall indistinguishable from not-found, because a distinguishable refusal confirms the observation
exists. An agent may learn what it may do; it may never learn what exists. `DISCLOSES_EXISTENCE`
carries that distinction so a caller cannot flatten it by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Optional

# --------------------------------------------------------------------------------------
# The vocabulary. One entry per thing an operator might reasonably withhold from one agent
# but not another. Named `<noun>.<verb>` so the set reads as a sentence in a briefing.
# --------------------------------------------------------------------------------------

MESSAGE_SEND = "message.send"
TASK_CREATE = "task.create"
TASK_TRANSITION = "task.transition"
QUESTION_ASK = "question.ask"
CHECKPOINT_WRITE = "checkpoint.write"
CHECKPOINT_READ = "checkpoint.read"
OBSERVATION_RECALL = "observation.recall"
SPEC_AUTHOR = "spec.author"
SPEC_RENAME = "spec.rename"
EVIDENCE_RECORD = "evidence.record"
EVIDENCE_ACCEPT = "evidence.accept"
JOB_SCHEDULE = "job.schedule"
AGENT_REQUEST = "agent.request"

ALL: FrozenSet[str] = frozenset(
    {
        MESSAGE_SEND,
        TASK_CREATE,
        TASK_TRANSITION,
        QUESTION_ASK,
        CHECKPOINT_WRITE,
        CHECKPOINT_READ,
        OBSERVATION_RECALL,
        SPEC_AUTHOR,
        SPEC_RENAME,
        EVIDENCE_RECORD,
        EVIDENCE_ACCEPT,
        JOB_SCHEDULE,
        AGENT_REQUEST,
    }
)

#: What a project grants unless an operator says otherwise. Everything an agent can already do today
#: without a grant, and nothing that is currently withheld — so adopting this module changes no
#: behaviour on its own. The three existing booleans stay withheld because they already are, and
#: `job.schedule` stays out because `Project.allow_agent_jobs` already defaults closed.
DEFAULT_FLOOR: FrozenSet[str] = frozenset(
    {
        MESSAGE_SEND,
        TASK_CREATE,
        TASK_TRANSITION,
        QUESTION_ASK,
        CHECKPOINT_WRITE,
        SPEC_AUTHOR,
        SPEC_RENAME,
        EVIDENCE_RECORD,
    }
)

#: Capabilities whose refusal must stay indistinguishable from not-found, because the call names an
#: identifier and a distinguishable refusal would confirm that identifier exists. See the module
#: docstring and `checkpoint_access.py:119,145`. These are disclosed ambiently — an agent is told it
#: does not hold `observation.recall` — but never in the response to a specific id.
DISCLOSES_EXISTENCE: FrozenSet[str] = frozenset({CHECKPOINT_READ, OBSERVATION_RECALL})

#: What each capability lets an agent do, in the second person, for the ambient briefing. This is the
#: feedback loop's highest-value half: an agent that knows it does not hold `job.schedule` never
#: plans around a loop it cannot create.
DESCRIPTION: Dict[str, str] = {
    MESSAGE_SEND: "send messages to other agents, which queues a turn for them",
    TASK_CREATE: "create tasks",
    TASK_TRANSITION: "move a task through its lifecycle",
    QUESTION_ASK: "ask the operator a question and wait for the answer",
    CHECKPOINT_WRITE: "record checkpoint notes",
    CHECKPOINT_READ: "read checkpoints recorded by other agents",
    OBSERVATION_RECALL: "recall another agent's recorded output verbatim",
    SPEC_AUTHOR: "create and submit specification documents",
    SPEC_RENAME: "rename a specification document",
    EVIDENCE_RECORD: "record evidence against a requirement",
    EVIDENCE_ACCEPT: "accept or reject evidence, including evidence you did not produce",
    JOB_SCHEDULE: "create, toggle or run scheduled jobs and loops",
    AGENT_REQUEST: "request a new agent from a pre-approved template",
}

#: The three booleans this vocabulary absorbs, so a migration has one place to read the mapping from
#: and a test has one place to assert it against.
LEGACY_FLAGS: Dict[str, str] = {
    "can_read_checkpoints": CHECKPOINT_READ,
    "can_recall": OBSERVATION_RECALL,
    "can_accept_evidence": EVIDENCE_ACCEPT,
}


class CapabilityRefusedError(RuntimeError):  # noqa: N818 - "refused" is the outcome, not a fault
    """This actor does not hold the capability this call needs."""

    def __init__(self, capability: str, agent: str) -> None:
        self.code = "capability_not_granted"
        self.capability = capability
        self.agent = agent
        super().__init__(remedy(capability))


def resolve(floor: Iterable[str], agent: Optional[Iterable[str]]) -> FrozenSet[str]:
    """The capabilities this agent actually holds.

    Intersection, never union: an agent's set narrows the project's floor and can never add to it.
    `None` means the agent states nothing and inherits the floor whole — the same meaning `None`
    already carries on `Agent.permission_timeout_seconds`, where a row storing today's default would
    keep saying it after the default moved.

    Members of `agent` that are not in `floor` are not an error and are not reported here. They are
    simply absent from the result, which is what makes narrowing-only structural: there is no path
    through this function that returns something `floor` does not contain.
    """
    grounded = frozenset(floor)
    if agent is None:
        return grounded
    return grounded & frozenset(agent)


def remedy(capability: str) -> str:
    """Why the call was refused and what would change it.

    Three things are load-bearing. The capability is **named**, so the refusal is about a grant
    rather than about this call. Retrying is **ruled out**, because a model given a bare refusal will
    try three more phrasings before giving up. And `ask_user` is **named**, so the agent lands in the
    escalation path that already exists instead of dead-ending. This is `requirement_gate.REMEDY`'s
    argument applied to authority: an unactionable refusal gets worked around, which is worse than
    never having refused.
    """
    does = DESCRIPTION.get(capability, "perform that action")
    return (
        f"You do not hold `{capability}`, so you cannot {does}. This is a grant you have not been "
        "given, not a temporary condition — retrying will not change it. If this task requires it, "
        "use `ask_user` to ask the operator to grant it."
    )


@dataclass(frozen=True)
class Briefing:
    """What an agent is told about its own authority at the start of a turn.

    Both halves matter and the second is the reason this exists. Withheld capabilities are named --
    not the objects they would have reached -- so an agent can plan without them rather than
    discovering them one refusal at a time.
    """

    held: List[str]
    withheld: List[str]

    def render(self) -> str:
        lines: List[str] = []
        if self.held:
            lines.append("You hold these capabilities:")
            lines.extend(f"- `{name}` — you may {DESCRIPTION[name]}." for name in self.held)
        else:
            lines.append("You hold no capabilities in this project.")
        if self.withheld:
            lines.append("")
            lines.append("You do not hold these, and calls that need them will not succeed:")
            lines.extend(f"- `{name}` — you may not {DESCRIPTION[name]}." for name in self.withheld)
            lines.append("")
            lines.append("Use `ask_user` if a task requires one of them.")
        return "\n".join(lines)


def briefing(granted: Iterable[str]) -> Briefing:
    """The ambient half of the feedback loop.

    Generalises what `api/v1/agents.py:1262` already does for `can_accept_evidence` alone: tell the
    agent, in prose, what it may do. Both lists are sorted so a turn's context is stable across runs
    and a diff of two briefings is readable.
    """
    held = frozenset(granted) & ALL
    return Briefing(held=sorted(held), withheld=sorted(ALL - held))
