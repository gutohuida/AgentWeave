"""Provoke `stream_gap` (scratch Hub :8119, profile ev1023).

The Hub drops a frame for a subscriber only when that subscriber's queue (256, `sse.py`) is full,
which only happens when the transport stops draining it. Two consumers that stop draining:

  wire      a raw socket on /api/v1/events that reads the headers and then stops reading, while
            N large `log_event`s are posted; then it reads everything and counts the frames
  browser   the app on the Ledger view (its Activity feed renders `stream_gap`), with the page's
            main thread blocked so the fetch reader stops reading; the same burst; then the feed

  py -3.11 scripts/drive/s1023_ev_sse_gap.py wire|browser [N] [KB]
"""

import concurrent.futures
import socket
import sys
import time
import urllib.parse

from s1023_ev_sse_lib import B, P, e2e, req

WHAT = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 400
KB = int(sys.argv[3]) if len(sys.argv) > 3 else 60


def burst(tag):
    blob = "z" * (KB * 1024)

    def one(i):
        return req("POST", f"{B}/logs", {"event_type": "gap_probe", "agent": "alpha",
                                         "data": {"i": i, "tag": tag, "blob": blob}}, timeout=60)[0]

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(one, range(N)))
    print(f"burst {tag}: {N} x {KB} KB posted in {time.time() - t0:.1f}s; statuses {sorted(set(codes))}")


if WHAT == "wire":
    u = urllib.parse.urlparse(e2e.hub())
    s = socket.create_connection((u.hostname, u.port))
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    s.sendall((f"GET /api/v1/events HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
               f"Authorization: Bearer {e2e.key()}\r\nAccept: text/event-stream\r\n\r\n").encode())
    head = s.recv(2048)
    print("headers:", head.split(b"\r\n")[0], "| first bytes:", head[-80:])
    burst("wire")
    time.sleep(2)
    s.settimeout(3)
    data = bytearray()
    try:
        while True:
            chunk = s.recv(1 << 20)
            if not chunk:
                break
            data += chunk
    except socket.timeout:
        pass
    s.close()
    text = data.decode("utf-8", "replace")
    frames = text.count("event: log_event")
    print(f"read {len(data)} bytes; log_event frames {frames}; stream_gap frames {text.count('event: stream_gap')}")
    at = text.find("event: stream_gap")
    if at >= 0:
        print("gap frame:", text[at:at + 120].replace("\r\n", " | "))
else:
    from uiharness import Judge

    def txt(loc):
        return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"

    with Judge("s1023-ev-sse-gap", hub=e2e.hub(), key=e2e.key()) as j:
        if WHAT == "throttle":
            # A slow network, set before the page loads, so the SSE fetch itself is throttled.
            ctx = j.browser.new_context(viewport={"width": 1440, "height": 940})
            ctx.add_init_script(j._seed(P, "light"))
            page = ctx.new_page()
            cdp = ctx.new_cdp_session(page)
            cdp.send("Network.enable")
            cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 20,
                                                          "downloadThroughput": 200 * 1024, "uploadThroughput": -1})
            page.goto(f"{e2e.hub()}/?project={P}&tab=activity", wait_until="domcontentloaded")
            page.wait_for_timeout(20000)
            page.locator("[aria-label='Activity view'] button", has_text="Ledger").first.click()
            page.wait_for_timeout(5000)
            main = page.locator("main")
            print("feed mentions 'fell behind' before:", "fell behind" in txt(main))
            burst("throttle")
            end = time.time() + 200
            while time.time() < end and "fell behind" not in txt(main):
                page.wait_for_timeout(5000)
            body = txt(main)
            at = body.find("fell behind")
            print(f"after {200 - (end - time.time()):.0f}s, feed mentions 'fell behind':", at >= 0, "|",
                  body[max(0, at - 160):at + 220] if at >= 0 else "")
            j.shot(page, "gap_throttled", full_page=True)
            sys.exit(0)
        page = j.page(P, mode="light", query="tab=activity")
        page.wait_for_timeout(4000)
        page.locator("[aria-label='Activity view'] button", has_text="Ledger").first.click()
        page.wait_for_timeout(4000)
        main = page.locator("main")
        print("feed mentions 'fell behind' before:", "fell behind" in txt(main))
        block_s = 25
        page.evaluate("s => { setTimeout(() => { const t = Date.now() + s * 1000; while (Date.now() < t) {} }, 200) }",
                      block_s)
        time.sleep(1)
        burst("browser")
        page.wait_for_timeout(block_s * 1000)
        page.wait_for_timeout(8000)
        body = txt(main)
        at = body.find("fell behind")
        print("feed mentions 'fell behind' after:", at >= 0, "|", body[max(0, at - 120):at + 200] if at >= 0 else "")
        j.shot(page, "gap_ledger", full_page=True)
        page.locator("[aria-label='Activity view'] button", has_text="Activity").first.click()
        page.wait_for_timeout(3000)
        print("digest top:", [txt(r.locator(".aw-digest-sentence")) for r in page.locator(".aw-digest-row").all()][:5])
