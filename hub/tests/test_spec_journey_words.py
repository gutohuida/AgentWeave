"""What the exploring steps ask for, and that nothing the Hub ships says "propose".

`exploring-ends-at-an-approved-plan`, task `journey-and-words`: the tasks step asks for coarse tasks
(FR-9), intake asks whether the work is already built (FR-8), the last step recommends a build with
reasons and a `spec/journey.json` naming its old name `delivery` still loads (FR-10), and no step
text, tool description, readiness message or charter tells anyone to propose a document (FR-11).
On master 1f02d86 the delivery step ends "ready for the operator to propose", the tasks step says
nothing about coarse tasks, and `delivery` is the step's only name.
"""

import ast
import json
import re
from pathlib import Path

import pytest

from hub import spec_journey

HUB = Path(__file__).parent.parent / "hub"
CHARTERS = HUB / "data" / "charters"

#: Telling someone to propose, or naming the retired phase. A "proposal" (an edit proposal at
#: `contract`/`gate` rigor) is a different, living thing and is not matched.
PROPOSE = re.compile(r"\bpropos(e|ed|es|ing|able)\b", re.IGNORECASE)
#: In a charter about something other than specs, "propose a fix" is ordinary English; proposing a
#: document or spec is what is retired.
PROPOSE_A_DOCUMENT = re.compile(
    r"\bpropos\w*\s+(?:it|the|a|this|your)?\s*(?:document|spec|specification|change)\b"
    r"|\bproposed\s+phase\b",
    re.IGNORECASE,
)


def _strings(path: Path, *, docstrings: bool) -> list:
    """Every string literal in a module (f-string parts included), docstrings only when asked."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skipped: set = set()
    if not docstrings:
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                body = node.body
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                ):
                    skipped.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skipped
    ]


def _tool_descriptions() -> list:
    """The docstring of every function `mcp_server` registers as a tool: what an agent is shown."""
    tree = ast.parse((HUB / "mcp_server.py").read_text(encoding="utf-8"))
    found = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            isinstance(d, ast.Call) and getattr(d.func, "id", "") == "_tool"
            for d in node.decorator_list
        ):
            found.append((node.name, ast.get_docstring(node) or ""))
    return found


# ---------------------------------------------------------------------------------------------
# tasks-step-text (coarse-tasks)
# ---------------------------------------------------------------------------------------------


def test_the_tasks_step_asks_for_coarse_tasks():
    text = spec_journey.duty(spec_journey.TASKS)

    assert "One task per independently demonstrable piece" in text
    assert "built by one agent" in text
    assert "`files`" in text and "`depends_on`" in text
    # Named only as what not to do.
    assert "not one task per layer" in text
    assert "one task per layer" not in text.replace("not one task per layer", "")


# ---------------------------------------------------------------------------------------------
# already-built-at-intake, recommend-a-build
# ---------------------------------------------------------------------------------------------


def test_intake_asks_whether_the_work_is_already_built():
    text = spec_journey.duty(spec_journey.INTAKE)

    assert "already built" in text and "`already_built`" in text and "commits" in text
    assert "already_built" in spec_journey.missing(spec_journey.INTAKE, {"problem": "p"}, "small")
    assert "already_built" not in spec_journey.missing(
        spec_journey.INTAKE, {"problem": "p", "already_built": {"built": False}}, "small"
    )


def test_the_last_step_recommends_a_build_with_reasons():
    text = spec_journey.duty(spec_journey.BUILD)

    assert spec_journey.marker("build") in text
    assert "recommend" in text.lower() and "`reasons`" in text
    assert "ready for the operator to approve" in text
    assert spec_journey.missing(spec_journey.BUILD, {"delivery": {"mode": "none"}}, None) == [
        "delivery.reasons"
    ]
    assert (
        spec_journey.missing(
            spec_journey.BUILD, {"delivery": {"mode": "none", "reasons": {"mode": "m"}}}, None
        )
        == []
    )


def test_a_recommended_build_keeps_its_reasons_and_refuses_an_unknown_choice():
    from hub.spec_payload import PayloadError, payload_to_dict, validate_payload
    from hub.spec_render import _delivery

    base = {"schema_version": 1, "kind": "change-spec", "title": "T"}
    reasons = {"agent": "dev wrote the module.", "reviewer": "qa reviewed the last slice."}
    payload = validate_payload(
        {**base, "delivery": {"mode": "flow", "agent": "dev", "reasons": reasons}}
    )

    assert payload_to_dict(payload)["delivery"]["reasons"] == reasons
    page = _delivery(payload)
    assert "dev wrote the module." in page and "qa reviewed the last slice." in page
    # A delivery written without reasons stores exactly as before.
    assert (
        "reasons"
        not in payload_to_dict(validate_payload({**base, "delivery": {"mode": "none"}}))["delivery"]
    )
    with pytest.raises(PayloadError):
        validate_payload({**base, "delivery": {"mode": "none", "reasons": {"budget": "x"}}})


def test_a_journey_file_naming_delivery_still_loads(tmp_path):
    """A project's `spec/journey.json` written before the rename: no invalid-journey diagnostic,
    and its steps end at `build`, with the project's appended instruction carried over."""
    document = {
        "steps": [
            {"key": "intake"},
            {"key": "requirements"},
            {"key": "requirements-and-acceptance"},
            {"key": "acceptance"},
            {"key": "approach"},
            {"key": "tasks"},
            {"key": "delivery", "append": "Name the reviewer."},
        ]
    }
    steps, problems = spec_journey.parse(document)
    assert problems == []
    assert steps.order()[-1] == "build"
    assert steps.get("build").append == "Name the reviewer."
    assert "Name the reviewer." in spec_journey.duty("delivery", steps)

    from hub.project_workspace import ProjectWorkspace

    (tmp_path / "spec").mkdir()
    (tmp_path / "spec" / "journey.json").write_text(json.dumps(document), encoding="utf-8")
    loaded = spec_journey.load(ProjectWorkspace(project_id="p", root=tmp_path, path_key="p"))
    assert loaded.diagnostics == ()
    assert loaded.order()[-1] == "build"
    assert spec_journey.next_step("small", "delivery", loaded) is None
    assert spec_journey.next_step("small", "tasks", loaded) == "build"


