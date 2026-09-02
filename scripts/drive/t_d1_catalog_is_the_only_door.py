"""D-1, 2026-09-02 (day window) — an INDEPENDENT re-drive of
`runner-model-is-chosen-from-the-catalog`, plus the question the research candidate raised.

Why it exists beside `t_n3_runner_model_picker_ui.py` and
`t_n4_runner_refusal_reaches_the_operator.py` rather than replacing them: those two were written by
the change's own author, in the same sitting as the code, and they transcribe the shipped UI's
predicates into Python. If the transcription errs in the same direction as the code, both agree and
the drive passes. This one starts from the *specification* and from `GET /model-catalog`, and never
reads the component's source for what to assert.

It drives the **served bundle** on the Hub's own port — no Vite dev server in the loop — because
that is what an operator loads.

Three questions, in the order the day window's `next_action` named them:

  A. does the model picker offer the catalog's models, and only those?
     (runner-registry: "Runner management offers declared models")
  B. does a refusal reach the screen? — F173, retired last night on its author's own drive.
     Re-derived here from a refusal an operator can actually *cause* from the screen, not one
     injected onto the wire.
  C. does the `<Select>` turn a stale catalog into a hard wall? Enumerate every operator-reachable
     route that sets a model and ask whether any of them accepts one the catalog does not declare.
     Then measure the catalog against the provider's own live model list.

Run:  py -3.11 scripts/drive/t_d1_catalog_is_the_only_door.py

Creates its own fixture project and deletes it. Refuses :8000 outright. No agent turn is triggered,
so nothing binds a model and nothing spends tokens.
"""

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
UI = os.environ.get("AW_UI", HUB)
KEY = os.environ.get("AW_KEY", "aw_live_n0901aaaaaaaaaaaaaaaaaaaaaaaaaaaa")
if HUB.endswith(":8000") or UI.endswith(":8000"):
    print("REFUSING TO RUN: 8000 is the operator's real usage.")
    sys.exit(1)

FIXTURE_DIR = os.path.join(os.path.expanduser("~"), "Documents", "drive-0902-d1")
SHOTS = os.path.join(tempfile.gettempdir(), "d1-shots")
os.makedirs(SHOTS, exist_ok=True)

PROVIDER_LABELS = {}
PASS, FAIL = [], []


def check(ok, label):
    (PASS if ok else FAIL).append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


