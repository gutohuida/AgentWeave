"""Ledger sweep, phase 1: fixture, then the unreached read paths (workspace, fs, session sync GET).

py -3.11 scripts/drive/s1019_ledger.py   (Hub: e2e.py hub-up ledger1019 8180)
"""

import os
import subprocess

from s1019_ledger_lib import DIR, S, api, e2e, git, ro, save, say

# --- fixture: a small library with a seeded defect, plus files for the workspace probes
DIR.mkdir(parents=True, exist_ok=True)
(DIR / "src").mkdir(exist_ok=True)
(DIR / "tests").mkdir(exist_ok=True)
(DIR / "src" / "calc.py").write_text(
    "def add(a, b):\n    return a - b  # seeded defect\n\n\ndef mul(a, b):\n    return a * b\n",
    encoding="utf-8",
)
(DIR / "tests" / "test_calc.py").write_text(
    "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parents[1] / 'src'))\n"
    "from calc import add, mul\n\n\ndef test_add():\n    assert add(2, 3) == 5\n\n\n"
    "def test_mul():\n    assert mul(2, 3) == 6\n",
    encoding="utf-8",
)
(DIR / "README.md").write_text("# calc — café ☕\n\nA tiny library.\n", encoding="utf-8")
(DIR / "notes café.md").write_text("non-ASCII and a space in the name\n", encoding="utf-8")
(DIR / "logo.bin").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64 + os.urandom(256))
(DIR / "utf16.txt").write_text("hello in utf-16\n", encoding="utf-16")
(DIR / "latin1.txt").write_bytes("caf\xe9 in latin-1\n".encode("latin-1"))
(DIR / "big.txt").write_text("x" * 99 + "\n", encoding="utf-8")  # rewritten below
with open(DIR / "big.txt", "w", encoding="utf-8") as fh:
    fh.write(("y" * 99 + "\n") * 21000)  # 2.1 MB
with open(DIR / "edge.txt", "wb") as fh:
    fh.write(b"z" * 1_048_576)  # exactly the 1 MiB bound
(DIR / ".gitignore").write_text("secret.env\n", encoding="utf-8")
(DIR / "secret.env").write_text("TOKEN=aw_live_notreal\n", encoding="utf-8")
(DIR / "empty.txt").write_text("", encoding="utf-8")
if not (DIR / ".git").is_dir():
    git("init", "-q", "-b", "master")
git("add", "src", "tests", "README.md", ".gitignore", "logo.bin", "utf16.txt", "latin1.txt")
git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
print(git("log", "--oneline"))

st, proj = api("POST", "/projects/open", {"path": str(DIR)})
say("open", (st, proj.get("id") if isinstance(proj, dict) else proj))
S["P"], S["DIR"] = proj["id"], str(DIR)
save()
P = S["P"]

# --- runner + agents (Haiku)
st, runner = api("POST", f"/projects/{P}/runners", {"name": "haiku", "cli": "claude", "model": "claude-haiku-4-5-20251001"})
say("runner", (st, runner.get("id")))
S["RUNNER"] = runner["id"]
for name in ("builder", "rev"):
    st, a = api("POST", f"/projects/{P}/agents", {"name": name, "runner_id": runner["id"]})
    say(f"agent {name}", (st, a.get("name") if isinstance(a, dict) else a))
save()

# --- GET /workspace/paths and /workspace/file
st, paths = api("GET", f"/projects/{P}/workspace/paths")
say("paths", (st, paths))
for path in [
    "src/calc.py",
    "README.md",
    "notes café.md",
    "logo.bin",
    "utf16.txt",
    "latin1.txt",
    "big.txt",
    "edge.txt",
    "empty.txt",
    "secret.env",
    "src",
    "src\\calc.py",
    "./src/calc.py",
    "src//calc.py",
    "../aw-ledger-1019/src/calc.py",
    "../../../Windows/win.ini",
    "C:/Windows/win.ini",
    str(DIR / "src" / "calc.py"),
    ".git/config",
    "nope.txt",
]:
    import urllib.parse

    st, body = api("GET", f"/projects/{P}/workspace/file?path=" + urllib.parse.quote(path))
    if isinstance(body, dict) and "content" in body:
        content = body.get("content")
        body = {k: v for k, v in body.items() if k != "content"}
        body["content_head"] = (content or "")[:60] if content is not None else None
    say(f"file {path!r}", (st, body))
st, body = api("GET", f"/projects/{P}/workspace/file?path=")
say("file ''", (st, body))
st, body = api("GET", f"/projects/{P}/workspace/file?path=" + "a" * 4097)
say("file 4097", (st, str(body)[:300]))

# --- GET /fs/roots and /fs/list
st, roots = api("GET", "/fs/roots")
say("roots", (st, roots))
home = os.path.expanduser("~")
for path in [
    home,
    str(DIR),
    str(DIR / "src" / "calc.py"),
    str(DIR / "missing"),
    "relative/path",
    "C:\\",
    "C:",
    "C:/",
    "\\\\?\\C:\\Users",
    "\\\\localhost\\C$",
    str(DIR) + "\\..\\aw-ledger-1019",
    "~",
    "C:\\Windows\\System32\\config",
]:
    import urllib.parse

    st, body = api("GET", "/fs/list?path=" + urllib.parse.quote(path))
    if isinstance(body, dict) and "entries" in body:
        body = {**body, "entries": [e["name"] for e in body["entries"]][:12], "n": len(body["entries"])}
    say(f"fs/list {path!r}", (st, body))

# unauthenticated
import urllib.request

for route in ("/api/v1/fs/roots", "/api/v1/fs/list?path=C:\\", f"/api/v1/projects/{P}/workspace/paths"):
    try:
        with urllib.request.urlopen(e2e.hub() + route, timeout=10) as r:
            say(f"noauth {route}", (r.status, r.read()[:200]))
    except urllib.error.HTTPError as exc:
        say(f"noauth {route}", (exc.code, exc.read()[:200]))

# --- session sync: read before any write
st, body = api("GET", f"/projects/{P}/session/sync")
say("GET session/sync", (st, body))
print(ro("select name, id from agents where project_id=?", (P,)))
subprocess.run(["git", "-C", str(DIR), "status", "--short"])
