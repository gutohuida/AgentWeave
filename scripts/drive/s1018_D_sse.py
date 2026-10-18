"""Sweep D SSE: a client that stops reading the operator stream while 4000 log events are published;
does it get stream_gap when it reads again? Also /events/history paging and F419 stamping."""
import pathlib, socket, sys, threading, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from s1018_D_common import mine, say, sc  # noqa: E402
m = mine(); b = m["base"]
tok = sc.api("GET", "/events/ticket")[1]["token"]
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
s.connect(("127.0.0.1", int(sc.CFG["port"])))
s.sendall(f"GET /api/v1/events?token={tok} HTTP/1.1\r\nHost: x\r\nAccept: text/event-stream\r\n\r\n".encode())
time.sleep(1); first = s.recv(4096); say("first", first[:300].decode(errors="replace"))
N = 4000; pad = "x" * 600
def post(lo, hi):
    for i in range(lo, hi):
        sc.api("POST", f"{b}/logs", {"event_type": "sweepd_flood", "agent": "alpha", "data": {"i": i, "pad": pad}, "severity": "debug"})
t0 = time.time()
ts = [threading.Thread(target=post, args=(k * N // 8, (k + 1) * N // 8)) for k in range(8)]
[t.start() for t in ts]; [t.join() for t in ts]
say("posted", f"{N} in {time.time()-t0:.1f}s")
s.settimeout(5); data = b""
try:
    while True:
        chunk = s.recv(1 << 20)
        if not chunk: break
        data += chunk
        if b"stream_gap" in data and len(data) > 200000: break
except socket.timeout:
    pass
s.close()
text = data.decode(errors="replace")
gaps = [l for l in text.splitlines() if "stream_gap" in l or '"dropped"' in l]
say("bytes read", len(data)); say("flood frames", text.count("sweepd_flood")); say("gap lines", gaps[:6])
h = sc.api("GET", f"{b}/events/history?limit=5")
say("history limit=5", (h[0], [x.get("event_type") for x in (h[1] if isinstance(h[1], list) else h[1].get("events", []))] if h[0] == 200 else h[1]))
h = sc.api("GET", f"{b}/events/history?limit=100000")
say("history limit=100000", (h[0], len(h[1]) if isinstance(h[1], list) else str(h[1])[:300]))
