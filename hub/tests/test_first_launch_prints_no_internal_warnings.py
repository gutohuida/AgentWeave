"""AW-129: a first launch prints AgentWeave's lines only, not library deprecation/reflection noise."""

import os
import subprocess
import sys
from pathlib import Path

HUB_ROOT = Path(__file__).resolve().parents[1]

SCRIPT = """
import asyncio
import hub.api.v1  # noqa: F401  (the import that warned about HTTP_422_UNPROCESSABLE_ENTITY)
from hub.db.engine import init_db
asyncio.run(init_db())
"""


def test_fresh_database_start_emits_no_python_warnings(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AW_", "HUB_"))}
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{(tmp_path / 'fresh.db').as_posix()}"
    env["PYTHONPATH"] = str(HUB_ROOT)
    proc = subprocess.run(
        [sys.executable, "-W", "always", "-c", SCRIPT],
        cwd=HUB_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Warning" not in proc.stderr, proc.stderr
