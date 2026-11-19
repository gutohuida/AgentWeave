"""Confirm a document's acceptance criteria, as an agent does before the operator approves it
(`existing-behaviour-is-caught-before-the-build` D3, D4).

Approval is refused while any criterion of a change document has no current confirmation, so a
test that approves one confirms its criteria first. Each criterion is confirmed with the kind its
guard flag says (a guard as `guard`, every other as `new`), through `spec_criterion_confirmations
.confirm`, the function the agent's `confirm-criteria` route calls; the route itself is tested in
`test_criterion_confirmations.py`.
"""

from hub import project_workspace, spec_criterion_confirmations, spec_lifecycle, spec_service
from hub.db.engine import async_session_factory

HELPER_AGENT = "claude-1"


async def confirm_all_in(session, workspace, document, *, by: str = HELPER_AGENT) -> dict:
    """Confirm every criterion of `document` in `session`, which the caller commits.

    A document that is not exploring is left as it is: confirming is refused there, and its
    approval is refused for its own reason (already approved, archived), which is what such a test
    asserts."""
    if document.phase != spec_lifecycle.EXPLORING:
        return {"path": document.path, "confirmed": [], "unconfirmed": []}
    payload = spec_service._stored_payload(workspace, document)
    confirmations = [
        {"criterion": c.key, "kind": "guard" if c.guard is True else "new"}
        for c in payload.acceptance_criteria
    ]
    if not confirmations:
        return {"path": document.path, "confirmed": [], "unconfirmed": []}
    return await spec_criterion_confirmations.confirm(
        session, document, payload, confirmations, actor=by, run_id=None
    )


async def confirm_criteria(path: str, project: str = "proj-test", *, by: str = HELPER_AGENT):
    """Confirm every criterion of the document at `path`, in a session of its own."""
    async with async_session_factory() as session:
        document = await spec_lifecycle.get_document(session, project, path)
        assert document is not None, f"no document at {path}"
        workspace = await project_workspace.resolve_project_workspace(session, project)
        result = await confirm_all_in(session, workspace, document, by=by)
        await session.commit()
    # As the agent's route does: the list's cached ready_to_approve must not lag it.
    from hub.api.v1.spec import _READY_VERDICTS

    _READY_VERDICTS.clear()
    return result


def all_confirmed(payload) -> dict:
    """`spec_completeness.check`'s `confirmations` for a payload whose every criterion is
    confirmed as it now stands; `payload` is a `SpecPayload` or the dict one validates from."""
    from hub.spec_digest import digest_of_criterion
    from hub.spec_payload import SpecPayload

    if isinstance(payload, dict):
        payload = SpecPayload.model_validate(payload)
    return {c.key: digest_of_criterion(c) for c in payload.acceptance_criteria}


async def submit_confirmed(submit, app, headers, document, path: str, *args, **kwargs):
    """`submit(app, headers, document, *args, **kwargs)`, its criteria confirmed, and the same
    document submitted again: the response a confirmed document's save gives. A first save cannot
    be confirmed, since its criteria do not exist until it is stored."""
    first = await submit(app, headers, document, *args, **kwargs)
    assert first.status_code == 200, first.text
    await confirm_criteria(path)
    return await submit(app, headers, document, *args, **kwargs)
