"""Acceptance drive for `every-spec-entry-point-leads-into-the-journey` (slice 2 of the journey).

Drives a Hub (the trial Hub, or a throwaway one when the trial Hub cannot open a project) and checks,
each as its own named check:

  1. drive-draft-lands-on-intake (and draft-entry-bound-to-new-document)
       The drive seeds its own fixture: an approved roadmap with one not-drafted slice that builds
       after nothing (so every slice it builds after is built). Draft on it (POST
       documents/next-slice/take): the answer names a new change document; that document is exploring
       at step intake with the roadmap link set; the queued drafting entry names that document (not the
       roadmap), its message neither mentions create_spec_document nor asks for the slice to be
       submitted whole, and the turn's own rendered context holds '[step: intake]'.
  2. drive-agent-create-is-offered-and-opened
       An agent asked to create_spec_document in a conversation with no open document: the
       conversation's offers name the new document; Open makes it the conversation's document and
       removes the notice; the next message's queued entry names it and the next turn's rendered
       context carries its step.
  3. drive-two-conversations-keep-their-own-documents
       Conversation A holds change document X, B none: B's attached document is null, a message sent in
       B is queued with spec_document null, A still holds X.

Contract it fixes for the build (none of it exists on today's tree, which is the point; design D3-D5):
  - GET  /projects/{P}/conversations/{id}/spec-documents -> {"attached": {path,..}|null, "offers": [{path,..}]}
  - PUT  /projects/{P}/conversations/{id}/spec-document  {"path": <path>|null}
  - POST /projects/{P}/conversations/{id}/spec-documents/answer {"path", "answer": "open"|"not_now"}
  - GET  /projects/{P}/queue/{agent} entries carry `spec_document` (null when none -- an absent key fails)
  - POST documents/next-slice/take answers `document: {path, title, phase, step}`

What "the turn's context" is: the file the Hub writes for the run, `<work dir>/.agentweave/context/
<agent>.md` (agent_trigger.run_context_file), found by searching AW_PROJECT_DIR for it. It is read after
the run holding the entry has started, so it is what that turn was told, not what the context route
renders for a document passed in by hand. No file found = the check is *not reached*, and says so.

Output: one PASS/FAIL line per check as it runs, then a baseline block, one line per check in the form
the drive-baseline gate reads: `check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>`.
A 404 on a conversation route this slice adds is reported reached=yes (the conversation itself was
found in the project's conversation list first) and failed_at_assertion=yes: the route's absence is the
assertion, the contract above being what the build adds.

Not part of the project's checks: it lands red on purpose until the slice is built. Real turns bind
Haiku (the agent is checked, never changed). Environment, nothing defaulted (aw.py):

    AW_HUB=http://127.0.0.1:8010  AW_KEY=...  AW_PROJECT=<testbed project id>
    AW_AGENT=<an open agent bound to a Haiku runner>
    AW_PROJECT_DIR=<the testbed project's directory>

    py -3.11 scripts/drive/spec_entry_points_drive.py

Every check runs, a failure does not stop the rest, so one red run lists every gap.
"""

import json
import os
import pathlib
import sys
import time

from aw import P, api, require_hub, require_key  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

AGENT = os.environ.get("AW_AGENT", "")
PROJECT_DIR = os.environ.get("AW_PROJECT_DIR", "")
BASE = f"/projects/{P}"
SPEC = f"{BASE}/project"
STAMP = time.strftime("%H%M%S")
results = []
baseline = []


def check(key, ok, detail="", reached=True):
    """One named check. `reached` False: the assertion was never evaluated (a precondition failed)."""
    ok = bool(ok)
    results.append((key, ok))
    print(("PASS " if ok else "FAIL ") + key + (f" -- {detail}" if detail else ""), flush=True)
    failed = (not ok) and reached
    # The Hub's baseline parser reads `check <key> (<text>): reached=...`: no colon in the key.
    name, _, what = key.partition(": ")
    label = f"{name} ({what.replace(')', ']').replace('(', '[')})" if what else name
    if "-fixture" in key or key.startswith("draft-take-queues"):
        # Setup, not a criterion: shown in the baseline only when it stops the drive short.
        if not ok:
            baseline.append(f"check {label}: reached=no failed_at_assertion=no -- setup failed: {detail}")
        return ok
    baseline.append(
        f"check {label}: reached={'yes' if reached else 'no'} "
        f"failed_at_assertion={'yes' if failed else 'no'} -- {detail or ('passes today' if ok else '')}"
    )
    return ok


