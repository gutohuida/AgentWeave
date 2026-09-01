"""Row 9a's screen half — which phase decisions the operator can actually take.

The API half (`t_sweep_row9_documents.py`) walked all seven declared edges of the document phase
machine and found every one of them accepted. Two of those seven were added deliberately for F37:
`exploring -> archived` and `proposed -> archived`, so that a document created by mistake could be
retired instead of sitting in the corpus forever leaving a manifest warning nobody can clear.

`SpecPhaseBar.tsx` is the only component in the UI that calls `useSetSpecPhase` — measured, not
assumed: `grep -rn useSetSpecPhase hub/ui/src` names it and its own test and nothing else. So the
question a browser answers, and source alone should not be trusted for, is:

  **Standing in front of a document the Hub will let you archive, does the product offer to?**

Run: AW_HUB=... AW_KEY=... AW_PROJECT=... AW_SHOTS=<dir> py -3.11 scripts/drive/t_sweep_row9_ui.py

The project it wants is a SMALL one — five documents, one per phase. It builds them itself.
"""

import json
import os
import pathlib
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
KEY = os.environ["AW_KEY"]
PROJECT = os.environ["AW_PROJECT"]
OUT = pathlib.Path(os.environ.get("AW_SHOTS", "."))
OUT.mkdir(parents=True, exist_ok=True)
TAG = os.environ.get("AW_RUN_TAG", "ui")
A = f"/projects/{PROJECT}/project"

FAILURES = []

SEED = f"""
sessionStorage.setItem('agentweave-session', {json.dumps(json.dumps({"apiKey": KEY, "hubUrl": HUB}))});
localStorage.setItem('agentweave-selected-project', {json.dumps(PROJECT)});
"""


