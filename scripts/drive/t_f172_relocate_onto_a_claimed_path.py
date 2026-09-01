"""F172 — relocating onto a path another project row still claims answers 500.

`_guard_relocation` (`hub/hub/project_lifecycle.py:224`) checks three things: that the path key
actually changed, that the *old* directory is gone, and that no run is active. It never asks whether
the **destination** path key is already held by a different project row. `projects.path_key` is
unique, so the commit two lines later raises `IntegrityError` and FastAPI turns it into a bare 500.

Every other refusal this router produces is typed and legible — `project_identity_conflict`,
`project_workspace_missing`, `invalid_project_path`, each with a `code`, a `message` and a
`directory_state`. This one is an unhandled database constraint.

Reproduction, from nothing:

  A and B are two projects. A's directory is moved away, so A's row is left holding a path key
  nothing occupies. B's directory is then moved into the place A used to be — which is an ordinary
  thing to do with folders — and B is relocated to say so.

Run: AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 scripts/drive/t_f172_relocate_onto_a_claimed_path.py
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api, show  # noqa: E402

STAMP = int(time.time()) % 100000
BASE = Path(os.environ.get("AW_TMP", r"C:\Users\huida\Documents"))
A = BASE / f"f172-a-{STAMP}"
B = BASE / f"f172-b-{STAMP}"
A_PARKED = BASE / f"f172-a-parked-{STAMP}"


def git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README.md").write_text("f172\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=path, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=d@e.com", "-c", "user.name=d", "commit", "-qm", "f172"],
        cwd=path,
        capture_output=True,
    )


created = []
try:
    git_init(A)
    git_init(B)
    code, pa = api("POST", "/projects/open", {"path": str(A)})
    assert code == 200, (code, pa)
    created.append(pa["id"])
    code, pb = api("POST", "/projects/open", {"path": str(B)})
    assert code == 200, (code, pb)
    created.append(pb["id"])
    print(f"A={pa['id']} at {A}")
    print(f"B={pb['id']} at {B}")

    # A's folder goes elsewhere. Its row keeps claiming the old path key.
    shutil.move(str(A), str(A_PARKED))
    # B's folder moves into the vacated place, carrying B's own marker.
    shutil.move(str(B), str(A))

    code, body = api("POST", f"/projects/{pb['id']}/relocate", {"path": str(A)})
    show("POST relocate onto a path key another project still holds", code, body)

    ok = code != 500
    print()
    print(
        f"[{'PASS' if ok else 'FAIL'}] the collision is refused legibly rather than 500-ing "
        f"— got {code}"
    )
    if not ok:
        print(
            "     the server log carries: sqlalchemy.exc.IntegrityError "
            "(sqlite3.IntegrityError) UNIQUE constraint failed: projects.path_key"
        )
    sys.exit(0 if ok else 1)
finally:
    for pid in created:
        api("DELETE", f"/projects/{pid}")
    for p in (A, B, A_PARKED):
        shutil.rmtree(p, ignore_errors=True)
