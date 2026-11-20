"""Acceptance drive for `every-spec-entry-point-leads-into-the-journey` (slice 2 of the journey).

Drives the trial Hub (or a testbed project on it) and checks, each as its own named check:

  1. drive-draft-lands-on-intake
       Draft on a roadmap slice (POST documents/next-slice/take) names a new change document that is
       exploring at step intake with the roadmap link set; the queued drafting entry names that
       document (not the roadmap), its message neither mentions create_spec_document nor asks for the
       whole slice at once, and the briefing a turn on it gets holds '[step: intake]'.
  2. drive-agent-create-is-offered-and-opened
       An agent asked to create_spec_document in a conversation with no open document: the
       conversation's notices name the new document; Open makes it the conversation's document and
       removes the notice; the next message's queued entry names it and its briefing carries its step.
  3. drive-two-conversations-keep-their-own-documents
       Conversation A holds change document X, B none: B's attached document is null, a message sent in
       B is queued with no spec_document, A still holds X.

Contract it fixes for the build (none of it exists on today's tree, which is the point):
  - GET  /conversations/{id}/spec-documents  -> {"document": <path|null>, "notices": [{"document": <path>, ...}]}
  - PUT  /conversations/{id}/spec-document   {"path": <path>|null}   (Open; null stops exploring)
  - GET  /queue/{agent} entries carry `spec_document`
  - POST documents/next-slice/take answers `document` (the new change document's path)

The briefing a turn receives is read the way d1009_step_journey.py reads it:
GET /agents/agent-context?agent=&spec_document=<the entry's document>.

Not part of the project's checks: it lands red on purpose until the slice is built. Real turns bind
Haiku (the agent is checked, never changed). Environment, nothing defaulted (aw.py):

    AW_HUB=http://127.0.0.1:8010  AW_KEY=...  AW_PROJECT=<trial or testbed project id>
    AW_AGENT=<an open agent bound to a Haiku runner>

    py -3.11 scripts/drive/spec_entry_points_drive.py

Every check runs, a failure does not stop the rest, so one red run lists every gap.
"""

import json
import os
import sys
import time
import urllib.parse

from aw import P, api, require_hub, require_key  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

AGENT = os.environ.get("AW_AGENT", "")
BASE = f"/projects/{P}"
STAMP = time.strftime("%H%M%S")
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    return bool(ok)


def poll(fn, secs=20.0):
    end = time.time() + secs
    while time.time() < end:
        try:
            got = fn()
        except Exception:  # noqa: BLE001 -- try again
            got = None
        if got:
            return got
        time.sleep(1)
    return None


def as_dict(body):
    return body if isinstance(body, dict) else {}


def entry(entry_id):
    """The queued entry by id, from the agent's queue (all states: the turn may have claimed it)."""
    _, rows = api("GET", f"{BASE}/queue/{AGENT}")
    return next((r for r in rows if r.get("id") == entry_id), None) if isinstance(rows, list) else None


def briefing(path):
    query = urllib.parse.urlencode({"agent": AGENT, "spec_document": path})
    code, body = api("GET", f"{BASE}/agents/agent-context?{query}")
    return body.get("context", "") if code == 200 and isinstance(body, dict) else f"{code} {body}"


def document(path):
    _, listed = api("GET", f"{BASE}/project/documents")
    return next((d for d in as_dict(listed).get("documents", []) if d.get("path") == path), {})


def attached(conversation_id):
    """(status, the conversation's open document or None, its notices)."""
    code, body = api("GET", f"/conversations/{conversation_id}/spec-documents")
    body = as_dict(body)
    return code, body.get("document"), body.get("notices") or []


def send(message, conversation_id=None, spec_document=None):
    payload = {"agent": AGENT, "message": message}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    if spec_document:
        payload["spec_document"] = spec_document
    code, out = api("POST", f"{BASE}/agent/trigger", payload)
    return as_dict(out) if code in (200, 202) else {"error": f"{code} {out}"}


def finished(run_id, minutes=8):
    end = time.time() + minutes * 60
    while time.time() < end:
        _, run = api("GET", f"{BASE}/runs/{run_id}")
        if as_dict(run).get("status") not in ("started", "running", "queued", "starting", None):
            return True
        time.sleep(3)
    return False


def setup():
    if not (P and AGENT):
        raise SystemExit("set AW_PROJECT and AW_AGENT (an open agent bound to Haiku)")
    require_hub()
    require_key()
    code, agents = api("GET", f"{BASE}/agents")
    row = next((a for a in agents if a.get("name") == AGENT), None) if isinstance(agents, list) else None
    runner = row.get("runner_id") if row else None
    _, runners = api("GET", f"{BASE}/runners")
    model = next((r.get("model") or "" for r in runners if r.get("id") == runner), "") if isinstance(runners, list) else ""
    if "haiku" not in model.lower():
        raise SystemExit(f"agent {AGENT!r} is not bound to Haiku (runner model {model!r}); real turns bind Haiku")