def as_dict(body):
    return body if isinstance(body, dict) else {}


def entry(entry_id):
    """The queued entry by id, from the agent's queue (all states: the turn may have claimed it)."""
    _, rows = api("GET", f"{BASE}/queue/{AGENT}")
    return next((r for r in rows if r.get("id") == entry_id), None) if isinstance(rows, list) else None


def documents():
    _, listed = api("GET", f"{SPEC}/documents")
    return as_dict(listed).get("documents", [])


def document(path):
    return next((d for d in documents() if d.get("path") == path), {})


def conversation_known(conversation_id):
    _, body = api("GET", f"{BASE}/conversations?lifecycle=all")
    rows = as_dict(body).get("conversations") or []
    return any(r.get("id") == conversation_id for r in rows)


def attached(conversation_id):
    """(status, the conversation's open document path or None, the offered paths)."""
    code, body = api("GET", f"{BASE}/conversations/{conversation_id}/spec-documents")
    body = as_dict(body)
    open_doc = body.get("attached")
    paths = [o.get("path") for o in (body.get("offers") or []) if isinstance(o, dict)]
    return code, (open_doc or {}).get("path") if isinstance(open_doc, dict) else None, paths


def route_note(code, extra=""):
    if code == 200:
        return extra
    return f"GET spec-documents answered {code}: the route is what this slice adds. {extra}".strip()


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


def entry_run(entry_id, secs=90):
    """The run that took the entry, once there is one."""
    end = time.time() + secs
    while time.time() < end:
        row = entry(entry_id) or {}
        if row.get("delivered_in_run_id"):
            return row["delivered_in_run_id"]
        time.sleep(2)
    return None


def turn_context(entry_id, since):
    """What the turn that took *entry_id* was told: the context file its run wrote, or None."""
    run_id = entry_run(entry_id)
    if not run_id or not PROJECT_DIR:
        return None, f"no run took the entry (run={run_id!r}) or AW_PROJECT_DIR unset"
    end = time.time() + 60
    while time.time() < end:
        files = [
            f
            for f in pathlib.Path(PROJECT_DIR).rglob(f"{AGENT}*.md")
            if f.parent.name == "context" and f.stat().st_mtime >= since - 2
        ]
        if files:
            newest = max(files, key=lambda f: f.stat().st_mtime)
            return newest.read_text(encoding="utf-8", errors="replace"), str(newest)
        time.sleep(2)
    return None, f"no context file for {AGENT} under {PROJECT_DIR} after the run {run_id} started"


def setup():
    if not (P and AGENT and PROJECT_DIR):
        raise SystemExit("set AW_PROJECT, AW_AGENT (an open agent bound to Haiku) and AW_PROJECT_DIR")
    require_hub()
    require_key()
    _, agents = api("GET", f"{BASE}/agents")
    row = next((a for a in agents if a.get("name") == AGENT), None) if isinstance(agents, list) else None
    runner = row.get("runner_id") if row else None
    _, runners = api("GET", f"{BASE}/runners")
    model = next((r.get("model") or "" for r in runners if r.get("id") == runner), "") if isinstance(runners, list) else ""
    if "haiku" not in model.lower():
        raise SystemExit(f"agent {AGENT!r} is not bound to Haiku (runner model {model!r}); real turns bind Haiku")


def write_document(payload, title):
    code, doc = api("POST", f"{SPEC}/documents", {"title": title, "kind": payload["kind"]})
    doc = as_dict(doc)
    if code not in (200, 201) or not doc.get("path"):
        return None, f"create {code} {str(doc)[:200]}"
    code, body = api("PUT", f"{SPEC}/documents/{doc['path']}/content", {"document": payload})
    if code != 200:
        return None, f"write {code} {str(body)[:300]}"
    return doc["path"], ""


