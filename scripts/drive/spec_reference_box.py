"""Acceptance drive for `reference-a-spec-in-a-sentence-from-the-composer`: the app's real Composer,
mounted alone by `spec_reference_box/` (no Hub), driven in Chromium with real key presses.

    py -3.11 scripts/drive/spec_reference_box.py

Prints one line per check, `check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>`,
and exits 1 when any check fails. On the pre-build textarea Composer there is no box: the reference
is the spec's title typed as text, the way the operator copies it in today, so the check reaches the
composer and fails at its own assertion. RSSC-2 extends `insert_reference` to pick the spec from the
@ menu, which yields a box.

The composer's content is read as text with each box written `[[<title>]]` and the caret as `|`.
"""

import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

REPO = pathlib.Path(__file__).resolve().parents[2]
UI = REPO / "hub" / "ui"
HARNESS = pathlib.Path(__file__).resolve().parent / "spec_reference_box"
SPEC_TITLE = "SPEC-1"
FIELD = "[data-testid=composer-input], textarea.composer-textarea"

# Text with each box as [[title]] and the caret as |, for a textarea or a contenteditable field.
READ = """(el) => {
  if (el.tagName === 'TEXTAREA') {
    const v = el.value, s = el.selectionStart, e = el.selectionEnd
    return s === e ? v.slice(0, s) + '|' + v.slice(s) : v.slice(0, s) + '[' + v.slice(s, e) + ']' + v.slice(e)
  }
  const sel = getSelection(); let out = ''
  const caret = (node, off) => sel.rangeCount && sel.isCollapsed && sel.anchorNode === node && sel.anchorOffset === off
  const walk = (node) => {
    for (let i = 0; i <= node.childNodes.length; i++) {
      if (caret(node, i)) out += '|'
      const c = node.childNodes[i]; if (!c) break
      if (c.nodeType === 3) {
        const t = c.textContent
        for (let j = 0; j <= t.length; j++) { if (caret(c, j)) out += '|'; if (j < t.length) out += t[j] }
      } else if (c.dataset && c.dataset.specBox !== undefined) out += '[[' + (c.dataset.title || c.textContent.trim()) + ']]'
      else if (c.tagName === 'BR') out += '\\n'
      else walk(c)
    }
  }
  walk(el); return out
}"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_harness():
    port = free_port()
    cmd = f"npx vite --config {HARNESS / 'vite.config.mjs'} --port {port} --strictPort --host 127.0.0.1"
    proc = subprocess.Popen(cmd, cwd=UI, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}/index.html"
    for _ in range(120):
        try:
            urllib.request.urlopen(url, timeout=1)
            return proc, url
        except OSError:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("harness did not start: " + proc.stdout.read().decode(errors="replace")[-2000:])


def stop(proc):
    subprocess.run(f"taskkill /F /T /PID {proc.pid}", shell=True, capture_output=True)


def read(page):
    return page.locator(FIELD).first.evaluate(READ)


def clear(page):
    page.locator(FIELD).first.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")


def insert_reference(page):
    """Put a reference to SPEC-1 at the caret by the composer's own route. Today's composer has
    none for specs, so the reference is its title as text."""
    page.keyboard.type(SPEC_TITLE)


def check_backspace_removes_whole_box(page):
    clear(page)
    page.keyboard.type("see ")
    insert_reference(page)
    page.keyboard.type("now")
    for _ in range(3):
        page.keyboard.press("ArrowLeft")
    before = read(page)
    page.keyboard.press("Backspace")
    after_bs = read(page)
    clear(page)
    page.keyboard.type("see ")
    insert_reference(page)
    page.keyboard.type("now")
    for _ in range(3):
        page.keyboard.press("ArrowLeft")
    page.keyboard.press("ArrowLeft")
    after_left = read(page)
    ok_bs = after_bs == "see |now"
    ok_left = after_left == f"see |[[{SPEC_TITLE}]]now"
    detail = (
        f"before {before!r}; Backspace gave {after_bs!r} (want 'see |now'); "
        f"one ArrowLeft gave {after_left!r} (want 'see |[[{SPEC_TITLE}]]now')"
    )
    return ok_bs and ok_left, detail


CHECKS = [("backspace-removes-whole-box", check_backspace_removes_whole_box)]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    proc, url = start_harness()
    failed = 0
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            page.locator(FIELD).first.wait_for(timeout=30000)
            print("browser:", browser.version, "| field:", page.locator(FIELD).first.evaluate("e => e.tagName"))
            for key, fn in CHECKS:
                try:
                    ok, detail = fn(page)
                    reached, at_assertion = "yes", "no" if ok else "yes"
                except Exception as exc:  # noqa: BLE001 - a crash is reported as not reached
                    ok, reached, at_assertion, detail = False, "no", "no", f"{type(exc).__name__}: {exc}"
                failed += not ok
                print(f"check {key}: reached={reached} failed_at_assertion={at_assertion} -- {detail}")
            if errors:
                print("page errors:", errors[:3])
            browser.close()
    finally:
        stop(proc)
    print(f"{len(CHECKS) - failed}/{len(CHECKS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