def check(label, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {label}" + (f" — {str(detail)[:320]}" if detail else ""))
    if not cond:
        FAILURES.append((label, str(detail)))


# ---------------------------------------------------------------------------- build the subjects
def payload(title):
    return {
        "schema_version": 1,
        "kind": "change-spec",
        "title": title,
        "summary": "A row 9a screen fixture, complete enough to be proposed.",
        "problem": "The phase bar cannot be looked at without a document in each phase.",
        "scope": {"in_scope": ["the phase bar"], "non_goals": ["everything else"]},
        "requirements": [
            {
                "key": "fr-1",
                "statement": "The phase bar MUST offer every phase decision the Hub will accept.",
                "modal": "MUST",
                "rationale": "An edge the operator cannot take is an edge that does not exist.",
            }
        ],
        "acceptance_criteria": [
            {
                "key": "ac-1",
                "requirement": "fr-1",
                "given": "a document the Hub will archive",
                "when": "the operator looks at the phase bar",
                "then": "an archive control is offered",
            }
        ],
        "tasks": [
            {
                "key": "t-1",
                "title": "Offer the decision",
                "description": "Render the control for every edge the phase machine declares.",
                "requirements": ["fr-1"],
                "reviewer": "critic",
            }
        ],
        "design": "A rendered control per declared edge.",
        "evidence": {"checked": ["nothing — a fixture"], "limits": ["describes no real software"]},
        "lifecycle": "Deleted with the fixture project.",
        "open_questions": [],
    }


def mk(stem, phase):
    path = f"spec/changes/r9ui-{TAG}-{stem}/spec.html"
    kind = "capability" if phase == "current" else "change-spec"
    c, _ = api("POST", f"{A}/documents", {"path": path, "title": f"{stem} ({phase})", "kind": kind})
    assert c == 201, f"create {stem}: {c}"
    if phase in ("current", "exploring-open"):
        return path
    if phase != "exploring-empty-closed":
        c, _ = api("PUT", f"{A}/documents/{path}/content", {"document": payload(stem)})
        assert c in (200, 201), f"content {stem}: {c}"
    c, _ = api("POST", f"{A}/documents/close-exploration?path={path}")
    assert c == 200, f"close {stem}: {c}"
    if phase in ("exploring-closed", "exploring-empty-closed"):
        return path
    c, b = api("POST", f"{A}/documents/propose?path={path}")
    assert c == 200 and not b.get("blocking"), f"propose {stem}: {c} {str(b)[:200]}"
    if phase == "proposed":
        return path
    c, _ = api("POST", f"{A}/documents/phase?path={path}&to=approved", {"reason": ""})
    assert c == 200, f"approve {stem}: {c}"
    return path


SUBJECTS = [
    ("open", "exploring-open", "exploring"),
    ("closed", "exploring-closed", "exploring"),
    ("empty", "exploring-empty-closed", "exploring"),
    ("proposed", "proposed", "proposed"),
    ("approved", "approved", "approved"),
    ("cap", "current", "current"),
]
PATHS = {}
for stem, build, want in SUBJECTS:
    PATHS[stem] = mk(stem, build)
    c, b = api("GET", f"{A}/documents")
    got = next((d["phase"] for d in b["documents"] if d["path"] == PATHS[stem]), None)
    check(f"fixture {stem!r} is in {want}", got == want, f"got {got}")

# What the Hub will actually accept for each of these, asked of the Hub and not assumed. Run
# against a THROWAWAY twin of each document so the subject the browser looks at is untouched.
ARCHIVABLE = {}
for stem, build, want in SUBJECTS:
    twin = mk(f"{stem}-twin", build)
    c, _ = api("POST", f"{A}/documents/phase?path={twin}&to=archived", {"reason": "probe"})
    ARCHIVABLE[stem] = c == 200
    print(
        f"  .. the Hub {'ACCEPTS' if c == 200 else f'refuses ({c})'} archiving a {want} document like {stem!r}"
    )

try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.goto(HUB, wait_until="domcontentloaded")
        page.evaluate(SEED)

        page.goto(f"{HUB}/?project={PROJECT}&tab=spec", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        page.screenshot(path=str(OUT / "row9-00-spec-tab.png"), full_page=True)
        # The rail's tree is collapsed on arrival, so document titles are NOT in the page text --
        # asserting on them measured the collapse, not the listing. The rail states a count instead,
        # and that is what this checks.
        rail = page.locator("aside, nav").first
        rail_text = rail.inner_text() if rail.count() else page.inner_text("body")
        # Counted off the API rather than off `PATHS`, so a second run of this file on the same
        # project -- which doubles the corpus -- still measures the rail against the truth.
        _c, _docs = api("GET", f"{A}/documents")
        real = len(_docs.get("documents") or [])
        check(
            "the Spec rail states how many documents the project has",
            str(real) in rail_text,
            f"the project has {real}; rail says {rail_text.splitlines()!r}",
        )

        for stem, _build, want in SUBJECTS:
            # Open the document by its own URL. `serializeDestination`
            # (hub/ui/src/lib/navigation.ts:291) puts the path in a `document` parameter, and a
            # full navigation is what makes the assertion below trustworthy: clicking rows in the
            # tree left the FIRST document open for every subject on the first attempt, and every
            # screen assertion then measured that one document six times.
            page.goto(
                f"{HUB}/?project={PROJECT}&tab=spec&document={quote(PATHS[stem], safe='')}",
                wait_until="domcontentloaded",
            )
            page.wait_for_timeout(3500)
            opened = True
            page.screenshot(path=str(OUT / f"row9-{stem}.png"), full_page=True)

            bar = page.locator('[data-testid="spec-phase"]')
            if bar.count() == 0:
                check(f"the phase bar is on screen for {stem!r}", False, f"opened={opened}")
                continue
            # Scoped to the phase bar itself — its parent row — never to body.
            panel = bar.locator("xpath=ancestor::div[contains(@class,'flex-col')][1]")
            text = panel.inner_text().strip()
            shown = bar.first.inner_text().strip()
            print(f"  .. {stem!r}: phase pill says {shown!r}; bar offers {text.splitlines()!r}")

            check(
                f"the phase bar states the phase for {stem!r}",
                shown == want,
                f"pill says {shown!r}",
            )

            offers_archive = "Archive" in text
            if ARCHIVABLE[stem]:
                check(
                    f"a {want} document the Hub WILL archive is offered an Archive control ({stem!r})",
                    offers_archive,
                    f"the Hub accepts the move; the bar offers only {text.splitlines()!r}",
                )
            else:
                check(
                    f"a {want} document the Hub will NOT archive is offered no Archive control ({stem!r})",
                    not offers_archive,
                    text,
                )

        real_errors = [
            e for e in console_errors if "409" not in e and "422" not in e and "404" not in e
        ]
        check("no unexplained console errors", not real_errors, str(real_errors[:3]))
        browser.close()
finally:
    print(f"\n===== ROW 9a UI: {len(FAILURES)} failing")
    for label, detail in FAILURES:
        print(f"  FAIL {label} — {detail[:220]}")
    print(f"screenshots in {OUT}")
