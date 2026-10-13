"""F537: the openspec corpus converter keeps the wrapped lines of a scenario clause.

A GIVEN/WHEN/THEN/AND bullet wrapped in the source markdown continues on an indented line. The
converter once kept only the first physical line, so `a run credential is presented to an` was
imported without its `operator API`.
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "migrate_openspec_corpus.py"


def _load():
    """Import the script by path -- `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location("migrate_openspec_corpus", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass looks its module up here
    spec.loader.exec_module(module)
    return module


mc = _load()


def test_wrapped_when_and_then_clauses_are_joined():
    body = (
        "\n"
        "- **WHEN** a project API key is presented to the agent API or a run credential is presented to an\n"
        "  operator API\n"
        "- **THEN** authentication is refused\n"
        "  and the attempt is recorded\n"
    )
    criterion, _ = mc.parse_scenario("Credentials cannot cross privilege planes", body)
    assert criterion["when"].endswith("presented to an operator API")
    assert criterion["then"] == "authentication is refused and the attempt is recorded"


def test_wrapped_and_line_joins_the_and_not_the_clause_before_it():
    body = (
        "- **GIVEN** a stopped run\n"
        "- **AND** its credential was minted\n"
        "  before the stop\n"
        "- **WHEN** the credential is used\n"
        "- **THEN** it is refused\n"
    )
    criterion, _ = mc.parse_scenario("s", body)
    assert criterion["given"] == "a stopped run its credential was minted before the stop"
    assert criterion["when"] == "the credential is used"


def test_unwrapped_clauses_and_bare_bullets_are_unchanged():
    body = "- **WHEN** x happens\n" "- **THEN** y follows\n" "- and z too\n"
    criterion, _ = mc.parse_scenario("s", body)
    assert criterion["when"] == "x happens"
    assert criterion["then"] == "y follows and z too"


def test_real_capability_scenario_is_whole(tmp_path):
    source = REPO_ROOT / "openspec" / "specs" / "agent-capability-plane" / "spec.md"
    capability = mc.parse_capability(source)
    cross = [c for c in capability.acceptance_criteria if "operator API" in (c.get("when") or "")]
    assert cross, "the wrapped WHEN clause lost its tail"
