"""F31 and F30: what the operator is shown must match what the system does.

F31 — redaction ate the Hub's own vocabulary. F30 — the launchability probe and the spawn
disagreed about the same agent, and the probe is the one on screen.
"""

import pytest

from hub.launchability import get_agent_config, probe_agent
from hub.runner_events import redact_secrets

# ---------------------------------------------------------------------------
# F31: redaction is bounded so it cannot consume non-secrets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "survivor",
    [
        # Measured 2026-08-25, all redacted by the old `[A-Za-z0-9_=-]{32,}` alternative.
        "spread-fairness-metric-fix-for-idle-staff",
        "mcp__agentweave__submit_spec_document",
        "mcp__agentweave__record_evidence",
        "this_is_a_perfectly_ordinary_function_name",
        # The Hub mints these itself, from a title an agent chose.
        "spec/changes/teal-manticore/spec.html",
    ],
)
def test_the_hubs_own_vocabulary_survives_redaction(survivor):
    """The operator loses precisely the identifier saying *which* document an agent read."""
    assert redact_secrets(survivor) == survivor
    assert redact_secrets({"path": survivor}) == {"path": survivor}


@pytest.mark.parametrize(
    "credential",
    [
        "aw_live_58ab7d84a1bf7b34eb2d1b424875bacd",
        "sk-ant-api03-abcdefghijklmnopqrstuvwxyz012345",
        # No recognised prefix, but hex: still a credential shape, still caught.
        "0123456789abcdef0123456789abcdef",
        "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY3ODkw",
    ],
)
def test_a_credential_is_still_redacted(credential):
    """Narrowing the third alternative must not cost the first two anything."""
    assert redact_secrets(credential) == "<redacted>"


def test_a_secret_field_name_is_still_redacted_whatever_its_value():
    assert redact_secrets({"api_key": "short"}) == {"api_key": "<redacted>"}
    assert redact_secrets({"authorization": "Bearer x"}) == {"authorization": "<redacted>"}


def test_a_credential_embedded_in_a_sentence_is_still_found():
    out = redact_secrets("the key is aw_live_58ab7d84a1bf7b34eb2d1b424875bacd ok")
    assert "aw_live_" not in out
    assert "<redacted>" in out


# ---------------------------------------------------------------------------
# F30: the probe and the spawn cannot disagree about the same agent
# ---------------------------------------------------------------------------


async def _agent(session, name, *, self_registered, runner_id=None):
    from hub.db.models import Agent

    session.add(
        Agent(
            id=f"agt-{name}",
            project_id="proj-test",
            name=name,
            self_registered=self_registered,
            runner_id=runner_id,
        )
    )
    await session.commit()


async def _runner(session, runner_id, cli="claude", model="haiku"):
    from hub.db.models import Runner

    session.add(
        Runner(id=runner_id, project_id="proj-test", name=f"{cli}-runner", cli=cli, model=model)
    )
    await session.commit()


@pytest.mark.asyncio
async def test_a_self_registered_agent_with_a_runner_reports_that_runner(app):
    """The F30 reproduction. Three agents made via `POST /agents/register` and then bound were all
    reported unlaunchable, naming a CLI after the agent itself — while triggering them worked."""
    from hub.db.engine import async_session_factory

    async with async_session_factory() as session:
        await _runner(session, "rnr-f30")
        await _agent(session, "architect", self_registered=True, runner_id="rnr-f30")

        config = await get_agent_config("proj-test", "architect", session)

    assert config["runner"] == "claude"
    assert config["model"] == "haiku"
    # The symptom: a binary named after the operator's own agent.
    verdict = probe_agent("architect", config)
    assert verdict["cli"] != "architect"


@pytest.mark.asyncio
async def test_a_self_registered_agent_with_no_runner_keeps_its_exemption(app):
    """The exemption's intent is sound and is preserved: such an agent manages its own execution
    and is not marked unbound."""
    from hub.db.engine import async_session_factory

    async with async_session_factory() as session:
        await _agent(session, "selfrun", self_registered=True)

        config = await get_agent_config("proj-test", "selfrun", session)

    assert config.get("runner") != "unbound"


@pytest.mark.asyncio
async def test_an_ordinary_agent_with_no_runner_is_still_reported_unbound(app):
    """The case the previous fix (2026-08-21) exists for, unchanged."""
    from hub.db.engine import async_session_factory

    async with async_session_factory() as session:
        await _agent(session, "norunner", self_registered=False)

        config = await get_agent_config("proj-test", "norunner", session)

    assert config["runner"] == "unbound"
    verdict = probe_agent("norunner", config)
    assert verdict["runnable"] is False
    # Never a binary named after the agent.
    assert "norunner" not in (verdict["reason"] or "")


@pytest.mark.asyncio
async def test_an_ordinary_bound_agent_is_unchanged(app):
    from hub.db.engine import async_session_factory

    async with async_session_factory() as session:
        await _runner(session, "rnr-plain", cli="codex", model="gpt-5")
        await _agent(session, "plain", self_registered=False, runner_id="rnr-plain")

        config = await get_agent_config("proj-test", "plain", session)

    assert config["runner"] == "codex"
    assert config["model"] == "gpt-5"
