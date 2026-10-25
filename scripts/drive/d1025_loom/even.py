import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from drive import App, wait_loom, SCRATCH_KEY, AW
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); app = App(b, "http://127.0.0.1:5192", SCRATCH_KEY, AW)
    for knot in (None, "chapter:ch-origin-interagent"):
        pg = app.page(knot=knot); wait_loom(pg); pg.wait_for_timeout(2500)
        c = pg.evaluate("() => [...document.querySelectorAll('.aw-loom[data-scale=surface] [data-slot=loom-bead]')].map(e => { const r = e.getBoundingClientRect(); return r.left + r.width / 2; })")
        steps = sorted({round(c[i + 1] - c[i], 3) for i in range(len(c) - 1)})
        print(knot, len(c), "distinct centre-to-centre steps:", steps)
        pg.close()
    b.close()