def seed_roadmap():
    """An approved roadmap with one slice that builds after nothing, so it is offered for drafting."""
    payload = {
        "schema_version": 1, "kind": "roadmap", "title": f"Drive roadmap {STAMP}",
        "summary": "One slice.", "problem": "Drive fixture roadmap for the draft entry point.",
        "scope": {"in_scope": ["one slice"], "non_goals": ["more"]},
        "slices": [{"key": "only", "title": f"Drive slice {STAMP}", "intent": "Build one thing.",
                    "done": "It exists."}],
        "design": "", "evidence": {"checked": [], "limits": []}, "lifecycle": "one-off",
        "open_questions": [],
    }
    path, why = write_document(payload, payload["title"])
    if not path:
        return None, why
    api("POST", f"{SPEC}/documents/close-exploration?path={path}")
    api("POST", f"{SPEC}/documents/propose?path={path}")
    _, spec = api("GET", f"{SPEC}/spec?path={path}")
    code, body = api("POST", f"{SPEC}/documents/phase?path={path}&to=approved",
                     {"reason": "drive", "approve_anyway": True,
                      "content_version": as_dict(spec).get("content_version")})
    return (path, "") if code == 200 else (None, f"approve {code} {str(body)[:200]}")


def scenario_draft():
    roadmap, why = seed_roadmap()
    _, offers = api("GET", f"{SPEC}/next-slice-offers")
    offered = [o for o in as_dict(offers).get("offers") or [] if o.get("roadmap") == roadmap]
    if not check("draft-fixture: the seeded roadmap's slice is offered", roadmap and offered,
                 why or f"offers={str(offers)[:200]}"):
        return
    before = {d.get("path") for d in documents()}
    t0 = time.time()
    code, taken = api("POST", f"{SPEC}/documents/next-slice/take", {"agent": AGENT, "path": roadmap, "slice": "only"})
    taken = as_dict(taken)
    if not check("draft-take-queues-a-turn: the take answered 200 with an entry", code == 200 and taken.get("entry_id"),
                 f"{code} {json.dumps(taken)[:200]}"):
        return
    answer = taken.get("document")
    # The take answers the document as {path, title, phase, step}; a bare path string is accepted too.
    new_path = answer.get("path") if isinstance(answer, dict) else answer
    check("drive-draft-lands-on-intake: the take's answer names a new change document",
          bool(new_path) and new_path != roadmap, f"answer.document={answer!r}")
    # The new document is also read from the project, independent of the answer's shape.
    made = [d for d in documents() if d.get("path") not in before and d.get("kind") == "change-spec"]
    row = made[0] if made else {}
    check("drive-draft-lands-on-intake: the document is exploring at step intake",
          row.get("phase") == "exploring" and row.get("step") == "intake",
          f"new change documents={len(made)} phase={row.get('phase')!r} step={row.get('step')!r}")
    link = row.get("roadmap") or {}
    check("drive-draft-lands-on-intake: the document's roadmap link is set",
          link.get("document") == roadmap and link.get("slice") == "only", f"roadmap={link!r}")
    queued = entry(taken["entry_id"]) or {}
    bound = queued.get("spec_document", "<field absent>")
    check("drive-draft-lands-on-intake: the queued drafting entry names the new document",
          bool(row.get("path")) and bound == row.get("path"),
          f"entry.spec_document={bound!r} new document={row.get('path')!r}")
    check("draft-entry-bound-to-new-document: the entry is not bound to the roadmap",
          bound not in (roadmap, "<field absent>", None) and bound == row.get("path"),
          f"entry.spec_document={bound!r} roadmap={roadmap!r}")
    content = queued.get("content") or ""
    check("draft-entry-bound-to-new-document: the message does not tell the agent to create a document",
          bool(content) and "create_spec_document" not in content,
          "message still says create_spec_document" if "create_spec_document" in content else "")
    check("draft-entry-bound-to-new-document: the message does not tell the agent to submit the slice whole",
          bool(content) and "submit it with" not in content,
          "message still says 'submit it with roadmap: ...'" if "submit it with" in content else "")
    text, where = turn_context(taken["entry_id"], t0)
    check("drive-draft-lands-on-intake: the turn's rendered context contains '[step: intake]'",
          bool(text) and "[step: intake]" in (text or ""),
          f"context {where} {'lacks' if text is not None and '[step: intake]' not in text else 'has'} '[step: intake]'",
          reached=text is not None)
    run_id = (entry(taken["entry_id"]) or {}).get("delivered_in_run_id")
    if run_id:
        finished(run_id)


