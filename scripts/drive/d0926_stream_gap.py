"""Drive a-live-view-that-fell-behind-is-told-and-catches-up, tasks.md 3.1 (F253).

A raw-socket operator-stream subscriber with a tiny receive buffer stops reading while 3,000
events are pushed through POST /logs; it then drains and we count `stream_gap` frames and the
burst events received. Needs AW_HUB, AW_KEY.
"""
import http.client, json, re, os, pathlib, socket, subprocess, sys, time, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api  # noqa: E402

HUB, KEY = os.environ["AW_HUB"], os.environ["AW_KEY"]
TAG = time.strftime("%H%M%S")
root = pathlib.Path(r"C:\Users\huida\Documents\projects\AgentWeave\testbed\scratch") / f"gap-{TAG}"
root.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text("gap drive\n", encoding="utf-8")
for cmd in (["git", "init", "-b", "main"], ["git", "config", "user.email", "a@example.invalid"],
            ["git", "config", "user.name", "a"], ["git", "add", "README.md"], ["git", "commit", "-m", "x"]):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)
c, proj = api("POST", "/projects/open", {"path": str(root), "name": f"gap-{TAG}"})
PID = proj["id"]
print("project", PID)

parts = urllib.parse.urlparse(HUB)
sock = socket.create_connection((parts.hostname, parts.port), timeout=10)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 512)
sock.sendall((f"GET /api/v1/events HTTP/1.1\r\nHost: {parts.hostname}:{parts.port}\r\n"
              f"Authorization: Bearer {KEY}\r\nAccept: text/event-stream\r\n\r\n").encode())
time.sleep(1.5)

BURST, SLOW = 3000, f"gap-{TAG}"
conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=30)
t0 = time.time()
for i in range(BURST):
    conn.request("POST", f"/api/v1/projects/{PID}/logs",
                 json.dumps({"event_type": SLOW, "data": {"i": i}, "agent": None, "severity": "info"}),
                 {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    r = conn.getresponse(); r.read()
conn.close()
print(f"pushed {BURST} in {time.time()-t0:.1f}s")
time.sleep(2)
sock.settimeout(4)
buf = b""
try:
    while True:
        ch = sock.recv(65536)
        if not ch:
            break
        buf += ch
except (socket.timeout, TimeoutError, OSError):
    pass
sock.close()
text = buf.decode("utf-8", "replace")
received = text.count(f'"{SLOW}"')
GAP_RE = re.compile("event: stream_gap[\r]?[\n]data: ([{].*?[}])")
gaps = [json.loads(m) for m in GAP_RE.findall(text)]
print("stream_gap occurrences in wire:", text.count("stream_gap"))
print("gap frames:", gaps)
dropped = sum(g["dropped"] for g in gaps)
print(f"received={received} dropped={dropped} sum={received + dropped} (burst {BURST})")
print("gap has project_id:", any("project_id" in g for g in gaps))
print("RESULT", "PASS" if gaps and received + dropped == BURST else "FAIL")
print("PID", PID)
