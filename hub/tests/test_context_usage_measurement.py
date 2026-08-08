"""Context usage is measured from the catalog, not from two colliding events.

Section 3 of 2026-08-07-conversation-handoff-rework. The evidence this fixes: across 400 stored
samples, `codex_appserver` produced 71 complete ones and `claude` produced 329 with **zero**
usable percentage — 299 carrying tokens with no limit, 30 carrying a limit with no tokens. Claude
reports the two in different messages, so neither is a measurement on its own and the read path
returned whichever half arrived last.

The shapes below are those real ones, not invented ones.
"""

import pytest

from hub.model_catalog import context_window_for_model
from hub.output_recording import resolve_usage_limit
from hub.runner_parsing import parse_claude_line

HAIKU = "claude-haiku-4-5-20251001"


def test_the_catalog_declares_a_window_for_every_claude_model_the_hub_offers():
    """`claude-opus-5` and `claude-fable-5` were declared with no window at all, so even a
    correct merge would have left them blank."""
    for model_id in ("claude-opus-5", "claude-fable-5", "claude-sonnet-5", HAIKU):
        assert context_window_for_model(model_id), model_id


def test_a_dated_snapshot_resolves_to_its_family():
    """Providers report dated ids the catalog may hold undated. A window that is right for the
    family beats no window; an unknown model still returns None rather than a guess."""
    assert context_window_for_model("claude-opus-5-20260901") == context_window_for_model(
        "claude-opus-5"
    )
    assert context_window_for_model("opus") == context_window_for_model("claude-opus-5")
    assert context_window_for_model("some-model-nobody-declared") is None
    assert context_window_for_model("") is None


def test_a_claude_assistant_line_now_carries_its_model():
    """The enabling change: without the model on the sample there is nothing to look up."""
    line = (
        '{"type":"assistant","session_id":"s1","message":{"model":"'
        + HAIKU
        + '","content":[{"type":"text","text":"hi"}],'
        '"usage":{"input_tokens":1000,"cache_read_input_tokens":9000,'
        '"cache_creation_input_tokens":0}}}'
    )
    parsed = parse_claude_line(line)
    assert parsed.usage is not None
    assert parsed.usage.model == HAIKU
    assert parsed.usage.context_tokens == 10_000
    # Still no limit from the provider — that is the whole point.
    assert parsed.usage.limit_tokens is None


def test_the_observed_claude_shape_completes_from_the_catalog():
    """299 of the 329 unusable samples had exactly this shape."""
    resolved = resolve_usage_limit(
        {
            "status": "measured",
            "source": "claude",
            "basis": "latest_request_input",
            "context_tokens": 20_000,
            "limit_tokens": None,
            "percent": None,
            "model": HAIKU,
        }
    )
    assert resolved["limit_tokens"] == 200_000
    assert resolved["percent"] == 10.0


def test_the_limit_only_claude_shape_is_left_alone():
    """The other 30. There is no measurement here to complete — inventing a token count would be
    fabricating usage, so this stays unusable and the read path routes around it instead."""
    payload = {
        "status": "measured",
        "source": "claude",
        "basis": "latest_request_input",
        "context_tokens": None,
        "limit_tokens": 200_000,
        "percent": None,
        "model": HAIKU,
    }
    assert resolve_usage_limit(dict(payload)) == payload


def test_a_complete_codex_sample_is_untouched():
    """Codex reports its own window. A provider that knows better than the catalog keeps its
    answer — this fills gaps, it does not overwrite."""
    payload = {
        "status": "measured",
        "source": "codex_appserver",
        "basis": "provider_context",
        "context_tokens": 68_000,
        "limit_tokens": 272_000,
        "percent": 25.0,
        "model": "gpt-5.4-mini",
    }
    assert resolve_usage_limit(dict(payload)) == payload


def test_an_undeclared_model_yields_no_percentage_rather_than_a_guess():
    payload = {
        "status": "measured",
        "source": "claude",
        "basis": "latest_request_input",
        "context_tokens": 20_000,
        "model": "claude-something-unreleased",
    }
    resolved = resolve_usage_limit(dict(payload))
    assert resolved.get("limit_tokens") is None
    assert resolved.get("percent") is None


@pytest.mark.asyncio
async def test_a_claude_agent_reports_a_percentage_end_to_end(app, auth_headers):
    """The claim this section exists to make true."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"ctx-claude": {}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    resp = await app.post(
        "/api/v1/projects/proj-test/agents/ctx-claude/context-usage",
        json={
            "status": "measured",
            "source": "claude",
            "basis": "latest_request_input",
            "context_tokens": 50_000,
            "model": HAIKU,
            "session_id": "sess-a",
            "observed_at": 1000,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201

    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    row = next(item for item in resp.json() if item["name"] == "ctx-claude")
    assert row["context_usage"]["percent"] == 25.0
    assert row["context_usage"]["limit_tokens"] == 200_000


@pytest.mark.asyncio
async def test_a_later_limit_only_row_does_not_hide_the_complete_one(app, auth_headers):
    """The read-path half. Claude's end-of-turn message arrives *after* the tokens and carries
    none, so `setdefault` on the newest row reported nothing for the whole turn."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"ctx-order": {}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    complete = await app.post(
        "/api/v1/projects/proj-test/agents/ctx-order/context-usage",
        json={
            "status": "measured",
            "source": "claude",
            "basis": "latest_request_input",
            "context_tokens": 50_000,
            "model": HAIKU,
            "session_id": "sess-a",
            "observed_at": 1000,
        },
        headers=auth_headers,
    )
    assert complete.status_code == 201

    # The end-of-turn report: a window, no tokens, same session, strictly newer.
    unusable = await app.post(
        "/api/v1/projects/proj-test/agents/ctx-order/context-usage",
        json={
            "status": "unavailable",
            "source": "claude",
            "session_id": "sess-a",
            "observed_at": 2000,
        },
        headers=auth_headers,
    )
    assert unusable.status_code == 201

    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    row = next(item for item in resp.json() if item["name"] == "ctx-order")
    assert row["context_usage"]["percent"] == 25.0


@pytest.mark.asyncio
async def test_a_reset_is_not_papered_over_with_the_previous_sessions_reading(app, auth_headers):
    """The fallback is scoped to the newest row's session on purpose. A compaction starts a new
    session at low usage; reporting the pre-compaction percentage as current would be worse than
    reporting none, because it is the number the operator would act on."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"ctx-reset": {}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    await app.post(
        "/api/v1/projects/proj-test/agents/ctx-reset/context-usage",
        json={
            "status": "measured",
            "source": "claude",
            "basis": "latest_request_input",
            "context_tokens": 180_000,
            "model": HAIKU,
            "session_id": "sess-old",
            "observed_at": 1000,
        },
        headers=auth_headers,
    )
    await app.post(
        "/api/v1/projects/proj-test/agents/ctx-reset/context-usage",
        json={
            "status": "unavailable",
            "source": "claude",
            "session_id": "sess-new",
            "observed_at": 2000,
        },
        headers=auth_headers,
    )

    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    row = next(item for item in resp.json() if item["name"] == "ctx-reset")
    assert row["context_usage"]["session_id"] == "sess-new"
    assert row["context_usage"].get("percent") is None