@pytest.mark.asyncio
async def test_setting_the_old_step_name_moves_to_build():
    from hub.db.models import SpecDocument
    from hub.spec_lifecycle import Actor

    class _Session:
        def add(self, row):
            pass

    document = SpecDocument(
        id="spdoc-x", project_id="p", path="spec/x.json", kind="change-spec", step="tasks"
    )
    move = await spec_journey.set_step(_Session(), document, "delivery", actor=Actor("operator"))

    assert move == {"from": "tasks", "to": "build"} and document.step == "build"


# ---------------------------------------------------------------------------------------------
# no-propose-words (nothing-says-propose)
# ---------------------------------------------------------------------------------------------


def test_no_step_text_says_propose():
    texts = [spec_journey.duty(step) for step in spec_journey.STEP_ORDER]
    texts += [spec_journey.ASK_TO_ADVANCE, spec_journey.removed("gone", None)]
    texts += _strings(HUB / "spec_journey.py", docstrings=False)
    found = [text for text in texts if PROPOSE.search(text)]
    assert found == []


def test_no_tool_description_says_propose():
    found = [
        (name, PROPOSE.search(text).group(0))
        for name, text in _tool_descriptions()
        if PROPOSE.search(text)
    ]
    assert _tool_descriptions(), "no tool was found: the collection is broken"
    assert found == []


def test_no_readiness_message_says_propose():
    sources = ["spec_completeness.py", "spec_service.py", "api/v1/spec.py", "launchability.py"]
    found = [
        (source, text[:80])
        for source in sources
        for text in _strings(HUB / source, docstrings=False)
        if PROPOSE.search(text) and "proposed_retired" not in text
    ]
    # The one sentence allowed to name the phase is the refusal that says it was retired, and the
    # retired route's own path, which answers that refusal.
    found = [
        (s, t)
        for s, t in found
        if "proposed phase was retired" not in t and t != "/documents/propose"
    ]
    assert found == []


def test_no_briefing_says_propose():
    from hub.api.v1 import agents

    texts = list(agents.SPEC_PHASE_DUTIES.values())
    texts += _strings(HUB / "api" / "v1" / "agents.py", docstrings=False)
    texts += _strings(HUB / "api" / "v1" / "agent_actions.py", docstrings=False)
    found = [text[:80] for text in texts if PROPOSE.search(text)]
    assert found == []


def test_no_charter_tells_anyone_to_propose_a_document():
    spec_charter = (CHARTERS / "spec.md").read_text(encoding="utf-8")
    assert not PROPOSE.search(spec_charter), PROPOSE.search(spec_charter)
    for charter in sorted(CHARTERS.glob("*.md")):
        text = charter.read_text(encoding="utf-8")
        assert not PROPOSE_A_DOCUMENT.search(text), (charter.name, PROPOSE_A_DOCUMENT.search(text))


def test_the_spec_charter_sends_questions_to_ask_user_after_approval():
    """The rule about asking in the reply or calling ask_user names approval, not proposal."""
    text = (CHARTERS / "spec.md").read_text(encoding="utf-8")

    assert "Once the\ndocument is approved, `ask_user` is the way" in text
