"""2026-10-20 Tasks x Dependencies x Worktrees sweep: fixture, runner, agents, a project check
(scratch Hub :8170).

    AW_P=proj-... py -3.11 scripts/drive/s1020_t_setup.py
"""

import pathlib
import subprocess

from s1020_t_lib import HAIKU, P, req, show

D = pathlib.Path.home() / "Documents" / "aw-t-1020"
(D / "shop").mkdir(exist_ok=True)
(D / "shop" / "__init__.py").write_text("", encoding="utf-8")
(D / "shop" / "price.py").write_text(
    "def total(items):\n    return sum(i['price'] for i in items)\n", encoding="utf-8"
)
(D / "shop" / "labels.py").write_text(
    'CURRENCY = "EUR"\n\n\ndef label(amount):\n    return f"{amount} {CURRENCY}"\n', encoding="utf-8"
)
(D / "tests").mkdir(exist_ok=True)
(D / "tests" / "test_price.py").write_text(
    "from shop.price import total\n\n\ndef test_total():\n    assert total([{'price': 2}, {'price': 3}]) == 5\n",
    encoding="utf-8",
)
for args in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "shop"]):
    subprocess.run(["git", "-C", str(D), *args])

st, runner = req("POST", f"/projects/{P}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
print("runner", st, runner.get("id"))
rid = runner["id"]
for name in ("alpha", "beta", "gamma"):
    show("POST", f"/projects/{P}/agents", {"name": name, "runner_id": rid}, limit=200)
