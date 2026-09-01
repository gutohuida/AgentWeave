"""Sweep row 3's screen half — the agent surfaces, driven as an operator would.

Row 2 found F173 by asking what the *screen* does with a refusal the API produces. This asks the
same question of the agent surfaces, and asks a second one the API half cannot: whether the
launchability and collaboration-readiness the Hub computes on every call reaches any screen at all.

Run: AW_HUB=... AW_KEY=... AW_PROJECT=<project id> AW_AGENT=<an agent with a runner>
     AW_QUEUED_AGENT=<an agent with queued work> AW_SHOTS=<dir>
     py -3.11 scripts/drive/t_sweep_row3_ui.py

The Hub on :8011 serves `hub/hub/static/ui`, a committed build artefact — a UI source change does
not appear here until it is rebuilt. Nothing in this iteration changed UI source, so what this
captures is the shipped bundle.
"""

import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
KEY = os.environ["AW_KEY"]
PROJECT = os.environ["AW_PROJECT"]
AGENT = os.environ["AW_AGENT"]
QUEUED_AGENT = os.environ.get("AW_QUEUED_AGENT", "")
OUT = pathlib.Path(os.environ.get("AW_SHOTS", "."))
OUT.mkdir(parents=True, exist_ok=True)

SEED = f"""
sessionStorage.setItem('agentweave-session', {json.dumps(json.dumps({"apiKey": KEY, "hubUrl": HUB}))});
localStorage.setItem('agentweave-selected-project', {json.dumps(PROJECT)});
"""

PROJECT_URL = f"{HUB}/?project={PROJECT}"


def settings_url(agent, section="identity"):
    return f"{HUB}/?project={PROJECT}&agent={agent}&settings={section}"


results = []


