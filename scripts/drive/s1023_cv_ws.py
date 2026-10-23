"""Conversations & composer, 2026-10-23: GET /workspace/paths and GET /workspace/file refusals —
outside the project, absolute, binary, huge, ignored, backslash spellings.

    py -3.11 scripts/drive/s1023_cv_ws.py
"""

import pathlib
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_cv_lib import B, DIR, req  # noqa: E402

probes = [
    "secret.txt",
    "docs/notes.md",
    "docs\\notes.md",
    "./secret.txt",
    "../aw-cv1023/secret.txt",
    "..",
    "../../.agentweave/hub/profiles/cv1023/agentweave.db",
    str(DIR / "secret.txt"),
    "C:/Windows/win.ini",
    ".git/config",
    ".agentweave/project.json",
    "blob.bin",
    "huge.txt",
    "nope.txt",
    "src",
]
for p in probes:
    st, res = req("GET", f"{B}/workspace/file?path={urllib.parse.quote(p)}")
    if isinstance(res, dict) and "content" in res:
        c = res.get("content")
        res = {k: v for k, v in res.items() if k != "content"} | {"content": (c or "")[:60] if c else c}
    print(f"{p!r:60} -> {st} {str(res)[:300]}")
# the empty and missing parameter
for tail in ("", "?path="):
    st, res = req("GET", f"{B}/workspace/file{tail}")
    print(f"file{tail!r} -> {st} {str(res)[:300]}")
