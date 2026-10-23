"""Shared helpers for the 2026-10-23 Conversations & composer drive (scratch Hub :8117, profile cv1023).

    AW_E2E_STATE=... py -3.11 scripts/drive/s1023_cv_lib.py GET /health
    AW_E2E_STATE=... py -3.11 scripts/drive/s1023_cv_lib.py seed      # seed the project's files
"""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys

os.environ.setdefault(
    "AW_E2E_STATE", "C:/Users/huida/Documents/projects/AgentWeave/testbed/e2e-state-cv1023.json"
)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

P = os.environ.get("AW_P", "proj-8cd25053c03e")
B = f"/projects/{P}"
DIR = pathlib.Path.home() / "Documents" / "aw-cv1023"
HAIKU = "claude-haiku-4-5-20251001"
SECRET = "ZEBRA-QUOKKA-4417"


def req(method, path, body=None, **kw):
    return e2e.request(method, path, body, **kw)


def show(method, path, body=None, limit=3000):
    status, res = req(method, path, body)
    text = json.dumps(res, indent=1, ensure_ascii=False)
    print(f"{method} {path} -> {status}\n{text[:limit]}")
    return status, res


def q(sql, *args):
    return [dict(r) for r in e2e.ro().execute(sql, args)]


def seed():
    (DIR / "secret.txt").write_text(f"The vault code is {SECRET}.\n", encoding="utf-8")
    (DIR / "docs").mkdir(exist_ok=True)
    (DIR / "docs" / "notes.md").write_text("# Notes\n\nCafé façade — naïve résumé.\n", encoding="utf-8")
    (DIR / "blob.bin").write_bytes(bytes(range(256)) * 40)
    (DIR / "huge.txt").write_bytes((b"x" * 1023 + b"\n") * (6 * 1024))  # 6 MiB of text
    (DIR / "src").mkdir(exist_ok=True)
    (DIR / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    for args in (
        ["add", "secret.txt", "docs/notes.md", "blob.bin", "huge.txt", "src/calc.py"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "seed files"],
    ):
        subprocess.run(["git", "-C", str(DIR), *args], check=True)
    print("seeded", sorted(p.name for p in DIR.iterdir()))


if __name__ == "__main__":
    if sys.argv[1] == "seed":
        seed()
    else:
        body = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
        show(sys.argv[1], sys.argv[2], body, limit=20000)
