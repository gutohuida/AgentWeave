"""F1053: Check starts the vault's spec check once per content version, and never on a blocked one.

`POST /documents/check` is pressed freely while an agent edits. It used to schedule the
spec-vault-check job (a model run) on every press: for a document with a blocking gap, and again
for content the newest firing had already checked. The worker is faked as in
`test_vault_spec_check.py`, so the count of its calls is the count of model runs.
"""

import pytest

from hub import vault_spec_check

from .test_spec_documents_api import PATH, _create, _submit, run_headers  # noqa: F401
from .test_vault_spec_check import (  # noqa: F401  (worker is a fixture)
    JANUARY,
    _check,
    _enable,
    _fact,
    _firings,
    _payload,
    _requirement,
    _saved,
    _source,
    worker,
)


async def _ready_document(app, auth_headers, run_headers, tmp_path, statement: str):  # noqa: F811
    """An enabled job, one current fact, and a saved document with no blocking gap."""
    january = await _source(app, auth_headers, JANUARY, "2026-01-10")
    fact = await _fact(app, auth_headers, tmp_path, january, "Refunds up to 300 need none.")
    await _enable(app, auth_headers)
    await _create(app, auth_headers)
    await _saved(app, run_headers, _requirement("r1", statement, [fact]))
    return fact


@pytest.mark.asyncio
async def test_checking_twice_on_unchanged_ready_content_starts_one_check(
    app, auth_headers, run_headers, worker, tmp_path  # noqa: F811
) -> None:
    await _ready_document(app, auth_headers, run_headers, tmp_path, "Refunds need no approval.")
    fake = worker([], [])

    first = await _check(app, auth_headers)
    second = await _check(app, auth_headers)

    assert first["ready"] is True and second["ready"] is True
    assert first["content_version"] == second["content_version"]
    assert len(fake.calls) == 1
    firings = await _firings()
    assert len(firings) == 1
    assert firings[0]["subject"] == {
        "document": PATH,
        "content_version": first["content_version"],
    }


@pytest.mark.asyncio
async def test_checking_a_document_with_a_blocking_gap_starts_no_check(
    app, auth_headers, run_headers, worker, tmp_path  # noqa: F811
) -> None:
    await _ready_document(app, auth_headers, run_headers, tmp_path, "Refunds need no approval.")
    blocked = _payload(_requirement("r1", "Refunds need no approval."))
    blocked["tasks"][0]["depends_on"] = ["nowhere"]
    saved = await _submit(app, run_headers, blocked)
    assert saved.status_code == 200, saved.text
    assert [b["code"] for b in saved.json()["blocking"]] == ["depends_on_unresolved"]
    fake = worker([])

    checked = await _check(app, auth_headers)

    assert checked["ready"] is False
    assert fake.calls == [] and await _firings() == []


@pytest.mark.asyncio
async def test_checking_after_an_edit_starts_a_new_check(
    app, auth_headers, run_headers, worker, tmp_path  # noqa: F811
) -> None:
    fact = await _ready_document(
        app, auth_headers, run_headers, tmp_path, "Refunds need no approval."
    )
    fake = worker([], [], [])

    first = await _check(app, auth_headers)
    await _saved(app, run_headers, _requirement("r1", "Refunds need a manager's approval.", [fact]))
    second = await _check(app, auth_headers)
    third = await _check(app, auth_headers)

    assert first["content_version"] != second["content_version"] == third["content_version"]
    assert len(fake.calls) == 2
    assert [f["subject"]["content_version"] for f in await _firings()] == [
        first["content_version"],
        second["content_version"],
    ]


@pytest.mark.asyncio
async def test_a_firing_with_no_recorded_version_never_matches(
    app, auth_headers, run_headers, worker, tmp_path  # noqa: F811
) -> None:
    """A firing recorded before the version was kept (or by another trigger) is not a match: the
    next Check runs once, and records the version."""
    await _ready_document(app, auth_headers, run_headers, tmp_path, "Refunds need no approval.")
    fake = worker([], [])
    await vault_spec_check.check_in_background(
        "proj-test", PATH, trigger=vault_spec_check.REQUESTED
    )
    assert len(fake.calls) == 1 and "content_version" not in (await _firings())[0]["subject"]

    await _check(app, auth_headers)
    await _check(app, auth_headers)

    assert len(fake.calls) == 2
