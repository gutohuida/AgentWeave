"""Author a change document on the trial Hub, as the operator, and propose it.

The payload is a JSON file (the `submit_spec_document` shape); the document lands at
`spec/changes/<name>/spec.html`. Re-runnable: a 409 on create means the document exists, and its
content is rewritten. Refuses to propose when the content is refused (F528).

Usage (Git Bash):
  export AW_HUB=http://127.0.0.1:8010 AW_KEY=$(cat ~/.agentweave/hub/profiles/trial/bootstrap-key.txt) \
         AW_PROJECT=proj-d85a82bf4216
  MSYS_NO_PATHCONV=1 py -3.11 scripts/drive/author_change.py <name> <payload.json>
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from aw import P, api  # noqa: E402


def main(name, payload_file):
    payload = json.loads(pathlib.Path(payload_file).read_text(encoding="utf-8"))
    base = f"/projects/{P}/project"
    path = f"spec/changes/{name}/spec.html"
    code, doc = api("POST", f"{base}/documents", {"title": payload["title"], "kind": "change-spec", "path": path})
    print("create", code, str(doc.get("id") or doc.get("detail") if isinstance(doc, dict) else doc)[:200])
    code, res = api("PUT", f"{base}/documents/{path}/content", {"document": payload})
    print("write", code, json.dumps(res)[:400])
    if code != 200:
        raise SystemExit("the content was refused; not proposing")
    api("POST", f"{base}/documents/close-exploration?path={path}")
    code, res = api("POST", f"{base}/documents/propose?path={path}")
    phase = res.get("phase") if isinstance(res, dict) else None
    print("propose", code, phase, json.dumps(res.get("blocking") if isinstance(res, dict) else res)[:400])
    if phase != "proposed":
        raise SystemExit("not proposed")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
