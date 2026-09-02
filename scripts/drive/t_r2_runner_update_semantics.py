"""R2 of the F173 spec loop — what `PATCH /runners/{id}` actually does, measured.

Round 1 wrote the proposal. Round 2 does not re-read round 1's reasoning; it opens the code round 1
cited and asks the questions round 1 did not. Two of them turn out to matter:

  1. `update_runner` assigns `runner.name` BEFORE `_reject_undeclared_model` can raise
     (`hub/hub/api/v1/runners.py:132-141`). What does the route leave behind when it raises — a
     committed rename beside a 400, or nothing? Round 1 never asked. That class of question is what
     all three rounds missed on 2026-08-28 (F108).

  2. `_reject_undeclared_model(runner.cli, body.model)` cannot see the runner's *stored* model. So
     what happens when a caller re-submits the unrecognised model a legacy runner already carries —
     which is exactly what round 1's own task 4.4 requires the new picker to do?

Also re-measures, rather than trusting, the two claims round 1 read off the source without driving:
`flags` is clearable via `[]`, and `PATCH {"model": null}` is a no-op answered 200.

    py -3.11 scripts/drive/t_r2_runner_update_semantics.py

Creates its own fixture project against the drive Hub and deletes it again, so it never reads
AW_PROJECT and can never touch a real one. Refuses :8000 outright.

The legacy-runner case cannot be reached through the API — every write path is gated by
`_reject_undeclared_model` — so this script writes one unrecognised model directly into the fixture
runner's row, which is the pre-catalog state the shipped "Existing runners keep working" scenario is
about. Only the fixture row it created is touched, and the project is deleted afterwards.
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
KEY = os.environ.get("AW_KEY", "aw_live_58ab7d84a1bf7b34eb2d1b424875bacd")
if HUB.endswith(":8000"):
    print("REFUSING TO RUN: 8000 is the operator's real usage.")
    sys.exit(1)

# Each candidate is confirmed by looking for *this run's own runner row* in it, so a wrong guess
# is skipped rather than written to. The temp-dir database is the one the :8011 drive Hub has
# actually been served from since 2026-09-01; it is first because leaving it out is what made Q5
# silently unmeasurable on 2026-09-02 until AW_DB was passed by hand.
CANDIDATE_DBS = [p for p in [os.environ.get("AW_DB")] if p] + [
    os.path.join(tempfile.gettempdir(), "aw0901n", "aw0901n.db"),
    os.path.expanduser("~/.agentweave/hub/profiles/beta/agentweave.db"),
    os.path.join("hub", "data", "agentweave.db"),
    os.path.expanduser("~/.agentweave/hub/profiles/trial/agentweave.db"),
]

PASS, FAIL = [], []


def check(ok, label):
    (PASS if ok else FAIL).append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


def call(method, path, body=None):
    req = urllib.request.Request(
        HUB + "/api/v1" + path,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


wd = os.path.join(tempfile.gettempdir(), "r2-runner-update-fixture")
shutil.rmtree(wd, ignore_errors=True)
status, project = call("POST", "/projects/create", {"path": wd, "name": "r2-runner-update"})
if status != 201:
    print(f"could not create the fixture project: {status} {project}")
    sys.exit(1)
PID = project["id"]
print(f"fixture project {PID} at {wd}\n")

try:
    status, catalog = call("GET", "/model-catalog")
    claude_models = [
        m["id"] for p in catalog["providers"] if p["provider"] == "claude" for m in p["models"]
    ]
    print(f"catalog declares {len(claude_models)} claude models: {claude_models}\n")
    good = claude_models[0]
    other = claude_models[1] if len(claude_models) > 1 else claude_models[0]

    # ---------------------------------------------------------------- Q1
    print("Q1 — what does the route leave behind when _reject_undeclared_model raises?")
    status, runner = call(
        "POST", f"/projects/{PID}/runners", {"name": "R2 original", "cli": "claude", "model": good}
    )
    check(status == 201, f"a declared model is accepted on create ({status})")
    RID = runner["id"]

    status, body = call(
        "PATCH", f"/projects/{PID}/runners/{RID}", {"name": "R2 RENAMED", "model": "opus"}
    )
    check(status == 400, f"PATCH name+undeclared model is refused ({status}: {body})")

    status, after = call("GET", f"/projects/{PID}/runners/{RID}")
    print(f"      after the refusal: name={after['name']!r} model={after['model']!r}")
    check(
        after["name"] == "R2 original",
        "the refused PATCH left the name alone (no half-applied write)",
    )
    check(after["model"] == good, "the refused PATCH left the model alone")

    # Field order matters: name is assigned first, so the reverse order proves nothing new,
    # but a partial commit would show up here too if the session were flushed early.
    status, _ = call(
        "PATCH", f"/projects/{PID}/runners/{RID}", {"name": "R2 second try", "model": "gpt-nope"}
    )
    status2, after2 = call("GET", f"/projects/{PID}/runners/{RID}")
    check(after2["name"] == "R2 original", "a second refused PATCH also left the name alone")

    # ---------------------------------------------------------------- Q2
    print("\nQ2 — does a refused create leave a row behind?")
    status, before = call("GET", f"/projects/{PID}/runners")
    n_before = len(before)
    status, body = call(
        "POST", f"/projects/{PID}/runners", {"name": "R2 never", "cli": "claude", "model": "opus"}
    )
    check(status == 400, f"POST with an undeclared model is refused ({status})")
    status, after_list = call("GET", f"/projects/{PID}/runners")
    check(
        len(after_list) == n_before, f"no runner row was created ({n_before} -> {len(after_list)})"
    )

    # ---------------------------------------------------------------- Q3
    print("\nQ3 — is `flags` actually clearable via [] ? (round 1 read this off the source)")
    status, _ = call("PATCH", f"/projects/{PID}/runners/{RID}", {"flags": ["--verbose"]})
    status, f1 = call("GET", f"/projects/{PID}/runners/{RID}")
    check(f1["flags"] == ["--verbose"], f"flags can be set ({f1['flags']!r})")
    status, patched = call("PATCH", f"/projects/{PID}/runners/{RID}", {"flags": []})
    status, f2 = call("GET", f"/projects/{PID}/runners/{RID}")
    check(status == 200 and f2["flags"] == [], f"PATCH flags:[] clears them ({f2['flags']!r})")
    status, _ = call("PATCH", f"/projects/{PID}/runners/{RID}", {"flags": ["--verbose"]})
    status, cleared = call("PATCH", f"/projects/{PID}/runners/{RID}", {"flags": None})
    status, f3 = call("GET", f"/projects/{PID}/runners/{RID}")
    check(
        f3["flags"] == ["--verbose"],
        f"PATCH flags:null is a no-op, same shape as model ({f3['flags']!r})",
    )
    call("PATCH", f"/projects/{PID}/runners/{RID}", {"flags": []})

    # ---------------------------------------------------------------- Q4
    # Round 2 wrote this section to MEASURE F219: PATCH {"model": null} answered 200 and
    # changed nothing, so a picker's unset option would have silently done nothing. That
    # measurement is preserved in design.md and in the finding; the section now asserts what
    # the shipped requirement asks for instead ("The provider's default is a choice, and
    # clearing is honoured"), so it is a regression check rather than a record of the defect.
    print("\nQ4 — F219: the provider's default is a choice, and clearing is honoured")
    status, body = call("PATCH", f"/projects/{PID}/runners/{RID}", {"model": None})
    check(status == 200, f"PATCH model:null answers {status}")
    check(
        body.get("model") is None,
        f"...and the answer carries the model as it now stands (model={body.get('model')!r})",
    )
    call("PATCH", f"/projects/{PID}/runners/{RID}", {"model": good})
    status, body = call("PATCH", f"/projects/{PID}/runners/{RID}", {"model": ""})
    check(status == 400, f'PATCH model:"" is refused ({status})')

    # ---------------------------------------------------------------- Q5
    print("\nQ5 — a legacy runner whose stored model the catalog does not declare")
    db = None
    for cand in CANDIDATE_DBS:
        if not os.path.exists(cand):
            continue
        con = sqlite3.connect(f"file:{cand}?mode=ro", uri=True)
        try:
            row = con.execute("SELECT id FROM runners WHERE id = ?", (RID,)).fetchone()
        except sqlite3.Error:
            row = None
        con.close()
        if row:
            db = cand
            break
    if db is None:
        print("      COULD NOT IDENTIFY the database serving this Hub — Q5 not measured")
        check(False, "Q5 measured (database not found)")
    else:
        print(f"      the Hub on {HUB} serves {db}")
        con = sqlite3.connect(db)
        con.execute("UPDATE runners SET model = ? WHERE id = ?", ("claude-3-legacy-9", RID))
        con.commit()
        con.close()

        status, legacy = call("GET", f"/projects/{PID}/runners/{RID}")
        check(legacy["model"] == "claude-3-legacy-9", "the legacy model is stored")
        check(
            legacy.get("model_unrecognised") is True,
            f"the Hub marks it unrecognised ({legacy.get('model_unrecognised')!r})",
        )

        status, body = call(
            "PATCH", f"/projects/{PID}/runners/{RID}", {"name": "R2 legacy renamed"}
        )
        check(status == 200, f"renaming a legacy runner without touching model works ({status})")
        status, still = call("GET", f"/projects/{PID}/runners/{RID}")
        check(still["model"] == "claude-3-legacy-9", "...and the legacy model survives")

        print("      now the case round 1's task 4.4 requires: re-submit the stored model")
        status, body = call(
            "PATCH",
            f"/projects/{PID}/runners/{RID}",
            {"name": "R2 legacy renamed", "model": "claude-3-legacy-9"},
        )
        check(
            status == 200,
            f"saving a legacy runner UNCHANGED is accepted -- got {status}: {body}",
        )
        status, final = call("GET", f"/projects/{PID}/runners/{RID}")
        check(
            final["model"] == "claude-3-legacy-9",
            f"...and it still carries its model ({final['model']!r})",
        )

finally:
    call("DELETE", f"/projects/{PID}")
    shutil.rmtree(wd, ignore_errors=True)
    status, projects = call("GET", "/projects")
    print(
        f"\nfixture deleted; project count now {len(projects) if isinstance(projects, list) else projects}"
    )

print(f"\n{len(PASS)} passed / {len(FAIL)} failed")
for f in FAIL:
    print(f"  FAILED: {f}")
