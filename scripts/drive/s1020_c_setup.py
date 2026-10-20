"""2026-10-20 Checkpoints x Accounting sweep: fixture + settings (scratch Hub :8150, profile c1020).

    AW_P=proj-... py -3.11 scripts/drive/s1020_c_setup.py
"""

import pathlib
import subprocess

from s1020_c_lib import HAIKU, P, req, show

D = pathlib.Path.home() / "Documents" / "aw-c-1020"
(D / "src").mkdir(exist_ok=True)
(D / "src" / "calc.py").write_text("def add(a, b):\n    return a - b  # seeded defect\n", encoding="utf-8")
(D / "tests").mkdir(exist_ok=True)
(D / "tests" / "test_calc.py").write_text(
    "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parents[1] / 'src'))\n"
    "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
    encoding="utf-8",
)
for args in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "calc"]):
    subprocess.run(["git", "-C", str(D), *args])

st, runner = req("POST", f"/projects/{P}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
print("runner", st, runner.get("id"))
rid = runner["id"]
for name in ("alpha", "beta", "gamma"):
    show("POST", f"/projects/{P}/agents", {"name": name, "runner_id": rid}, limit=300)
show(
    "PUT",
    f"/projects/{P}/settings",
    {
        "checkpoint_mode": "offered",
        "checkpoint_threshold_mode": "tokens",
        "checkpoint_threshold_value": 8000,
        "checkpoint_runner_id": rid,
        "checkpoint_model": HAIKU,
    },
    limit=2500,
)
show("GET", f"/projects/{P}/settings", limit=2500)