def scenario_agent_create():
    first = send("Reply with the single word ready.")
    conv = first.get("conversation_id")
    if not check("create-fixture: a conversation with no open document starts", bool(conv), str(first)[:200]):
        return
    finished(first["run_id"])
    known = conversation_known(conv)
    code, open_doc, _ = attached(conv)
    check("drive-agent-create-is-offered-and-opened: the conversation starts with no open document",
          code == 200 and open_doc is None, route_note(code, f"attached={open_doc!r}")
          + " [precondition: its value is right before the build; it fails only because the route is absent]", reached=known)
    before = {d.get("path") for d in documents()}
    turn = send(f"Call create_spec_document once with title 'Drive probe {STAMP}', kind change-spec. "
                "Then reply done and do nothing else.", conversation_id=conv)
    if turn.get("run_id"):
        finished(turn["run_id"])
    made_rows = [d for d in documents() if d.get("path") not in before and d.get("kind") == "change-spec"]
    made = made_rows[0]["path"] if made_rows else None
    if not check("create-fixture: the agent created a change document", bool(made), f"new={made!r}"):
        return
    code, _, offered = attached(conv)
    check("drive-agent-create-is-offered-and-opened: the notice names the new document",
          made in offered, route_note(code, f"made={made!r} offers={offered!r}"), reached=known)
    code, out = api("POST", f"{BASE}/conversations/{conv}/spec-documents/answer", {"path": made, "answer": "open"})
    answered = code == 200
    code, open_doc, offered = attached(conv)
    check("drive-agent-create-is-offered-and-opened: after Open the conversation's document is the new one",
          open_doc == made, route_note(code, f"answer={'ok' if answered else out!r} attached={open_doc!r}"), reached=known)
    check("drive-agent-create-is-offered-and-opened: after Open the notice is gone",
          code == 200 and answered and made not in offered,
          route_note(code, f"offers={offered!r}"), reached=known)
    t1 = time.time()
    # Like the composer: it sends the conversation's open document (what the GET above attached).
    nxt = send("Reply with the single word ok.", conversation_id=conv, spec_document=open_doc)
    queued = entry(nxt.get("queue_entry_id")) or {}
    bound = queued.get("spec_document", "<field absent>")
    check("drive-agent-create-is-offered-and-opened: the next entry names the document",
          bound == made, f"entry.spec_document={bound!r} made={made!r}", reached=bool(queued))
    step = document(made).get("step") or "intake"
    text, where = (turn_context(nxt["queue_entry_id"], t1) if queued else (None, "no entry was queued"))
    check("drive-agent-create-is-offered-and-opened: the next turn's rendered context carries the document's current step",
          bool(text) and f"[step: {step}]" in (text or ""),
          f"context {where} {'lacks' if text is not None and f'[step: {step}]' not in text else 'has'} '[step: {step}]'",
          reached=text is not None)
    if nxt.get("run_id"):
        finished(nxt["run_id"])


def scenario_two_conversations():
    path, why = write_document(
        {"schema_version": 1, "kind": "change-spec", "title": f"Drive X {STAMP}"}, f"Drive X {STAMP}")
    if not check("two-fixture: change document X exists", bool(path), why):
        return
    a = send("Reply with the single word a.", spec_document=path)
    b = send("Reply with the single word b.")
    conv_a, conv_b = a.get("conversation_id"), b.get("conversation_id")
    if not check("two-fixture: conversations A (X) and B (none) exist",
                 bool(conv_a and conv_b and conv_a != conv_b), f"A={a} B={b}"[:300]):
        return
    known = conversation_known(conv_a) and conversation_known(conv_b)
    code, doc_b, _ = attached(conv_b)
    check("drive-two-conversations-keep-their-own-documents: B's attached document is null",
          code == 200 and doc_b is None, route_note(code, f"attached={doc_b!r}")
          + " [its value is right before the build; it fails only because the route is absent]", reached=known)
    again = send("Reply with the single word b2.", conversation_id=conv_b)
    queued = entry(again.get("queue_entry_id")) or {}
    bound = queued.get("spec_document", "<field absent>")
    check("drive-two-conversations-keep-their-own-documents: B's queued entry names no document",
          bool(queued) and bound is None,
          f"entry.spec_document={bound!r} (an absent key is a failure: the entry must carry the field)",
          reached=bool(queued))
    code, doc_a, _ = attached(conv_a)
    check("drive-two-conversations-keep-their-own-documents: A's attached document is still X",
          code == 200 and doc_a == path, route_note(code, f"attached={doc_a!r}"), reached=known)
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
            check(f"{scenario.__name__}-ran-to-its-end", False, f"{type(exc).__name__}: {exc}", reached=False)
    bad = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed\n\n== baseline")
    print("\n".join(baseline))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
