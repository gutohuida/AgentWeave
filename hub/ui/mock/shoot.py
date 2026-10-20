"""Screenshot mock screens: py -3.11 mock/shoot.py <out-dir> <hash> [<hash> ...] [--light] [--narrow] [--tall]

Each <hash> is a mock route such as `tab/vault` or `settings/manager`. Writes <out-dir>/<hash>_<mode>_<width>.png.
Prints console errors. Needs the mock dev server on :5199 (npx vite --config vite.mock.config.ts).
An optional action after `::` clicks a selector before the shot, e.g. `tab/vault::text=Add`.
"""

import pathlib
import re
import sys

from playwright.sync_api import sync_playwright

args = [a for a in sys.argv[1:] if not a.startswith("--")]
flags = {a for a in sys.argv[1:] if a.startswith("--")}
out = pathlib.Path(args[0])
out.mkdir(parents=True, exist_ok=True)
modes = ["dark", "light"] if "--light" in flags else ["dark"]
widths = [1440, 960] if "--narrow" in flags else [1440]
height = 2000 if "--tall" in flags else 900

with sync_playwright() as p:
    browser = p.chromium.launch()
    for spec in args[1:]:
        route, _, action = spec.partition("::")
        for mode in modes:
            for width in widths:
                ctx = browser.new_context(viewport={"width": width, "height": height})
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                page.on("console", lambda m, errors=errors: errors.append(m.text) if m.type == "error" else None)
                page.add_init_script(f"try {{ document.documentElement.dataset.mode = '{mode}' }} catch (e) {{}}")
                page.goto(f"http://localhost:5199/mock.html#{route}")
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(900)
                page.evaluate(f"document.documentElement.classList.add('no-transitions'); document.documentElement.dataset.mode = '{mode}'")
                page.wait_for_timeout(150)
                page.evaluate("document.documentElement.classList.remove('no-transitions')")
                if action:
                    for step in action.split("::"):
                        page.locator(step).first.click()
                        page.wait_for_timeout(600)
                name = re.sub(r"[^A-Za-z0-9_.-]+", "-", route + ("_" + action if action else ""))[:80]
                path = out / f"{name}_{mode}_{width}.png"
                page.screenshot(path=str(path))
                print(path, "ERR:" + " | ".join(errors[:3]) if errors else "")
                ctx.close()
    browser.close()
