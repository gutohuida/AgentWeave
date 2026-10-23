"""Projects sweep 2026-10-23 -- the native folder dialog, driven once, unattended.

The Hub's POST /fs/native-dialog/open pops a real Tk folder dialog on the Hub's desktop and waits
up to 120 s for it (hub/hub/native_dialog.py). Nobody answers it here, so this drive measures:
the pending button, a second tab's click while it is open (409 busy, what reaches the screen),
the API's own 409 body, whether /health stays live, closing the modal while the OS dialog stays
up, and the timeout notice when the Hub kills the dialog at 120 s.

    py -3.11 scripts/drive/s1023_pj_native.py
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s1023_pj_lib import PA, hub_and_key, req  # noqa: E402
from uiharness import Judge  # noqa: E402

HUB, KEY = hub_and_key()


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def os_dialog_windows():
    out = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process | Where-Object { $_.MainWindowTitle -like '*project folder*' } | "
            "ForEach-Object { \"$($_.Id) $($_.ProcessName) $($_.MainWindowTitle)\" }",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return out.stdout.strip()


def open_modal(page):
    page.wait_for_timeout(2500)
    page.get_by_text("Add project", exact=True).first.click()
    page.wait_for_timeout(800)
    return page.get_by_role("dialog")


def main():
    with Judge("s1023-pj", hub=HUB, key=KEY) as j:
        p1 = j.page(PA, mode="dark")
        d1 = open_modal(p1)
        print("modal title:", txt(d1.locator("h2")))
        btn = p1.get_by_label("Choose a folder", exact=True)
        print("native button present:", btn.count(), "text", txt(btn))
        t0 = time.time()
        btn.click()
        p1.wait_for_timeout(2500)
        print("p1 button while open:", repr(txt(btn)), "disabled", btn.is_disabled())
        print("OS dialog windows:", os_dialog_windows() or "<none found>")
        j.shot(p1, "10_native_pending")

        p2 = j.page(PA, mode="light")
        open_modal(p2)
        b2 = p2.get_by_label("Choose a folder", exact=True)
        b2.click()
        p2.wait_for_timeout(2000)
        print("p2 notice:", repr(txt(p2.get_by_role("dialog").get_by_role("status"))))
        j.shot(p2, "11_native_second_tab")

        status, body = req("POST", "/fs/native-dialog/open")
        print("API second open ->", status, json.dumps(body))
        h0 = time.time()
        with urllib.request.urlopen(HUB + "/health") as r:
            print("health during dialog:", r.status, round(time.time() - h0, 3), "s")

        # Close the modal on p2 (Escape) while the OS dialog stays up; reopen and press again.
        p2.keyboard.press("Escape")
        p2.wait_for_timeout(800)
        print("p2 modal after Escape:", p2.get_by_role("dialog").count())
        open_modal(p2)
        b2b = p2.get_by_label("Choose a folder", exact=True)
        print("p2 reopened button:", repr(txt(b2b)), "disabled", b2b.is_disabled())
        b2b.click()
        p2.wait_for_timeout(2000)
        print("p2 reopened notice:", repr(txt(p2.get_by_role("dialog").get_by_role("status"))))
        j.shot(p2, "12_native_reopened")

        # Wait for the Hub to kill the dialog, then press once more to see the state is clean.
        remaining = 125 - (time.time() - t0)
        print(f"waiting {remaining:.0f}s for the Hub's 120 s timeout")
        while time.time() - t0 < 125:
            time.sleep(5)
        print("OS dialog windows after timeout:", os_dialog_windows() or "<none found>")
        print("p2 notice after timeout:", repr(txt(p2.get_by_role("dialog").get_by_role("status"))))
        print("p1 notice after timeout:", repr(txt(p1.get_by_role("dialog").get_by_role("status"))))
        j.shot(p1, "13_native_after_timeout")
        print("errors:", j.errors[:5])


if __name__ == "__main__":
    main()
