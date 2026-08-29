"""A before-validator that reads an alias must also consume it.

`extra="forbid"` and a `model_validator(mode="before")` that renames legacy fields are
each correct alone and dangerous together: the validator runs first, so whatever it hands
back is what `forbid` judges. If it hands back a fresh dict built only from names it knew,
an undeclared field vanishes silently -- the exact absorption F116 is about. If instead it
subtracts only the alias it *read*, a rolling upgrade that emits two names for one operand
(`tokens_used` **and** `input_tokens`) gets its survivor refused -- and two of those names
are in `agent-context-usage`'s "Legacy context compatibility", so that 422 is a breach of a
shipped requirement, not a bad payload.

The rule both validators now follow: subtract the whole legacy vocabulary, keep everything
else, and let `forbid` speak for what is genuinely undeclared.
"""

import pytest
from pydantic import ValidationError

from hub.schemas.agents import ContextUsageCreate
from hub.schemas.tasks import TaskCreate, TaskUpdate


def _refused_fields(exc: ValidationError) -> set[str]:
    return {str(error["loc"][-1]) for error in exc.errors()}


# --- ContextUsageCreate ------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"tokens_used": 1200, "tokens_limit": 200000, "wat": 1}, id="legacy-shape"),
        pytest.param(
            {
                "status": "measured",
                "source": "probe",
                "basis": "provider_context",
                "context_tokens": 1,
                "limit_tokens": 10,
                "observed_at": 1.0,
                "wat": 1,
            },
            id="modern-shape",
        ),
    ],
)
def test_an_undeclared_field_is_named_on_both_paths(body):
    """The legacy path used to absorb it; only the modern path ever refused."""
    with pytest.raises(ValidationError) as caught:
        ContextUsageCreate.model_validate(body)
    assert "wat" in _refused_fields(caught.value)


@pytest.mark.parametrize(
    "body,expected",
    [
        pytest.param(
            {"tokens_used": 1200, "tokens_limit": 200000},
            {"status": "measured", "context_tokens": 1200, "limit_tokens": 200000},
            id="tokens",
        ),
        pytest.param(
            {"context_usage": 0.4},
            {"status": "measured", "percent": 40.0},
            id="ratio",
        ),
        pytest.param(
            {"percent": 0},
            {"status": "unavailable", "context_tokens": None, "percent": None},
            id="zero-percent-degrades",
        ),
        pytest.param(
            {"tokens_used": 1200, "max_context_tokens": 200000},
            {"status": "measured", "context_tokens": 1200, "limit_tokens": 200000},
            id="max-context-tokens",
        ),
    ],
)
def test_every_legacy_shape_still_normalizes(body, expected):
    sample = ContextUsageCreate.model_validate(body)
    for field, value in expected.items():
        assert getattr(sample, field) == value, field


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {"tokens_used": 1200, "input_tokens": 1200, "tokens_limit": 200000},
            id="tokens_used+input_tokens",
        ),
        pytest.param(
            {"tokens_used": 1200, "tokens_limit": 200000, "context_limit": 200000},
            id="tokens_limit+context_limit",
        ),
        pytest.param(
            {"context_usage": 0.4, "context_usage_ratio": 0.4},
            id="context_usage+context_usage_ratio",
        ),
        pytest.param(
            {"tokens_used": 1, "tokens_limit": 10, "observed_at": 1.0, "updated_at": 1.0},
            id="observed_at+updated_at",
        ),
    ],
)
def test_a_rolling_upgrade_body_carrying_two_names_is_accepted(body):
    """A writer mid-upgrade emits the new name and the old one. `input_tokens` and
    `context_limit` are named by `agent-context-usage`'s Legacy context compatibility as
    aliases the Hub SHALL normalize, so refusing one here is a breach, not a bad body."""
    sample = ContextUsageCreate.model_validate(body)
    assert sample.status == "measured"


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"percent": 0, "warning": False, "critical": False}, id="watchdog-reset"),
        pytest.param({"agent": "someone", "tokens_limit": 200000}, id="body-repeats-the-agent"),
    ],
)
def test_the_retired_watchdog_fields_are_consumed_not_refused(body):
    """`warning` and `critical` were computed by the deleted watchdog and pushed with every
    sample; `agent` repeated the name already in the path. The validator never *read* any of
    them, so enumerating the vocabulary from what it reads missed all three -- and the first
    body here is verbatim the shape `agent-context-usage`'s "Legacy data claims zero without
    a limit" scenario is written about. It SHALL degrade, not 422."""
    assert ContextUsageCreate.model_validate(body).status == "unavailable"


def test_a_declared_field_survives_the_legacy_path():
    """`breakdown` is declared, and the fresh-dict rebuild dropped it on the legacy path.

    Asserted so the residue's side effect is a decision on the record rather than a
    surprise in a later session.
    """
    sample = ContextUsageCreate.model_validate(
        {"tokens_used": 1200, "tokens_limit": 200000, "breakdown": {"input_tokens": 10}}
    )
    assert sample.breakdown == {"input_tokens": 10}


@pytest.mark.asyncio
async def test_a_rolling_upgrade_pair_survives_the_real_route(app, auth_headers):
    """The rows above are model-level. This one goes through HTTP, because the ordering
    they depend on -- before-validator first, `forbid` second -- is a property of the
    route's own validation, and a model that validates in isolation has not proved it."""
    synced = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"rolling": {}}}},
        headers=auth_headers,
    )
    assert synced.status_code == 200, synced.text

    accepted = await app.post(
        "/api/v1/projects/proj-test/agents/rolling/context-usage",
        json={"tokens_used": 1200, "input_tokens": 1200, "tokens_limit": 200000},
        headers=auth_headers,
    )
    assert accepted.status_code in (200, 201), accepted.text

    refused = await app.post(
        "/api/v1/projects/proj-test/agents/rolling/context-usage",
        json={"tokens_used": 1200, "tokens_limit": 200000, "wat": 1},
        headers=auth_headers,
    )
    assert refused.status_code == 422, refused.text
    assert "wat" in refused.text


# --- TaskCreate / TaskUpdate -------------------------------------------------------


@pytest.mark.parametrize("model", [TaskCreate, TaskUpdate], ids=["create", "update"])
@pytest.mark.parametrize("alias", ["assigned_to", "assigned_agent"])
def test_the_canonical_name_beside_its_alias_is_accepted(model, alias):
    """`TaskCreate` stripped the aliases only when `assignee` was absent, so a body
    carrying both answered 422 naming a field the contract accepts. `TaskUpdate` never
    stripped them at all, so *every* alias body it read was refused."""
    fields = {"title": "t"} if model is TaskCreate else {}
    parsed = model.model_validate({**fields, "assignee": "canonical", alias: "legacy"})
    assert parsed.assignee == "canonical"


@pytest.mark.parametrize("model", [TaskCreate, TaskUpdate], ids=["create", "update"])
@pytest.mark.parametrize("alias", ["assigned_to", "assigned_agent"])
def test_the_alias_alone_still_names_the_assignee(model, alias):
    fields = {"title": "t"} if model is TaskCreate else {}
    parsed = model.model_validate({**fields, alias: "legacy"})
    assert parsed.assignee == "legacy"


@pytest.mark.parametrize("model", [TaskCreate, TaskUpdate], ids=["create", "update"])
def test_an_undeclared_field_is_still_named_on_a_task_body(model):
    fields = {"title": "t"} if model is TaskCreate else {}
    with pytest.raises(ValidationError) as caught:
        model.model_validate({**fields, "assigned_to": "legacy", "wat": 1})
    assert "wat" in _refused_fields(caught.value)
