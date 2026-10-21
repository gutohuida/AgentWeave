"""2026-10-20 Jobs & loops x Flows x Resilience sweep: fixture, runner, agents (scratch Hub :8160).

    AW_P=proj-... py -3.11 scripts/drive/s1020_l_setup.py
"""

import pathlib
import subprocess

from s1020_l_lib import HAIKU, P, req, show

D = pathlib.Path.home() / "Documents" / "aw-l-1020"
(D / "mathkit").mkdir(exist_ok=True)
(D / "mathkit" / "__init__.py").write_text("", encoding="utf-8")
(D / "mathkit" / "stats.py").write_text(
    "def mean(values):\n    return sum(values) / len(values)\n", encoding="utf-8"
)
(D / "mathkit" / "text.py").write_text(
    "def shout(text):\n    return text.upper()\n", encoding="utf-8"
)
(D / "mathkit" / "registry.py").write_text('PUBLIC = ["mean", "shout"]\n', encoding="utf-8")
(D / "tests").mkdir(exist_ok=True)
(D / "tests" / "test_stats.py").write_text(
    "from mathkit.stats import mean\n\n\ndef test_mean():\n    assert mean([1, 2, 3]) == 2\n",
    encoding="utf-8",
)
for args in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "mathkit"]):
    subprocess.run(["git", "-C", str(D), *args])

st, runner = req("POST", f"/projects/{P}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
print("runner", st, runner.get("id"))
rid = runner["id"]
for name in ("alpha", "beta", "rev", "gamma"):
    show("POST", f"/projects/{P}/agents", {"name": name, "runner_id": rid}, limit=200)