def scenario_draft():
    _, offers = api("GET", f"{BASE}/project/next-slice-offers")
    offer = next(iter(as_dict(offers).get("offers") or []), None)
    if not check("draft: an offered slice exists on the trial project (built builds-after slices)",
                 offer is not None, f"offers={offers!r}"[:300]):
        return
    roadmap = offer.get("roadmap") or offer.get("path")
    slice_key = (offer.get("next_slice") or {}).get("key") or offer.get("slice")
    code, taken = api("POST", f"{BASE}/project/documents/next-slice/take",
                      {"agent": AGENT, "path": roadmap, "slice": slice_key})
    taken = as_dict(taken)
    new_path = taken.get("document")
    check("drive-draft-lands-on-intake: the take's answer names a new change document",
          code == 200 and new_path and new_path != roadmap, f"{code} {json.dumps(taken)[:300]}")
    row = document(new_path) if new_path else {}
    check("drive-draft-lands-on-intake: the document is exploring at step intake",
          row.get("phase") == "exploring" and row.get("step") == "intake",
          f"phase={row.get('phase')!r} step={row.get('step')!r}")
    link = row.get("roadmap") or {}
    check("drive-draft-lands-on-intake: the document's roadmap link is set",
          link.get("document") == roadmap and link.get("slice") == slice_key, f"roadmap={link!r}")
    queued = entry(taken.get("entry_id")) or {}
    check("drive-draft-lands-on-intake: the queued drafting entry names the new document",
          bool(new_path) and queued.get("spec_document") == new_path,
          f"entry.spec_document={queued.get('spec_document')!r}")
    check("draft-entry-bound-to-new-document: the entry is not bound to the roadmap",
          queued.get("spec_document") not in (None, roadmap), f"{queued.get('spec_document')!r}")
    content = queued.get("content") or ""
    check("draft-entry-bound-to-new-document: the message does not tell the agent to create a document",
          bool(content) and "create_spec_document" not in content, "")
    check("drive-draft-lands-on-intake: the turn's briefing contains '[step: intake]'",
          bool(new_path) and "[step: intake]" in briefing(new_path), "")


def scenario_agent_create():
    first = send("Reply with the single word ready.")
    conv = first.get("conversation_id")
    if not check("create: a conversation with no open document starts", bool(conv), str(first)[:200]):
        return
    finished(first["run_id"])
    code, open_doc, _ = attached(conv)
    check("drive-agent-create-is-offered-and-opened: the conversation starts with no open document",
          code == 200 and open_doc is None, f"{code} document={open_doc!r}")
    before = {d.get("path") for d in as_dict(api("GET", f"{BASE}/project/documents")[1]).get("documents", [])}
    turn = send(f"Call create_spec_document once with title 'Drive probe {STAMP}', kind change-spec. "
                "Then reply done and do nothing else.", conversation_id=conv)
    if turn.get("run_id"):
        finished(turn["run_id"])
    after = as_dict(api("GET", f"{BASE}/project/documents")[1]).get("documents", [])
    made = next((d.get("path") for d in after if d.get("path") not in before), None)
    code, _, notices = attached(conv)
    named = [n for n in notices if made and made in json.dumps(n)]
    check("drive-agent-create-is-offered-and-opened: the notice names the new document",
          bool(named), f"made={made!r} {code} notices={json.dumps(notices)[:300]}")
    code, out = api("PUT", f"/conversations/{conv}/spec-document", {"path": made})
    code, open_doc, notices = attached(conv)
    seen = code == 200
    check("drive-agent-create-is-offered-and-opened: after Open the conversation's document is the new one",
          bool(made) and open_doc == made, f"document={open_doc!r}")
    check("drive-agent-create-is-offered-and-opened: after Open the notice is gone",
          seen and not [n for n in notices if made and made in json.dumps(n)], f"{code} notices={json.dumps(notices)[:300]}")
    nxt = send("Reply with the single word ok.", conversation_id=conv)
    queued = entry(nxt.get("queue_entry_id")) or {}
    check("drive-agent-create-is-offered-and-opened: the next entry names the document",
          bool(made) and queued.get("spec_document") == made, f"entry.spec_document={queued.get('spec_document')!r}")
    check("drive-agent-create-is-offered-and-opened: its briefing carries the document's current step",
          bool(made) and "[step: intake]" in briefing(made), "")
    if nxt.get("run_id"):
        finished(nxt["run_id"])


def scenario_two_conversations():
    code, out = api("POST", f"{BASE}/project/documents",
                    {"title": f"Drive X {STAMP}", "kind": "change-spec"})
    doc_x = as_dict(out).get("path")
    if not check("two: change document X exists", code in (200, 201) and doc_x, f"{code} {str(out)[:200]}"):
        return
    a = send("Reply with the single word a.", spec_document=doc_x)
    b = send("Reply with the single word b.")
    conv_a, conv_b = a.get("conversation_id"), b.get("conversation_id")
    if not check("two: conversations A (X) and B (none) exist",
                 bool(conv_a and conv_b and conv_a != conv_b), f"A={a} B={b}"[:300]):
        return
    code, doc_b, _ = attached(conv_b)
    check("drive-two-conversations-keep-their-own-documents: B's attached document is null",
          code == 200 and doc_b is None, f"{code} document={doc_b!r}")
    again = send("Reply with the single word b2.", conversation_id=conv_b)
    queued = entry(again.get("queue_entry_id")) or {}
    check("drive-two-conversations-keep-their-own-documents: B's queued entry names no document",
          bool(queued) and not queued.get("spec_document"), f"entry.spec_document={queued.get('spec_document')!r}")
    code, doc_a, _ = attached(conv_a)
    check("drive-two-conversations-keep-their-own-documents: A's attached document is still X",
          code == 200 and doc_a == doc_x, f"{code} document={doc_a!r}")
    for run in (a, b, again):
        if run.get("run_id"):
            finished(run["run_id"])


def main():
    setup()
    for scenario in (scenario_draft, scenario_agent_create, scenario_two_conversations):
        print(f"\n== {scenario.__name__}", flush=True)
        try:
            scenario()
        except Exception as exc:  # noqa: BLE001 -- a crash is a red check, not a silent skip
            check(f"{scenario.__name__} ran to its end", False, f"{type(exc).__name__}: {exc}")
    bad = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
