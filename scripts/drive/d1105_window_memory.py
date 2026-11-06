"""Acceptance drive for AWOAW-2's FR-5 and FR-6 (spec agentweave-is-its-own-app-on-windows).

FR-5 reopen-keeps-work: a window closed while its Hub stays in the background (close means stop
since AWOAW-3, so the drive turns the rollback setting on for its port, as App settings writes it),
a real Haiku turn started, then the app launched: the window opens on the same Hub process and the
turn completes.
FR-6 window-reopens-maximized: closed maximized -> reopens maximized; closed at 1200x800 at
(130, 70) -> reopens there; remembered off every screen -> reopens on the primary at 1200x800.

Reuses d1105_own_app.py's helpers: this checkout's CLI and Hub, scratch port 8174 and a scratch
d1105own* profile, never :8000 or :8010. Cleans up its Hub, profile and geometry file either way.

  py -3.11 scripts/drive/d1105_window_memory.py
"""

import ctypes
import json
import pathlib
import sys
import time
from ctypes import wintypes

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "drive"))
ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
import d1105_own_app as d  # noqa: E402

user32 = d.user32
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT]
user32.GetDpiForWindow.argtypes = [wintypes.HWND]
PORT = 8174
app = d.App(PORT, d.PROFILE_PREFIX + d.RUN + "g", d.project_dir("geo"))
geo_file = d.HUB_HOME / "app-window" / f"window-{PORT}.json"
geo_file.unlink(missing_ok=True)
# The rollback setting (D5) for this scratch port only: every close here leaves the Hub running.
close_file = d.HUB_HOME / "app-window" / f"close-{PORT}.json"
close_file.parent.mkdir(parents=True, exist_ok=True)
close_file.write_text(json.dumps({"keep_running": True}), encoding="utf-8")


def rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def open_window():
    p = app.launch()
    h = app.wait_window(p, 60)
    time.sleep(4.0)
    return p, h


def close(h):
    d.close_window(h)
    d.wait_for(lambda: not user32.IsWindow(h), 15, 0.1)
    time.sleep(1.0)


try:
    p1, h = open_window()
    d.check("window opens", h is not None)
    app.wait_healthy()
    hub = d.hub_pids(PORT)
    user32.ShowWindow(h, 3)
    time.sleep(1.5)  # SW_MAXIMIZE
    close(h)
    saved = json.loads(geo_file.read_text())
    d.note(f"saved after a maximized close: {saved}")
    d.check("FR-6: a maximized close is remembered as maximized", saved.get("maximized") is True)
    d.check(
        "FR-5: the Hub kept running in the background after the close",
        d.hub_pids(PORT) == hub,
        f"{hub}",
    )

    run_id, why = d.start_turn(app)
    d.check("a Haiku turn started", bool(run_id), why or run_id)
    time.sleep(10)
    d.note(f"turn {run_id}: {d.run_status(app, run_id)}")

    p2, h = open_window()
    d.check("FR-5: a window opens on the background Hub", h is not None)
    d.check(
        "FR-5: on the same Hub process", d.hub_pids(PORT) == hub, f"{hub} -> {d.hub_pids(PORT)}"
    )
    d.check(
        "FR-5: the turn is still in progress",
        d.run_status(app, run_id) == "running",
        d.run_status(app, run_id),
    )
    d.check("FR-6: it reopens maximized", bool(user32.IsZoomed(h)))

    user32.ShowWindow(h, 9)
    time.sleep(1.0)  # SW_RESTORE
    s = user32.GetDpiForWindow(h) / 96
    user32.SetWindowPos(h, None, int(130 * s), int(70 * s), int(1200 * s), int(800 * s), 0x0014)
    time.sleep(1.0)
    close(h)
    d.note(f"saved after a 1200x800 close: {json.loads(geo_file.read_text())}")
    p3, h = open_window()
    got = rect(h)
    want = (int(130 * s), int(70 * s), int(1200 * s), int(800 * s))
    d.check(
        "FR-6: it reopens at 1200x800 at that position",
        all(abs(a - b) <= 2 for a, b in zip(got, want)) and not user32.IsZoomed(h),
        f"{got} vs {want}",
    )
    close(h)

    data = json.loads(geo_file.read_text())
    data.update(x=60000, y=60000)
    geo_file.write_text(json.dumps(data))
    p4, h = open_window()
    x, y, w, hgt = rect(h)
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    d.check(
        "FR-6: off every screen, it reopens on the primary screen at 1200x800",
        0 <= x
        and x + w <= sw
        and 0 <= y
        and y + hgt <= sh
        and abs(w - int(1200 * s)) <= 2
        and abs(hgt - int(800 * s)) <= 2,
        f"{(x, y, w, hgt)} on a {sw}x{sh} primary",
    )
    d.check("FR-5: still the same Hub process", d.hub_pids(PORT) == hub)
    done = d.wait_for(
        lambda: d.run_status(app, run_id) not in ("running", "queued", "starting"), 300, 3
    )
    d.check(
        "FR-5: the turn completes without interruption",
        d.run_status(app, run_id) == "completed",
        d.run_status(app, run_id),
    )
    close(h)
finally:
    app.cleanup()
    geo_file.unlink(missing_ok=True)
    close_file.unlink(missing_ok=True)
    d.clear_scratch()
print("\n%d FAIL" % len(d.failures) if d.failures else "\nALL PASS", d.failures)
sys.exit(1 if d.failures else 0)
