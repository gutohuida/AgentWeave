"""Browser half of the coverage-bar drive: opens the served bundle on the document, screenshots. AW_HUB, AW_KEY, AW_PROJECT, DOC."""

import os, sys

sys.stdout.reconfigure(encoding="utf-8")

from aw import require_key  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ["AW_HUB"]; KEY = require_key(); PROJ = os.environ["AW_PROJECT"]

SEED = f"""

sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, hubUrl: {HUB!r}}}));

localStorage.setItem('agentweave-selected-project', {PROJ!r});

"""

with sync_playwright() as p:

    b = p.chromium.launch(); page = b.new_page(viewport={"width": 1600, "height": 1000})

    page.add_init_script(SEED)

    page.goto(HUB, wait_until="domcontentloaded"); page.wait_for_timeout(3000)

    page.get_by_text("Spec", exact=True).first.click(); page.wait_for_timeout(2500)

    shot = lambda n: page.screenshot(path=os.environ["SHOT"] + n + ".png")

    page.get_by_test_id("spec-coverage").locator("button").first.click(); page.wait_for_timeout(800)
    tog = page.locator("[data-testid^='coverage-evidence-toggle-']").first

    tog.wait_for(timeout=120000); print("toggle:", tog.inner_text()); tog.click(); page.wait_for_timeout(1500)

    print("pieces:", page.locator("[data-testid^='evidence-piece-']").count())
    piece = page.locator("[data-testid^='evidence-piece-']").last

    print("piece:", piece.inner_text().replace(chr(10), " | "))

    held = page.locator("[data-testid^='evidence-held-']")

    accept = piece.get_by_role("button", name="Accept")

    print("held sentence present:", held.count(), "| accept disabled:", accept.is_disabled()); shot("A_live")

    # no reload: wait for the run to end and the broadcast to un-grey the row

    for i in range(40):

        page.wait_for_timeout(5000)

        if not accept.is_disabled(): break

    print("after %ds: held=%d accept disabled=%s" % (5 * (i + 1), held.count(), accept.is_disabled())); shot("B_ended")

    print("awaiting before:", page.locator("[data-testid='coverage-count-evidence_awaiting_review']").inner_text().replace(chr(10), " "))

    accept.click(); page.wait_for_timeout(3000); shot("C_accepted")

    print("piece after:", piece.inner_text().replace(chr(10), " | "))

    for k in ("evidence_awaiting_review", "satisfied", "evidence_accepted"):

        l = page.locator(f"[data-testid='coverage-count-{k}']")

        print(k, l.inner_text().replace(chr(10), " ") if l.count() else "(none)")

    print("body:", page.inner_text("body")[-900:])

    b.close()

