"""Acceptance-drive baseline for `the-side-panel-s-running-tab-...` task SPSRT-1 (FR-2, FR-4).

Not collected by the suite (no `test_` prefix); run by path against the PRE-build code (59333db,
before `GET /project/builds`), borrowing the seed from the route test:

    cp hub/tests/test_the_running_tab_lists_every_build.py <pre-build tree>/hub/tests/
    cp hub/tests/drive_baseline_running_builds.py <pre-build tree>/hub/tests/
    py -3.11 -m pytest hub/tests/drive_baseline_running_builds.py -q -s

It seeds a flow build with its loop, a lead build with an open blocking question, a finished and a
stopped build, then reads every project-scoped route that existed and asserts that SOME single read
carries what the Running tab needs. Each check reaches its assertion (the routes answer 200) and
fails there. It does not hit the new route: a 404 would be "not reached".

ac-stall is deliberately not here: the Hub's stall reason is already on `GET /loops` and the
Running model already turns it into a Needs-you row, so it has no failing data-side check; its
live wiring is SPSRT-2's.
"""

import pytest

from .test_the_running_tab_lists_every_build import P, _seed

READS = ("loops", "documents", "spec", "reopening-warnings", "project/builds")


async def _reads(app, auth_headers) -> dict:
    out = {}
    for name in READS:
        response = await app.get(f"/api/v1/projects/{P}/{name}", headers=auth_headers)
        out[name] = response.text if response.status_code == 200 else None
    return out


def _report(key: str, reached: bool, failed: bool, detail: str) -> None:
    print(
        f"check {key}: reached={'yes' if reached else 'no'} "
        f"failed_at_assertion={'yes' if failed else 'no'} -- {detail}"
    )


@pytest.mark.asyncio
async def test_baseline(app, auth_headers):
    await _seed()
    reads = await _reads(app, auth_headers)
    answered = {k: v for k, v in reads.items() if v is not None}
    titles = ("A flow build", "A lead build", "A finished build", "A build stopped early")

    once = [k for k, v in answered.items() if all(t in v for t in titles)]
    _report("ac-once", bool(answered), not once, "no single project read lists the four builds")

    ended = [k for k, v in answered.items() if "build-done" in v and "build-early" in v]
    _report(
        "ac-ended-builds",
        bool(answered),
        not ended,
        "no read lists ended builds with when they ended",
    )

    asked = [k for k, v in answered.items() if "Which database?" in v and "build-lead" in v]
    _report("ac-question", bool(answered), not asked, "no read ties a build to its open question")

    assert not once, once
