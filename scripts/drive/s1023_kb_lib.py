"""Shared helpers for the 2026-10-23 Keyboard & dialogs drive (scratch Hub :8118, profile kb1023).

Every drive here is keyboard-only after the page loads: `page.keyboard`, then a read of
`document.activeElement` after each step.

    AW_E2E_STATE=... py -3.11 scripts/drive/s1023_kb_<name>.py
"""

import importlib.util
import json
import os
import pathlib
import sys

os.environ.setdefault(
    "AW_E2E_STATE", "C:/Users/huida/Documents/projects/AgentWeave/testbed/e2e_state_kb1023.json"
)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

P = os.environ.get("AW_P", "proj-f7897cfb459c")
B = f"/projects/{P}"
HAIKU = "claude-haiku-4-5-20251001"
SHOTS = pathlib.Path(__file__).resolve().parents[2] / "testbed" / "ui-judge" / "s1023-kb"
SHOTS.mkdir(parents=True, exist_ok=True)

_ACTIVE_JS = """() => {
  const e = document.activeElement;
  if (!e || e === document.body) return {tag: 'BODY'};
  const cs = getComputedStyle(e);
  const dlg = e.closest('[role=dialog],[role=alertdialog],[cmdk-dialog]');
  return {
    tag: e.tagName,
    testid: e.getAttribute('data-testid'),
    aria: e.getAttribute('aria-label'),
    role: e.getAttribute('role'),
    id: e.id || null,
    text: (e.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 60),
    inDialog: dlg ? ((dlg.getAttribute('aria-label') || '') + '|' +
      ((dlg.querySelector('h2,[id$=title],.aw-dialog-title') || {}).textContent || '')).slice(0, 60) : null,
    outline: cs.outlineStyle !== 'none' && cs.outlineWidth !== '0px' ? cs.outlineStyle + ' ' + cs.outlineWidth + ' ' + cs.outlineColor : null,
    shadow: cs.boxShadow !== 'none' ? cs.boxShadow.slice(0, 60) : null,
  };
}"""


def req(method, path, body=None, **kw):
    return e2e.request(method, path, body, **kw)


def q(sql, *args):
    return [dict(r) for r in e2e.ro().execute(sql, args)]


def active(page):
    return page.evaluate(_ACTIVE_JS)


def fmt(a):
    bits = [a.get("tag", "?")]
    for k in ("testid", "aria", "role", "id"):
        if a.get(k):
            bits.append(f"{k}={a[k]}")
    if a.get("text"):
        bits.append(repr(a["text"][:40]))
    if a.get("inDialog") is not None:
        bits.append(f"[dialog {a['inDialog']!r}]")
    return " ".join(bits)


def step(page, key, label=None, wait=350):
    page.keyboard.press(key)
    page.wait_for_timeout(wait)
    a = active(page)
    print(f"  {label or key:28} -> {fmt(a)}")
    return a


def dialogs(page):
    """Visible dialog layers, outermost first."""
    return page.evaluate(
        """() => [...document.querySelectorAll('[role=dialog],[role=alertdialog]')]
        .filter(d => d.offsetParent !== null || getComputedStyle(d).position === 'fixed')
        .map(d => (d.getAttribute('aria-label') || (d.querySelector('h2,.aw-dialog-title') || {}).textContent || d.className || '').toString().slice(0, 50))"""
    )


def tab_cycle(page, n=14, shift=False):
    """Press Tab *n* times; return the list of formatted stops and whether all stayed in a dialog."""
    stops = []
    for _ in range(n):
        page.keyboard.press("Shift+Tab" if shift else "Tab")
        page.wait_for_timeout(120)
        stops.append(active(page))
    escaped = [fmt(s) for s in stops if s.get("inDialog") is None]
    return stops, escaped


def shot(page, name):
    path = SHOTS / f"{name}.png"
    page.screenshot(path=str(path))
    print("  shot:", path)
    return path


def open_page(browser, query="", width=1440, height=940):
    hub, key = e2e.hub(), e2e.key()
    context = browser.new_context(viewport={"width": width, "height": height})
    context.add_init_script(
        "try { sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
        "localStorage.setItem('agentweave-selected-project', %s); } catch (e) {}"
        % (json.dumps(key), json.dumps(hub), json.dumps(P))
    )
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    writes = []
    page.on(
        "request",
        lambda r: writes.append(f"{r.method} {r.url.split('/api/v1')[-1]}")
        if r.method in ("POST", "PUT", "PATCH", "DELETE")
        else None,
    )
    url = f"{hub}/?project={P}" + (f"&{query}" if query else "")
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    page.errors = errors
    page.writes = writes
    return page
