"""Every HTTP request body has a contract, and the contract refuses what it cannot honour.

F116: `POST .../agent/trigger` accepted a top-level `permission_mode`, answered 200, discarded
it, and ran the agent unsupervised while the operator believed a posture had been set. The
sibling decide route refused the same mistake with a 422 that named the field. The difference
was one line of `model_config` -- which is exactly the kind of difference no reviewer notices
one model at a time. So the rule is asserted over the whole write surface at once, from the
routing table rather than from a list somebody remembered to update.

Two assertions, because a body can escape the rule two ways:

* a model that tolerates extras (`extra != "forbid"`), and
* a route with no model at all (`body: dict`), whose vocabulary is unbounded and which the
  first assertion passes over in silence.

Both exemption lists carry a reason per entry. An entry with no reason is the defect this file
is about, written down.
"""

from __future__ import annotations

import os
import typing

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel

from hub.main import create_app

# `document: Any` is deliberately tolerant, and so is the model around it:
# `agent-document-creation` requires that an unsupported document shape be *unexpressible*
# rather than merely refused, and `spec-document-authority`'s "The payload contract is
# versioned and forward compatible" requires that unrecognised fields survive a round trip
# with "no validation error raised on their account". Forbidding here would breach both.
LAX_BY_DESIGN: dict[str, str] = {
    "hub.schemas.spec.SpecDocumentCreate": (
        "agent-document-creation / spec-document-authority: the payload contract is "
        "forward compatible and unrecognised fields must survive a round trip"
    ),
}

# A route whose body is an untyped `dict` has no contract to enforce. These are named, with
# the reason they are still here, so that the count is a decision rather than an oversight.
NO_CONTRACT_BY_DESIGN: dict[str, str] = {
    "register_agent": (
        "F111 deletes this route outright -- self-registration is the watchdog-spawn contact "
        "mode's last caller and the Hub owns execution now. Giving it a model first would be "
        "work thrown away."
    ),
    "patch_agent": (
        "F116/D7: the handler guards on `body.keys()` and answers 400 for an unknown key, so "
        "the vocabulary is enforced -- but by hand, and with the wrong status. Modelling it "
        "turns those 400s into 422s across the agent UI; filed as its own finding rather than "
        "changed inside this one."
    ),
}


def _body_models(annotation: object) -> list[type[BaseModel]]:
    """Every BaseModel reachable from a body annotation, including through its fields.

    A body can be `Model`, `list[Model]`, `Model | None`, or a model whose *field* is a model
    -- and a nested model with tolerant config is just as much a hole as a top-level one. The
    nested set happens to be strict today; it will not stay that way on its own.
    """
    found: list[type[BaseModel]] = []
    seen: set[type[BaseModel]] = set()

    def walk(ann: object) -> None:
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            if ann in seen:
                return
            seen.add(ann)
            found.append(ann)
            for field in ann.model_fields.values():
                walk(field.annotation)
            return
        for arg in typing.get_args(ann):
            walk(arg)

    walk(annotation)
    return found


def _routes_with_bodies() -> list[tuple[APIRoute, object]]:
    """(route, body annotation) for every route FastAPI parses a request body for.

    `route.body_field` is FastAPI's own answer to "what is this route's body" -- derived from
    the same dependant it uses at request time. Classifying the endpoint's parameters by hand
    gets a different, wronger answer.
    """
    app = create_app()
    out = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        body_field = getattr(route, "body_field", None)
        if body_field is None:
            continue
        out.append((route, body_field.field_info.annotation))
    return out


def test_every_request_body_model_forbids_unknown_fields():
    offenders = []
    checked = 0
    for route, annotation in _routes_with_bodies():
        for model in _body_models(annotation):
            checked += 1
            qualname = f"{model.__module__}.{model.__name__}"
            if model.model_config.get("extra") == "forbid":
                continue
            if qualname in LAX_BY_DESIGN:
                continue
            offenders.append(f"{qualname} (body of {route.name} {route.path})")

    assert checked, "found no request body models at all -- the walk is broken, not the code"
    assert not offenders, (
        "these request bodies absorb unknown fields instead of naming them; inherit "
        "hub.schemas.common.RequestModel, or add the model to LAX_BY_DESIGN with a "
        "reason:\n  " + "\n  ".join(sorted(set(offenders)))
    )


def test_every_route_with_a_body_has_a_contract():
    offenders = []
    for route, annotation in _routes_with_bodies():
        if _body_models(annotation):
            continue
        if route.name in NO_CONTRACT_BY_DESIGN:
            continue
        offenders.append(f"{route.name} {sorted(route.methods)} {route.path} -> {annotation!r}")

    assert not offenders, (
        "these routes take an untyped body, so no field name is ever refused; give them a "
        "RequestModel, or add the route name to NO_CONTRACT_BY_DESIGN with a reason:\n  "
        + "\n  ".join(sorted(offenders))
    )


def test_exemptions_carry_reasons():
    """An exemption list without reasons is the silence this file exists to break."""
    for name, reason in {**LAX_BY_DESIGN, **NO_CONTRACT_BY_DESIGN}.items():
        assert reason.strip(), f"{name} is exempted with no reason"


@pytest.mark.asyncio
async def test_trigger_refuses_a_top_level_permission_mode(app, auth_headers):
    """F116's exact body.

    Posture travels in `overrides`; a top-level `permission_mode` is a field the Hub cannot
    honour, and the operator who sent it believes the run is supervised.
    """
    response = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "nobody", "message": "hello", "permission_mode": "manual"},
        headers=auth_headers,
    )
    assert response.status_code == 422, response.text
    assert "permission_mode" in response.text


def test_the_probe_sees_the_whole_write_surface():
    """A guard on the walk itself: if `body_field` ever stops resolving, both tests above
    would pass vacuously. This is the count that makes that visible."""
    assert len(_routes_with_bodies()) > 50


assert os.environ.get("DATABASE_URL"), "conftest must have configured the test database"
