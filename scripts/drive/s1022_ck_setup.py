"""2026-10-22 Checkpoints x Accounting sweep: fixture + runners + settings (scratch Hub :8122,
profile ck1022). A Haiku runner (alpha, beta) and a Copilot provider runner aimed at the zero-spend
stub (`s1018_A_copilot_stub.py`, port argv[1]) for an agent `cop`, whose turns report tokens but
no cost: the "no reported cost" path.

    AW_P=proj-... py -3.11 scripts/drive/s1022_ck_setup.py <stub-port>
"""

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1022_ck_lib import B, HAIKU, e2e, req, show  # noqa: E402

D = pathlib.Path(e2e.os.environ["AW_E2E_ROOT"]) / "ck-main"
(D / "src").mkdir(exist_ok=True)
(D / "src" / "calc.py").write_text("def add(a, b):\n    return a - b  # seeded defect\n", encoding="utf-8")
(D / "tests").mkdir(exist_ok=True)
(D / "tests" / "test_calc.py").write_text(
    "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parents[1] / 'src'))\n"
    "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
    encoding="utf-8",
)
for args in (["add", "src", "tests"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "calc"]):
    subprocess.run(["git", "-C", str(D), *args])

st, runner = req("POST", f"{B}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
print("runner", st, runner.get("id"))
rid = runner["id"]
for name in ("alpha", "beta"):
    show("POST", f"{B}/agents", {"name": name, "runner_id": rid}, limit=300)
port = sys.argv[1]
st, cop = req("POST", f"{B}/runners", {
    "name": "cop-stub", "cli": "copilot", "model": HAIKU,
    "provider_config": {"type": "anthropic", "base_url": f"http://127.0.0.1:{port}",
                        "api_key_var": "PROCESSOR_ARCHITECTURE"}})
print("copilot runner", st, cop if st >= 300 else cop.get("id"))
if st < 300:
    show("POST", f"{B}/agents", {"name": "cop", "runner_id": cop["id"]}, limit=300)
show("PUT", f"{B}/settings", {
    "checkpoint_mode": "offered",
    "checkpoint_threshold_mode": "tokens",
    "checkpoint_threshold_value": 8000,
    "checkpoint_runner_id": rid,
    "checkpoint_model": HAIKU,
}, limit=800)
show("GET", f"{B}/agents/launchability", limit=1500)