def call(method, path, body=None):
    url = HUB + "/api/v1" + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + KEY)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def main():
    code, catalog = call("GET", "/model-catalog")
    if code != 200:
        print(f"catalog unreadable [{code}] {catalog}")
        return 2
    declared = {p["provider"]: [m["id"] for m in p["models"]] for p in catalog["providers"]}
    labels = {
        p["provider"]: {m["id"]: m["label"] for m in p["models"]} for p in catalog["providers"]
    }
    defaults = {
        p["provider"]: next((m["id"] for m in p["models"] if m.get("default")), None)
        for p in catalog["providers"]
    }
    PROVIDER_LABELS.update({p["provider"]: p["label"] for p in catalog["providers"]})
    print(f"catalog: { {k: len(v) for k, v in declared.items()} }, defaults={defaults}")

    code, proj = call(
        "POST", "/projects/open", {"path": FIXTURE_DIR.replace("\\", "/"), "name": "drive-0902-d1"}
    )
    if code != 200:
        print(f"could not open fixture project [{code}] {proj}")
        return 2
    pid = proj["id"]
    print(f"fixture project {pid}")

    try:
        drive(pid, declared, labels, defaults)
    finally:
        dcode, _ = call("DELETE", f"/projects/{pid}")
        ccode, rest = call("GET", "/projects")
        print(f"\ncleanup: DELETE [{dcode}], projects now {len(rest) if ccode == 200 else '?'}")
        check(dcode in (200, 204), "the fixture project is deleted")
        check(ccode == 200 and not any(p["id"] == pid for p in rest), "and no longer listed")

    print(f"\n{len(PASS)} passed / {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


def drive(pid, declared, labels, defaults):
    # ------------------------------------------------------------------ C, API half
    # Every operator-reachable route that can set a runner's model, asked to set one the catalog
    # does not declare. The spec says the Hub refuses these; the question here is whether *any*
    # door is left open, because the UI select closed the only one that used to be soft.
    print("\nC(api) — is any operator-reachable route able to set an undeclared model?")
    doors = []

    code, body = call(
        "POST",
        f"/projects/{pid}/runners",
        {"name": "D1 New", "cli": "claude", "model": "claude-fable-5-1"},
    )
    doors.append(("POST /runners", code, body))
    check(code == 400, f"POST /runners refuses an undeclared model [{code}]")

    code, seed = call(
        "POST", f"/projects/{pid}/runners", {"name": "D1 Seed", "cli": "claude", "model": None}
    )
    check(code == 201, f"a runner with no model is accepted [{code}]")
    rid = seed["id"] if code == 201 else None

    if rid:
        code, body = call("PATCH", f"/projects/{pid}/runners/{rid}", {"model": "claude-fable-5-1"})
        doors.append(("PATCH /runners", code, body))
        check(code == 400, f"PATCH /runners refuses an undeclared model [{code}]")

    code, body = call(
        "POST",
        f"/projects/{pid}/agents",
        {"name": "d1probe", "provider": "claude", "model": "claude-fable-5-1"},
    )
    doors.append(("POST /agents", code, body))
    check(code == 400, f"POST /agents refuses an undeclared model [{code}]")

    open_doors = [d for d in doors if d[1] < 400]
    check(
        not open_doors,
        f"no operator-reachable route accepts an undeclared model (tried {len(doors)})",
    )
    print(f"    doors tried: {[(d[0], d[1]) for d in doors]}")

    # ------------------------------------------------------------------ B, the refusal's words
    # F173's own sequence is unreachable now (no free-text field), so the refusal used here is one
    # an operator can still *cause* from the Runners dialog. Two candidates, established on the
    # wire first so the browser half knows what sentence to look for:
    #
    #   1. a duplicate runner name — MEASURED ACCEPTED (201). `ix_runners_project_name` is a plain
    #      index, not unique, so this refuses nothing and cannot serve.
    #   2. a name longer than `RunnerCreate.name`'s max_length=256 — a Pydantic 422 whose `detail`
    #      is a *list*, which is exactly the body shape task 3.1's `readableApiError` swap exists
    #      for, and which the deleted local helper returned raw.
    print("\nB(api) — a refusal an operator can still cause from the Runners screen")
    code, dup = call(
        "POST", f"/projects/{pid}/runners", {"name": "D1 Seed", "cli": "claude", "model": None}
    )
    print(f"    duplicate name -> [{code}] {json.dumps(dup)[:160]}")
    check(True, f"duplicate runner name answered [{code}] (recorded, not asserted)")

    long_name = "L" * 300
    code, longbody = call(
        "POST", f"/projects/{pid}/runners", {"name": long_name, "cli": "claude", "model": None}
    )
    print(f"    300-character name -> [{code}] {json.dumps(longbody)[:260]}")
    over_length_refused = code >= 400
    detail_is_list = isinstance(longbody, dict) and isinstance(longbody.get("detail"), list)
    check(over_length_refused, f"an over-length runner name is refused [{code}]")
    check(
        detail_is_list,
        "and its detail is a Pydantic list — the body readableApiError exists to render",
    )

    # ------------------------------------------------------------------ the browser
    seed_js = f"""
sessionStorage.setItem('agentweave-session', {json.dumps(json.dumps({"apiKey": KEY, "hubUrl": ""}))});
localStorage.setItem('agentweave-selected-project', {json.dumps(pid)});
"""
    url = f"{UI}/?project={pid}&tab=environment&section=runners"

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(seed_js)
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(4500)
        page.screenshot(path=os.path.join(SHOTS, "d1-01-runners.png"))

        # -------------------------------------------------------------- A
        print("\nA — the picker offers the catalog's models, and only those")
        page.get_by_role("button", name="New Runner").first.click()
        page.wait_for_timeout(700)
        page.screenshot(path=os.path.join(SHOTS, "d1-02-new-runner.png"))

        selects = page.locator("div[role='dialog'] select, select")
        n = selects.count()
        print(f"    {n} select(s) in the dialog")

        def options_of(sel):
            return sel.evaluate("s => Array.from(s.options).map(o => [o.value, o.textContent])")

        cli_sel = model_sel = None
        for i in range(n):
            s = selects.nth(i)
            vals = [v for v, _ in options_of(s)]
            if set(vals) >= set(declared.keys()):
                cli_sel = s
            elif any(v in sum(declared.values(), []) for v in vals) or "" in vals:
                model_sel = s
        check(cli_sel is not None, "a CLI select is on screen")
        check(model_sel is not None, "a model select is on screen")

        # No free-typed model field. The Name field is a text input and must stay, so this asks
        # specifically whether any text input is the *model* one.
        texts = page.locator(
            "div[role='dialog'] input[type='text'], div[role='dialog'] input:not([type])"
        )
        placeholders = [
            texts.nth(i).get_attribute("placeholder") or "" for i in range(texts.count())
        ]
        print(f"    text inputs in the dialog: {placeholders}")
        check(
            not any("model" in (p or "").lower() for p in placeholders)
            and not any("sonnet" in (p or "").lower() for p in placeholders),
            "no free-typed model field is presented",
        )

        for provider in declared:
            if cli_sel is None or model_sel is None:
                break
            cli_sel.select_option(provider)
            page.wait_for_timeout(400)
            opts = options_of(model_sel)
            values = [v for v, _ in opts]
            texts_ = [t.strip() for _, t in opts]
            expected = [""] + declared[provider]
            check(
                values == expected,
                f"{provider}: the select offers exactly Provider default + "
                f"{len(declared[provider])} declared models",
            )
            if values != expected:
                print(f"      offered: {values}\n      expected: {expected}")
            check(
                model_sel.input_value() == "",
                f"{provider}: choosing the CLI leaves the model UNSET (provider default)",
            )
            missing = [
                labels[provider][m] for m in declared[provider] if labels[provider][m] not in texts_
            ]
            check(not missing, f"{provider}: every declared model is offered by its label")
        page.screenshot(path=os.path.join(SHOTS, "d1-03-codex-models.png"))

        # -------------------------------------------------------------- B
        print("\nB — a refusal an operator causes from the screen reaches the screen")
        if cli_sel is not None:
            cli_sel.select_option("claude")
            page.wait_for_timeout(300)
        name_box = page.locator(
            "div[role='dialog'] input[type='text'], div[role='dialog'] input:not([type])"
        ).first
        name_box.fill(long_name)
        page.wait_for_timeout(300)
        typed = name_box.input_value()
        print(f"    the field accepted {len(typed)} of the {len(long_name)} characters typed")
        check(
            len(typed) > 256,
            "the name field does not itself cap the value, so the refusal is operator-reachable",
        )
        save = page.get_by_role("button", name="Save").first
        check(save.is_enabled(), "Save is enabled")
        save.click()
        page.wait_for_timeout(3000)
        page.screenshot(path=os.path.join(SHOTS, "d1-04-after-save.png"))

        alerts = page.locator("div[role='dialog'] [role='alert']")
        alert_text = " | ".join(
            (alerts.nth(i).inner_text() or "").strip() for i in range(alerts.count())
        )
        dialog_open = page.locator("div[role='dialog']").count() > 0
        print(f"    dialog still open: {dialog_open}")
        print(f"    alert text: {alert_text!r}")
        check(bool(alert_text), "the refusal's own words are on screen in a role=alert")
        check(dialog_open, "and the dialog stayed open")
        check(
            name_box.input_value() == typed,
            "with the entered values still in it",
        )
        check(
            "[object Object]" not in alert_text and "{" not in alert_text,
            "and the sentence is prose, not a rendered object",
        )
        # Reset the form to a saveable state so the dialog can be closed cleanly.
        name_box.fill("D1 Ok")
        page.wait_for_timeout(200)

        # -------------------------------------------------------------- C, on screen
        print("\nC — the Add-agent dialog's preselected model, against the provider's own list")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        page.goto(f"{UI}/?project={pid}&tab=agents", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        preselected, unreachable = {}, {}
        try:
            page.get_by_role("button", name="Add agent").first.click()
            page.wait_for_timeout(1200)
            page.screenshot(path=os.path.join(SHOTS, "d1-05-add-agent.png"))
            for provider in declared:
                page.get_by_role("button", name="Provider", exact=True).first.click()
                page.wait_for_timeout(400)
                opt = page.locator("div[role='listbox'] button[role='option']").filter(
                    has_text=PROVIDER_LABELS.get(provider, provider)
                )
                if opt.count() == 0:
                    unreachable[provider] = "no option"
                    page.keyboard.press("Escape")
                    continue
                if not opt.first.is_enabled():
                    unreachable[provider] = "option disabled (not launchable here)"
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(200)
                    continue
                opt.first.click()
                page.wait_for_timeout(600)
                msel = page.locator("select[aria-label='Model']")
                if msel.count() == 0:
                    unreachable[provider] = "no model select appeared"
                    continue
                preselected[provider] = msel.first.input_value()
                offered = msel.first.evaluate("s => Array.from(s.options).map(o => o.value)")
                check(
                    offered == declared[provider],
                    f"{provider}: the Add-agent dialog offers exactly the catalog's models",
                )
            page.screenshot(path=os.path.join(SHOTS, "d1-06-add-agent-model.png"))
        except Exception as exc:  # noqa: BLE001
            print(f"    could not drive the Add-agent dialog: {type(exc).__name__}: {exc}")
        print(f"    preselected model per provider: {preselected}")
        print(f"    providers not reachable from this dialog here: {unreachable}")
        for provider, chosen in preselected.items():
            check(
                chosen == defaults.get(provider),
                f"{provider}: the dialog preselects the catalog's declared default "
                f"({chosen!r} vs {defaults.get(provider)!r})",
            )

        # -------------------------------------------------------------- D
        # Not in the brief. It fell out of B: the duplicate name the API accepted (201) is the
        # spec's own blessed shape — "Operator creates a second `claude` runner with a different
        # default model" — so this asks what the surface that *uses* runners does with two.
        print("\nD — two runners of one provider, distinguished only by their model")
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        code, r1 = call(
            "POST",
            f"/projects/{pid}/runners",
            {"name": "Claude Code", "cli": "claude", "model": "claude-opus-5"},
        )
        code2, r2 = call(
            "POST",
            f"/projects/{pid}/runners",
            {"name": "Claude Code", "cli": "claude", "model": "claude-haiku-4-5-20251001"},
        )
        check(
            code == 201 and code2 == 201,
            f"two same-named claude runners with different models are accepted [{code}/{code2}]",
        )
        acode, agent = call(
            "POST",
            f"/projects/{pid}/agents",
            {"name": "d1binder", "provider": "claude", "model": "claude-sonnet-5"},
        )
        check(acode == 201, f"an agent exists to bind them to [{acode}]")

        # C's fourth door, and the one an operator meets most often: the composer's per-run Model
        # pill. It needs an agent to exist, so it is measured here rather than in C(api). The
        # override is validated before anything spawns, so a refusal costs no tokens.
        if acode == 201:
            tcode, tbody = call(
                "POST",
                f"/projects/{pid}/agent/trigger",
                {
                    "agent": "d1binder",
                    "message": "noop",
                    "overrides": {"model": "claude-fable-5-1"},
                },
            )
            print(f"    per-run model override -> [{tcode}] {json.dumps(tbody)[:180]}")
            check(
                tcode == 400,
                f"the composer's per-run model override refuses an undeclared model [{tcode}]",
            )
        page.goto(f"{UI}/?project={pid}&tab=agents", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        binder_options = []
        try:
            page.get_by_role("button", name="Actions for d1binder").first.click(force=True)
            page.wait_for_timeout(700)
            page.get_by_text("Agent settings", exact=True).first.click()
            page.wait_for_timeout(2500)
            picker = page.locator("select[aria-label='Runner for d1binder']")
            if picker.count() == 0:
                # The rail carries the section list; walk it until the runner picker appears.
                sections = page.locator("nav[aria-label='Agent settings sections'] button")
                for i in range(sections.count()):
                    sections.nth(i).click()
                    page.wait_for_timeout(1000)
                    if picker.count():
                        break
            page.screenshot(path=os.path.join(SHOTS, "d1-07-runner-binding.png"))
            if picker.count():
                binder_options = picker.first.evaluate(
                    "s => Array.from(s.options).map(o => o.textContent.trim())"
                )
        except Exception as exc:  # noqa: BLE001
            print(f"    could not reach the runner-binding select: {type(exc).__name__}: {exc}")
        print(f"    runner-binding options on screen: {binder_options}")
        dupes = [o for o in binder_options if binder_options.count(o) > 1]
        if binder_options:
            check(
                not dupes,
                "the runner-binding select distinguishes the two runners "
                f"(identical option text: {sorted(set(dupes))})",
            )
        else:
            check(False, "the runner-binding select could not be read (D is unmeasured)")

        print(f"\n    console errors: {errors[:5]}")
        browser.close()

    # ------------------------------------------------------------------ C, the drift itself
    print("\nC(drift) — the catalog against Codex's own server-synced model list")
    cache = os.path.expanduser("~/.codex/models_cache.json")
    if not os.path.exists(cache):
        check(True, "no ~/.codex/models_cache.json on this machine (drift unmeasurable)")
    else:
        with open(cache, encoding="utf-8") as fh:
            data = json.load(fh)
        listed = [m["slug"] for m in data.get("models", []) if m.get("visibility") == "list"]
        print(
            f"    fetched_at={data.get('fetched_at')} client_version={data.get('client_version')}"
        )
        print(f"    cache lists: {listed}")
        print(f"    catalog declares: {declared.get('codex')}")
        gone = [m for m in declared.get("codex", []) if m not in listed]
        new = [m for m in listed if m not in declared.get("codex", [])]
        print(f"    declared-but-gone: {gone}")
        print(f"    listed-but-undeclared: {new}")
        check(not gone, f"every model the catalog declares for codex still exists ({gone})")
        check(
            defaults.get("codex") in listed,
            f"the catalog's codex DEFAULT ({defaults.get('codex')!r}) still exists upstream",
        )
        check(not new, f"no model the provider offers is unreachable through the catalog ({new})")


if __name__ == "__main__":
    sys.exit(main())
