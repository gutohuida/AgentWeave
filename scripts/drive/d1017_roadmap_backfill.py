"""Backfill the visibility roadmap's archived slice documents with their roadmap link (F674, vis-D9).

Links each archived change document that built a slice of
`evidence-goes-agentic-and-the-project-becomes-visible-roadmap`, then reads the roadmap page and
checks every linked slice shows its document as archived. Re-runnable: a link already there is a
no-op (`changed: false`).

Usage (Git Bash):
  export AW_HUB=http://127.0.0.1:8010 AW_KEY=$(cat ~/.agentweave/hub/profiles/trial/bootstrap-key.txt) \
         AW_PROJECT=proj-d85a82bf4216
  py -3.11 scripts/drive/d1017_roadmap_backfill.py
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from aw import P, api  # noqa: E402

ROADMAP = "spec/changes/evidence-goes-agentic-and-the-project-becomes-visible-roadmap/spec.json"
SLICES = {
    "agentic-evidence": "the-reviewers-verdict-decides-the-tasks-evidence",
    "evidence-worth-reading": "evidence-carries-what-it-takes-to-judge-it",
    "task-story": "a-tasks-whole-story-is-in-its-drawer",
    "evidence-browser": "every-piece-of-evidence-in-one-place",
    "requirement-story": "how-a-requirement-changed-and-what-proved-it",
    "project-ledger": "the-activity-tab-becomes-the-projects-ledger",
    "remaining-hidden-data": "the-rest-of-what-the-hub-records-becomes-reachable",
}


def main():
    base = f"/projects/{P}/project"
    failures = []
    for key, name in SLICES.items():
        path = f"spec/changes/{name}/spec.json"
        code, res = api("PUT", f"{base}/documents/{path}/roadmap", {"document": ROADMAP, "slice": key})
        print("link", key, code, res.get("changed") if isinstance(res, dict) else res)
        if code != 200:
            failures.append(f"link {key}: {code} {res}")

    code, page = api("GET", f"{base}/spec?path={ROADMAP}")
    html = page.get("content", "") if isinstance(page, dict) else ""
    for key, name in SLICES.items():
        item = re.search(rf'<li id="slice-{key}".*?</li>', html, flags=re.S)
        text = item.group(0) if item else ""
        ok = "archived" in text and name in text
        print("page", key, "ok" if ok else "MISSING")
        if not ok:
            failures.append(f"page {key}: {text[:200]!r}")

    if failures:
        print("FAILED")
        for line in failures:
            print(" ", line)
        raise SystemExit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
