"""Acceptance drive `real-agent-opens-it` for `reference-a-spec-in-a-sentence-from-the-composer` (FR-10).

    py -3.11 scripts/drive/spec_reference_agent_turn.py

Starts a throwaway Hub from this checkout (fresh database, scratch project; never :8000 or :8010),
binds an agent to Haiku, creates a spec document D with one distinctive requirement, and triggers a
real turn whose only naming of D is the text a composer box delivers (design D1,
`[spec: <title>](<id>)`, hub/ui/src/lib/specReference.ts). Passes when the run's trace holds a
`read_spec_document` call naming D's id or path and the agent's reply quotes D's first requirement.
No instruction about references is added to the message or the agent.

Prints `check real-agent-opens-it: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>`;
exits 1 on failure.
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from spec_reference_box import HAIKU, Hub  # noqa: E402

TITLE = "Zephyr gasket torque"
CLAUSE = "The Zephyr gasket SHALL be torqued to exactly 42 newton-metres"
KEY = "gasket-torque"


def main():
    with Hub() as hub:
        root = hub.scratch / "agent-turn-project"
        root.mkdir()
        (root / "README.md").write_text("A scratch project for the agent-turn drive.\n", encoding="utf-8")
        project = hub.need("POST", "/projects/open", {"path": str(root), "name": "spec-reference-agent-turn"})
        base = f"/projects/{project['id']}"
        runner = hub.need("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
        hub.need("POST", f"{base}/agents", {"name": "Alpha", "runner_id": runner["id"]})
        created = hub.need("POST", f"{base}/project/documents", {"title": TITLE, "kind": "change-spec"})
        path = created.get("path") or (created.get("document") or {}).get("path")
        doc_id = created.get("id") or (created.get("document") or {}).get("id") or ""
        body = {"schema_version": 1, "kind": "change-spec", "title": TITLE, "summary": "A drive fixture.",
                "problem": "The drive needs one.", "scope": {"in_scope": ["the drive"], "non_goals": ["else"]},
                "requirements": [{"key": KEY, "modal": "SHALL", "statement": f"{CLAUSE}."}],
                "acceptance_criteria": [{"key": "ok", "requirement": KEY, "given": "x", "when": "y",
                                         "then": "z", "how_to_check": "read", "checked_by": "agent"}]}
        code, out = hub.api("PUT", f"{base}/project/documents/{path}/content", {"document": body})
        if code != 200:
            print(f"check real-agent-opens-it: reached=no failed_at_assertion=no -- save refused {code} {out}")
            return 1
        listed = hub.need("GET", f"{base}/project/documents")["documents"]
        doc_id = next((d.get("id") for d in listed if d.get("path") == path), doc_id)
        message = f"What is the first requirement of [spec: {TITLE}]({doc_id})?"
        trig = hub.need("POST", f"{base}/agent/trigger", {"agent": "Alpha", "message": message})
        conv = trig.get("conversation_id")
        end, runs = time.time() + 600, {}
        while time.time() < end:
            code, chat = hub.api("GET", f"{base}/agent/Alpha/chat/{conv}")
            runs = (chat or {}).get("runs", {}) if code == 200 else {}
            if runs and all(r.get("status") not in ("started", "running") for r in runs.values()):
                break
            time.sleep(5)
        reply = json.dumps(chat)
        texts = [e.get("content") or e.get("text") or "" for e in (chat or {}).get("entries", []) if e.get("output_kind") == "text"]
        print("agent reply:", texts[-1:] )
        traces = json.dumps([hub.api("GET", f"{base}/traces/by-run/{rid}", None)[1] for rid in runs])
        called = "read_spec_document" in traces and (doc_id in traces or path in traces)
        quoted = "42 newton" in reply
        ok = called and quoted
        print(f"check real-agent-opens-it: reached={'yes' if runs else 'no'} "
              f"failed_at_assertion={'no' if ok else 'yes'} -- message {message!r}; runs "
              f"{[(r.get('status'), r.get('error')) for r in runs.values()]}; read_spec_document naming "
              f"{doc_id}/{path} in trace={called}; reply quotes first requirement={quoted}")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
