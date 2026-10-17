"""The UI judging harness for the visibility roadmap (slice `foundations`, decision vis-D8).

A drive imports this, opens the app on a Hub (the Terra replica by default, from
`terra_replica.py --up`), and gets four things every slice is judged by:

  shots(page, name, prepare)    the same screen at 1440 and 900 wide, in dark and in light
  frames(page, name, action)    a strip of frames taken while an animation plays, as one image
  reduced(...)                  a context that asks for reduced motion, to check nothing moves
  errors                        every console error and page error seen, which a drive must fail on

Output lands in `testbed/ui-judge/<drive>/<HHMMSS>/` (ignored), and the drive prints each path so the
images are read and critiqued before a commit. Never drives :8000; refuses :8010.

    from uiharness import Judge
    with Judge("d1017-gallery") as j:
        page = j.page(project="proj-cd006955cbe2", mode="dark")
        ...
"""

import json
import pathlib
import time
import urllib.parse

from PIL import Image
from playwright.sync_api import sync_playwright

HOME = pathlib.Path.home()
REPO = pathlib.Path(__file__).resolve().parents[2]
REPLICA_STATE = HOME / ".agentweave" / "e2e-replica.json"
WIDTHS = (1440, 900)
MODES = ("dark", "light")


def replica():
    """`(hub_url, key, db_path)` of the running Terra replica."""
    state = json.loads(REPLICA_STATE.read_text(encoding="utf-8"))
    return state["hub"], state["key"], state["db"]


class Judge:
    def __init__(self, drive, hub=None, key=None):
        if hub is None:
            hub, key, _db = replica()
        if hub.rstrip("/").endswith((":8000", ":8010")):
            raise SystemExit("the UI judge never drives :8000 or :8010")
        self.hub, self.key = hub.rstrip("/"), key
        self.out = REPO / "testbed" / "ui-judge" / drive / time.strftime("%H%M%S")
        self.out.mkdir(parents=True, exist_ok=True)
        self.errors = []
        self.written = []

    def __enter__(self):
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch()
        return self

    def __exit__(self, *exc):
        self.browser.close()
        self._pw.stop()
        print(f"UI judge output: {self.out}")
        for path in self.written:
            print("  " + str(path))
        if self.errors:
            print(f"  {len(self.errors)} console/page error(s):")
            for error in self.errors[:10]:
                print("    " + error[:300])
        return False

    def _seed(self, project, mode):
        return (
            "try { sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
            "localStorage.setItem('agentweave-selected-project', %s);"
            "localStorage.setItem('agentweave-prefs', JSON.stringify({mode: %s})); } catch (e) {}"
            % (json.dumps(self.key), json.dumps(self.hub), json.dumps(project), json.dumps(mode))
        )

    def page(self, project, mode="dark", width=1440, height=940, reduced_motion=False, query=""):
        context = self.browser.new_context(
            viewport={"width": width, "height": height},
            reduced_motion="reduce" if reduced_motion else "no-preference",
            device_scale_factor=1,
        )
        context.add_init_script(self._seed(project, mode))
        page = context.new_page()
        page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        page.on(
            "console",
            lambda m: self.errors.append(f"console: {m.text}") if m.type == "error" else None,
        )
        params = {"project": project}
        if query:
            params.update(dict(urllib.parse.parse_qsl(query)))
        page.goto(f"{self.hub}/?{urllib.parse.urlencode(params)}", wait_until="domcontentloaded")
        return page

    def set_mode(self, page, mode):
        page.evaluate(
            "m => { localStorage.setItem('agentweave-prefs', JSON.stringify({mode: m}));"
            " document.documentElement.dataset.mode = m; }",
            mode,
        )

    def shot(self, page, name, full_page=False, locator=None):
        path = self.out / f"{name}.png"
        if locator is not None:
            locator.screenshot(path=str(path))
        else:
            page.screenshot(path=str(path), full_page=full_page)
        self.written.append(path)
        return path

    def shots(self, project, name, prepare, query="", locator=None, full_page=False):
        """*prepare(page)* brings the screen to the state to judge; shot at each width and mode."""
        paths = []
        for width in WIDTHS:
            for mode in MODES:
                page = self.page(project, mode=mode, width=width, query=query)
                prepare(page)
                target = locator(page) if locator else None
                paths.append(self.shot(page, f"{name}_{width}_{mode}", full_page, target))
                page.context.close()
        return paths

    def frames(self, page, name, action, count=8, interval_ms=45, clip=None):
        """Trigger *action(page)*, then take *count* frames *interval_ms* apart, side by side."""
        images = []
        action(page)
        for index in range(count):
            path = self.out / f"_{name}_{index}.png"
            page.screenshot(path=str(path), clip=clip)
            images.append(Image.open(path))
            page.wait_for_timeout(interval_ms)
        width, height = images[0].size
        strip = Image.new("RGB", (width * len(images), height))
        for index, image in enumerate(images):
            strip.paste(image, (index * width, 0))
        out = self.out / f"{name}_frames.png"
        strip.save(out)
        for index in range(count):
            (self.out / f"_{name}_{index}.png").unlink()
        self.written.append(out)
        return out
