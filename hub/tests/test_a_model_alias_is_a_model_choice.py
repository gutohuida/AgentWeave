"""a-model-alias-is-a-model-choice — a declared alias is accepted wherever a model id is, and a
runner keeps it as written (D1/D2 of the change's design.md).
"""

from unittest.mock import patch

import pytest

from hub.model_catalog import get_provider, undeclared_model_reason, validate_overrides
from hub.runner_commands import build_command
from hub.worker import model_is_declared

P = "/api/v1/projects/proj-test"
ALIAS = "opus"
OPUS_ID = next(m.id for m in get_provider("claude").models if ALIAS in m.aliases)


# --- test 1: every door accepts the alias, and stores it as written -------------------------------


@pytest.mark.asyncio
async def test_post_runners_accepts_the_alias_and_stores_it_as_written(app, auth_headers):
    created = await app.post(
        P + "/runners",
        json={"name": "r-alias", "cli": "claude", "model": ALIAS},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["model"] == ALIAS


@pytest.mark.asyncio
async def test_post_agents_accepts_the_alias_and_stores_it_as_written(app, auth_headers):
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        created = await app.post(
            P + "/agents",
            json={"name": "a-alias", "provider": "claude", "model": ALIAS},
            headers=auth_headers,
        )
    assert created.status_code == 201, created.text
    runner_id = created.json()["runner_id"]
    runner = await app.get(f"{P}/runners/{runner_id}", headers=auth_headers)
    assert runner.json()["model"] == ALIAS


@pytest.mark.asyncio
async def test_patch_runners_accepts_the_alias_and_stores_it_as_written(app, auth_headers):
    created = await app.post(
        P + "/runners",
        json={"name": "r-declared", "cli": "claude", "model": "claude-sonnet-5"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    runner_id = created.json()["id"]

    patched = await app.patch(
        f"{P}/runners/{runner_id}", json={"model": ALIAS}, headers=auth_headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["model"] == ALIAS


def test_validate_overrides_accepts_the_alias_and_passes_it_through_unchanged():
    accepted, rejection = validate_overrides("claude", {"model": ALIAS})
    assert rejection is None
    assert accepted == {"model": ALIAS}


def test_worker_model_is_declared_accepts_the_alias():
    assert model_is_declared("claude", ALIAS) is True


# --- test 2: the alias reaches argv exactly as stored ----------------------------------------------


def test_build_command_passes_the_alias_as_written():
    cmd = build_command(runner="claude", cli="claude", prompt="hi", model=ALIAS)
    assert "--model" in cmd
    assert cmd[cmd.index("--model") + 1] == ALIAS


# --- test 3: an alias-stored runner is not flagged unrecognised ------------------------------------


@pytest.mark.asyncio
async def test_a_runner_stored_as_an_alias_is_not_unrecognised(app, auth_headers):
    created = await app.post(
        P + "/runners",
        json={"name": "r-alias-2", "cli": "claude", "model": ALIAS},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["model_unrecognised"] is False

    fetched = await app.get(f"{P}/runners/{created.json()['id']}", headers=auth_headers)
    assert fetched.json()["model_unrecognised"] is False


# --- test 4: the refusal names the aliases among what would be accepted ---------------------------


def test_the_refusal_lists_aliases_among_what_would_be_accepted():
    reason = undeclared_model_reason("claude", "claude-opus-9")
    assert "is not a model 'claude' declares" in reason
    assert ALIAS in reason
    assert OPUS_ID in reason


@pytest.mark.asyncio
async def test_an_unknown_model_is_still_refused(app, auth_headers):
    refused = await app.post(
        P + "/runners",
        json={"name": "r-bad", "cli": "claude", "model": "claude-opus-9"},
        headers=auth_headers,
    )
    assert refused.status_code == 400, refused.text
    assert ALIAS in refused.json()["detail"]


# --- naming: an alias-found-or-created runner names the alias, not its current target --------------


@pytest.mark.asyncio
async def test_an_alias_created_runner_is_named_for_the_alias_not_its_target(app, auth_headers):
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        created = await app.post(
            P + "/agents",
            json={"name": "a-alias-name", "provider": "claude", "model": ALIAS},
            headers=auth_headers,
        )
    assert created.status_code == 201, created.text
    runner_id = created.json()["runner_id"]
    runner = await app.get(f"{P}/runners/{runner_id}", headers=auth_headers)
    assert runner.json()["name"] == f"Claude Code — {ALIAS} (latest)"
