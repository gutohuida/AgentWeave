"""F173 / F219 — what runner management's API actually accepts, measured.

Written by the F173 spec loop's round 1 (2026-09-01) rather than by a sweep. A model *picker* has
to name its unset choice out loud, so round 1 asked whether the API can honour one. It cannot, and
answers 200 anyway — filed as F219.

    py -3.11 scripts/drive/t_f219_runner_model_clear.py

Creates its own fixture project against the drive Hub and deletes it again, so it never needs
AW_PROJECT and can never touch a real one. Everything below is a call to the running Hub; nothing
is read off the source.
"""

import json
import os
import shutil
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

PASS, FAIL = [], []


def check(ok: bool, label: str) -> None:
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


wd = os.path.join(tempfile.gettempdir(), "f219-runner-model-fixture")
shutil.rmtree(wd, ignore_errors=True)
status, project = call("POST", "/projects/create", {"path": wd, "name": "f219-runner-model"})
if status != 201:
    print(f"could not create the fixture project: {status} {project}")
    sys.exit(1)
P = project["id"]
print(f"fixture project {P} at {wd}\n")

try:
    print("LEG 1 — the catalog, and what the seeded runners record")
    status, catalog = call("GET", "/model-catalog")
    declared = {p["provider"]: [m["id"] for m in p["models"]] for p in catalog["providers"]}
    check(bool(declared.get("claude")), f"claude declares models: {declared.get('claude')}")
    status, seeded = call("GET", f"/projects/{P}/runners")
    check(
        all(r["model"] is None for r in seeded) and len(seeded) >= 2,
        f"both seeded runners record no model: {[(r['name'], r['model']) for r in seeded]}",
    )

    print("\nLEG 2 — F173: an undeclared model is refused, with a sentence")
    status, refused = call("POST", f"/projects/{P}/runners", {"name": "typed", "cli": "claude", "model": "opus"})
    check(status == 400, f"POST with model 'opus' is refused — {status}")
    check(
        isinstance(refused, dict) and "is not a model" in str(refused.get("detail", "")),
        f"the refusal carries a readable sentence — {refused!r}",
    )

    print("\nLEG 3 — F219: a set model cannot be cleared, and the attempt answers 200")
    model = declared["claude"][-1]
    status, runner = call("POST", f"/projects/{P}/runners", {"name": "valid", "cli": "claude", "model": model})
    check(status == 201 and runner["model"] == model, f"a declared model is accepted — {model}")
    RID = runner["id"]

    status, patched = call("PATCH", f"/projects/{P}/runners/{RID}", {"model": None})
    check(status == 200, f"PATCH model=null answers {status}")
    check(
        patched.get("model") is None,
        f"the model is cleared — response says model={patched.get('model')!r}  <-- F219 when this fails",
    )
    status, reread = call("GET", f"/projects/{P}/runners/{RID}")
    check(
        reread.get("model") is None,
        f"and it is still cleared on re-read — model={reread.get('model')!r}  <-- F219 when this fails",
    )

    status, empty = call("PATCH", f"/projects/{P}/runners/{RID}", {"model": ""})
    check(status == 400, f"PATCH model='' is refused rather than treated as a clear — {status}")

    print("\nLEG 4 — an absent model leaves the runner's model alone (the control)")
    status, named = call("PATCH", f"/projects/{P}/runners/{RID}", {"name": "renamed"})
    check(
        status == 200 and named.get("name") == "renamed" and named.get("model") == model,
        f"PATCH name only keeps the model — {named.get('name')!r}/{named.get('model')!r}",
    )

    print("\nLEG 5 — model_unrecognised is computed and served")
    check("model_unrecognised" in runner, "RunnerResponse carries model_unrecognised")
    check(runner.get("model_unrecognised") is False, "a declared model is not flagged")
finally:
    code, _ = call("DELETE", f"/projects/{P}")
    print(f"\nfixture project deleted -> {code}")
    shutil.rmtree(wd, ignore_errors=True)

print(f"\n{len(PASS)} passed / {len(FAIL)} failed")
for label in FAIL:
    print(f"  FAILED: {label}")
