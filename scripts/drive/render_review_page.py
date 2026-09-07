"""Render a review page in a real browser, in both colour schemes, and report what it looks like.

    py -3.11 scripts/drive/render_review_page.py [path] [--shots DIR]

`check_review_page.py` proves the file *parses* and is self-contained. This proves it *reads*: a
page can be perfectly well-formed and still overflow horizontally on a narrow column, throw a
console error, or come out invisible in dark mode because a colour was hard-coded rather than
taken from a variable.

Written on 2026-09-07 (D-9), after the same Playwright snippet had been retyped by hand for the
2026-09-05, -06 and -07 pages. The checks are exactly the ones the D-5 log entry recorded, so a
later page is comparable to an earlier one rather than checked to a different standard each time.

Everything here is measured against a `file://` URL with no network, because that is how the
operator opens it.
"""
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

args = [a for a in sys.argv[1:] if not a.startswith("--")]
PATH = pathlib.Path(args[0] if args else "spec-queue/review/review-2026-09-07.html").resolve()
SHOTS = None
if "--shots" in sys.argv:
    SHOTS = pathlib.Path(sys.argv[sys.argv.index("--shots") + 1])
    SHOTS.mkdir(parents=True, exist_ok=True)

URL = PATH.as_uri()
fail = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + (f"  -- {detail}" if detail and not cond else ""))
    if not cond:
        fail.append(label)


MEASURE = """() => {
  const de = document.documentElement;
  const over = [];
  for (const el of document.querySelectorAll('pre, table, code, img')) {
    if (el.scrollWidth > el.clientWidth + 1) {
      over.push((el.tagName + ': ' + (el.textContent || '').slice(0, 60)).replace(/\\s+/g, ' '));
    }
  }
  return {
    bg: getComputedStyle(document.body).backgroundColor,
    ink: getComputedStyle(document.body).color,
    height: de.scrollHeight,
    hoverflow: de.scrollWidth > de.clientWidth + 1,
    overflowing: over,
    h2: [...document.querySelectorAll('h2')].map(h => h.textContent.replace(/\\s+/g, ' ').trim()),
    asks: [...document.querySelectorAll('.ask h4')].map(h => h.textContent.replace(/\\s+/g, ' ').trim()),
    cards: [...document.querySelectorAll('.card > h3 > code')].map(c => c.textContent.trim()),
  };
}"""

print(f"rendering {URL}\n")
results = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    for scheme in ("light", "dark"):
        ctx = browser.new_context(color_scheme=scheme, viewport={"width": 1100, "height": 900})
        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.goto(URL, wait_until="load")
        r = page.evaluate(MEASURE)
        r["errors"] = errors
        results[scheme] = r
        if SHOTS:
            page.screenshot(path=str(SHOTS / f"review-{scheme}-top.png"))
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            page.screenshot(path=str(SHOTS / f"review-{scheme}-bottom.png"))
        ctx.close()
    browser.close()

for scheme, r in results.items():
    print(f"[{scheme}]")
    print(f"  body background {r['bg']}   ink {r['ink']}   height {r['height']}px")
    check(f"{scheme}: no horizontal overflow on <html>", not r["hoverflow"])
    check(f"{scheme}: nothing overflows its box", not r["overflowing"], str(r["overflowing"])[:300])
    check(f"{scheme}: no console errors", not r["errors"], str(r["errors"])[:300])
    check(f"{scheme}: body background is not transparent", r["bg"] not in ("rgba(0, 0, 0, 0)", ""))

check("both schemes render the same height", results["light"]["height"] == results["dark"]["height"],
      f"{results['light']['height']} vs {results['dark']['height']}")
check("the two schemes differ in background", results["light"]["bg"] != results["dark"]["bg"])

print("\nsections:")
for h in results["light"]["h2"]:
    print(f"  {h}")
print("asks:")
for a in results["light"]["asks"]:
    print(f"  {a}")
print("change cards:")
for c in results["light"]["cards"]:
    print(f"  {c}")
if SHOTS:
    print(f"\nshots -> {SHOTS}")
print(json.dumps({k: {"bg": v["bg"], "height": v["height"]} for k, v in results.items()}))
print("\nFAILED" if fail else "\nALL CHECKS PASSED")