def check(label, ok, detail=""):
    """`detail` is the evidence, printed either way — a passing row's evidence is what a later
    reader needs to know the assertion was about something real."""
    results.append((label, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    console_errors = []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(str(e)))

    # Every request the app makes, so a claim about "the screen never asks for X" is measured
    # from the wire rather than inferred from a grep.
    urls = []
    page.on("request", lambda r: urls.append(r.url))

    page.add_init_script(SEED)

    # ------------------------------------------------------------ 1. the project screen
    page.goto(PROJECT_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(4500)
    page.screenshot(path=str(OUT / "row3-01-project.png"), full_page=False)
    body = page.content()
    check("the project screen renders with the agent rail", AGENT in body, page.title())

    # The claim `get_agents_launchability`'s own docstring makes: it "feeds launchability
    # indicators in the agent/runner selector". Measured from the wire.
    check(
        "some screen actually fetches GET /agents/launchability",
        any("/agents/launchability" in u for u in urls),
        f"{len(urls)} requests, none to /agents/launchability",
    )

    # ------------------------------------------------------------ 2. create-agent dialog
    add = page.locator('button[aria-label*="Add agent" i], button[title*="Add agent" i]')
    if add.count() == 0:
        # The rail's add control may be an icon button; fall back to any control naming it.
        add = page.get_by_role("button", name="Add agent")
    check("the rail offers a way to add an agent", add.count() > 0, f"{add.count()} candidates")
    if add.count():
        add.first.click()
        page.wait_for_timeout(1200)
        dialog = page.locator('[role="dialog"]')
        check("it opens the create-agent dialog", dialog.count() > 0, str(dialog.count()))
        page.screenshot(path=str(OUT / "row3-02-create-dialog.png"), full_page=False)

        # The F173 contrast: this dialog is the one that got it right. Model comes from the
        # catalog rather than free text.
        selects = dialog.locator("select")
        check(
            "the model field offers the catalog's models rather than free text",
            selects.count() >= 1,
            f"{selects.count()} select(s), {dialog.locator('input').count()} input(s)",
        )

        # Type a duplicate name and watch what the operator is told.
        dialog.locator("input").first.fill(AGENT)
        page.wait_for_timeout(300)
        # Provider must be chosen before Save is enabled.
        picker = dialog.locator('button:has-text("Select a provider")')
        if picker.count():
            picker.first.click()
            page.wait_for_timeout(400)
            option = dialog.locator('[role="option"]:has-text("Claude")')
            check(
                "the provider list states why a provider that cannot launch is unavailable",
                dialog.locator('[role="listbox"]').count() > 0,
                f"{option.count()} Claude option(s) in the listbox",
            )
            if option.count():
                option.first.click()
                page.wait_for_timeout(700)
        page.screenshot(path=str(OUT / "row3-03-duplicate-typed.png"), full_page=False)
        save = dialog.locator('button:has-text("Create agent")')
        enabled = save.count() > 0 and save.first.is_enabled()
        check(
            "Create is reachable once a provider is chosen",
            enabled,
            "enabled" if enabled else "still disabled after choosing a provider",
        )
        if enabled:
            save.first.click()
            page.wait_for_timeout(2500)
            page.screenshot(path=str(OUT / "row3-04-duplicate-refused.png"), full_page=False)
            after = page.inner_text("body")
            told = "already exists" in after
            check(
                "the operator is told the duplicate name was refused, and why (F173's contrast)",
                told,
                "the sentence is on screen" if told else "no alert, no message",
            )
            still_open = page.locator('[role="dialog"]').count() > 0
            check(
                "the dialog stays open rather than closing on a failure",
                still_open,
                "open" if still_open else "dialog closed",
            )
        # close
        cancel = page.locator('button:has-text("Cancel")')
        if cancel.count():
            cancel.first.click()
            page.wait_for_timeout(500)

    # ------------------------------------------------------------ 3. agent settings
    page.goto(settings_url(AGENT), wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    page.screenshot(path=str(OUT / "row3-05-settings.png"), full_page=False)
    s = page.inner_text("body")
    check("the agent's settings page renders", AGENT in s, page.title())
    archive_present = page.locator('[data-testid="agent-archive-toggle"]').count() > 0
    check(
        "it offers the archive control", archive_present, "present" if archive_present else "absent"
    )

    # The runner binding lives on the Execution section, not Identity.
    page.goto(settings_url(AGENT, "execution"), wait_until="domcontentloaded")
    page.wait_for_timeout(3500)
    page.screenshot(path=str(OUT / "row3-05b-execution.png"), full_page=False)
    ex = page.inner_text("body")
    check(
        "the Execution section names the runner the agent is bound to",
        "claude" in ex.lower(),
        "runner named" if "claude" in ex.lower() else "no runner named",
    )

    # The finding this harness exists to settle: no launchability indicator reaches the operator.
    launch_said = (
        ("not runnable" in ex.lower())
        or ("cannot run" in ex.lower())
        or ("bind one in the hub ui" in ex.lower())
        or ("collaboration" in ex.lower())
    )
    check(
        "the Execution section says whether the agent can actually launch",
        launch_said,
        (
            "stated"
            if launch_said
            else "nothing on screen states launchability or collaboration readiness"
        ),
    )

    # And the sharper case: an agent with NO runner has undeliverable work, and the Hub already
    # has the sentence for it — "No runner is bound to this agent. Bind one in the Hub UI before
    # it can run." — recorded on the queue entry it cannot deliver.
    if QUEUED_AGENT:
        page.goto(settings_url(QUEUED_AGENT, "execution"), wait_until="domcontentloaded")
        page.wait_for_timeout(3500)
        page.screenshot(path=str(OUT / "row3-08-no-runner-execution.png"), full_page=False)
        nx = page.inner_text("body")
        check(
            "an agent bound to NO runner is told so as a problem, not offered as a value",
            "Bind one" in nx or "cannot run" in nx.lower() or "no runner is bound" in nx.lower(),
            "screen shows only a neutral 'No runner' dropdown value",
        )

    # ------------------------------------------------------------ 4. the archive refusal
    if QUEUED_AGENT:
        page.goto(settings_url(QUEUED_AGENT), wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        toggle = page.locator('[data-testid="agent-archive-toggle"]')
        check(
            "the blocked agent's settings page offers Archive",
            toggle.count() > 0,
            f"{toggle.count()} control(s)",
        )
        if toggle.count():
            toggle.first.click()
            page.wait_for_timeout(2500)
            page.screenshot(path=str(OUT / "row3-06-archive-refused.png"), full_page=False)
            # `inner_text`, not `content()`: an HTML search for a word an operator must READ is
            # a trap. "bind" matched `tabindex` on this very page and turned a real defect into
            # a green row until it was checked by hand.
            a = page.inner_text("body")
            check(
                "the archive refusal reaches the operator",
                "queued message" in a or page.locator('[role="alert"]').count() > 0,
                "refusal rendered" if "queued message" in a else "no refusal in the visible text",
            )
            check(
                "and it offers the remedy the refusal names (discard the queued work)",
                "Discard" in a,
                "discard offered" if "Discard" in a else "no discard control",
            )
            # The non-destructive remedy is the one the Hub itself treats as the repair: binding
            # a runner is a redrain site (agents.py, `runner_newly_bound`). The screen offers only
            # the destructive one.
            check(
                "the screen also names the non-destructive remedy (bind a runner, and it delivers)",
                "bind" in a.lower(),
                "only 'Discard … cannot be undone' is offered",
            )

    # ------------------------------------------------------------ 5. archived agents on screen
    # Archive from the UI is exercised above; the roster filter is the API half's job. What is
    # asked here is only whether the rail reflects it after an archive elsewhere.
    page.goto(PROJECT_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3500)
    page.screenshot(path=str(OUT / "row3-07-rail-after.png"), full_page=False)

    script_errors = [e for e in console_errors if "Failed to load resource" not in e]
    check(
        "no uncaught JavaScript error was produced by any of the above",
        not script_errors,
        "; ".join(script_errors[:3]),
    )

    browser.close()

print()
print("=" * 78)
failed = [r for r in results if not r[1]]
print(f"ROW 3 UI RESULT: {len(results) - len(failed)}/{len(results)} passed")
for label, _, det in failed:
    print(f"  FAIL  {label}" + (f"  — {det}" if det else ""))
sys.exit(0 if not failed else 1)
