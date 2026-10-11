"""Drive for F547 (Tier 0), 2026-10-12: the fold draft is refused for a change that is not approved.

Starts its own Hub from source on :8108 with a fresh database (never :8000 or :8010). No agent turn.
Steps, all over HTTP against the real routes:

  1. a capability (merged once) and a change-spec with content are created;
  2. GET fold-draft while the change is exploring, then proposed: 409 fold_change_not_approved, the
     same code POST fold answers (the two share one refusal);
  3. the change is approved: GET fold-draft answers 200 with the drafted requirements and writes
     nothing; POST fold then folds and archives it.

    py -3.11 scripts/drive/d1012_f547_fold_draft_phase.py
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402

d.PORT = 8108
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1012-f547" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

CAP = "spec/capabilities/widgets/spec.json"
CHANGE = "spec/changes/widgets-glow/spec.json"


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# f547\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "f547"})
    assert code in (200, 201), (code, project)
    base = f"/projects/{project['id']}/project"

    code, out = d.api("POST", f"{base}/documents", {"path": CAP, "title": "Widgets", "kind": "capability"})
    d.check("0 the capability is created", code == 201, f"{code} {out}")
    capability = {"schema_version": 1, "kind": "capability", "title": "Widgets",
                  "requirements": [{"key": "widgets-exist", "statement": "A widget MUST exist.",
                                    "modal": "MUST"}]}
    code, out = d.api("POST", f"{base}/documents/{CAP}/merge", {"payload": capability, "from_changes": []})
    d.check("0 the capability is merged", code == 200, f"{code} {str(out)[:200]}")

    code, out = d.api("POST", f"{base}/documents", {"path": CHANGE, "title": "Widgets glow"})
    d.check("1 the change is created", code == 201, f"{code} {out}")
    change = {
        "schema_version": 1, "kind": "change-spec", "title": "Widgets glow",
        "scope": {"in_scope": ["widgets"], "non_goals": ["gadgets"]},
        "requirements": [{"key": "glow", "statement": "A widget MUST glow when hovered.",
                          "modal": "MUST", "rationale": "visible"}],
        "acceptance_criteria": [{"key": "glow-c", "requirement": "glow", "given": "a widget",
                                 "when": "hovered", "then": "it glows"}],
        "tasks": [], "delivery": {"mode": "none"},
    }
    code, out = d.api("PUT", f"{base}/documents/{CHANGE}/content", {"document": change})
    d.check("1 the change content is written", code == 200, f"{code} {str(out)[:200]}")

    draft = f"{base}/documents/{CHANGE}/fold-draft?into={CAP}"

    def refused(label):
        code, out = d.api("GET", draft)  # an error body comes back as text
        d.check(f"2 {label}: the draft is refused", code == 409
                and '"code":"fold_change_not_approved"' in out, f"{code} {str(out)[:200]}")

    refused("exploring")
    code, out = d.api("POST", f"{base}/documents/{CHANGE}/fold", {"into": CAP})
    d.check("2 exploring: POST fold answers the same code", code == 409
            and '"code":"fold_change_not_approved"' in out, f"{code} {str(out)[:200]}")
    q = f"?path={CHANGE}"
    d.api("POST", f"{base}/documents/close-exploration{q}")
    code, out = d.api("POST", f"{base}/documents/phase{q}&to=proposed", {})
    d.check("2 moved to proposed", code == 200, f"{code} {str(out)[:200]}")
    refused("proposed")

    code, out = d.api("POST", f"{base}/documents/phase{q}&to=approved",
                      {"reason": "drive", "approve_anyway": True})
    d.check("3 moved to approved", code == 200, f"{code} {str(out)[:200]}")
    code, out = d.api("GET", draft)
    keys = [r["key"] for r in out.get("requirements", [])] if code == 200 else []
    d.check("3 approved: the draft is served", code == 200 and keys == ["widgets-glow-glow"],
            f"{code} {str(out)[:200]}")
    code, out = d.api("POST", f"{base}/documents/{CHANGE}/fold", {"into": CAP})
    d.check("3 approved: the fold archives the change", code == 200, f"{code} {str(out)[:200]}")


if __name__ == "__main__":
    d.drive = drive
    d.main()
