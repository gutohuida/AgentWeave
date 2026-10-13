"""Driving sweep 1 (vault), 2026-10-13: the eight vault slices together, against one scratch Hub.

Each slice was driven alone (d1012, d1015-d1017, d1024-d1027). This drives them on one project at
once and watches the seams between them: concurrent distillations of a text, a PDF and an image
uploaded back to back; a contradiction across media; a requirement citing a disputed fact; an
agent's report on a PDF-derived fact; resolving the contradiction under an approved document;
fetch counts after all of it; and what each route answers when the thing behind it is gone.

Start a scratch Hub by hand (see sweep_client.py), then run one phase at a time:

    SWEEP_PORT=8110 SWEEP_KEY=... SWEEP_DB=... py -3.11 scripts/drive/s1013_vault_sweep.py <phase>

State between phases is kept in testbed/sweep1013-vault/state.json.
"""

import json
import pathlib
import sys
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from sweep_client import HAIKU, api, call, git, poll, records, ro, turn  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
TMP = REPO / "testbed" / "sweep1013-vault"
STATE = TMP / "state.json"
ROOT = TMP / "proj"
JOBS = ("vault-distillation", "vault-reports", "spec-vault-check")
DOC = "spec/changes/refund-limits/spec.json"

TEXT = (
    "Refund policy meeting with Acme Retail, 2026-01-10.\n"
    "Attendees: Dana (Acme), Lee (us).\n"
    "Dana opened with the weather and the Christmas rush.\n"
    "Agreed: refunds up to 300 euros need no manager approval.\n"
    "Lee will write it up by Friday.\n"
)
PDF_PAGES = (
    ("Acme Retail - refund policy update, 2026-03-01", "Page 1 of 2. Supersedes January."),
    ("Refunds up to 500 euros need no manager approval.", "Page 2 of 2."),
)
PNG_LINES = ("Shop settings", "Free shipping threshold: 75 euros")
PRIVATE = "Internal note: the Acme account manager's direct line is 555-0199.\n"


def load():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else {}


def save(state):
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def say(label, obj=""):
    print(f"--- {label}: {obj if isinstance(obj, str) else json.dumps(obj, default=str)[:1500]}",
          flush=True)


def make_pdf(path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(path), pagesize=A4)
    for first, second in PDF_PAGES:
        pdf.setFont("Helvetica", 18)
        pdf.drawString(72, 760, first)
        pdf.drawString(72, 730, second)
        pdf.showPage()
    pdf.save()
    return path.read_bytes()


def make_png(path):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (900, 260), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=40)
    draw.text((30, 12), PNG_LINES[0], fill="black", font=font)
    draw.text((30, 140), PNG_LINES[1], fill="black", font=font)
    image.save(path)
    return path.read_bytes()


def upload_file(base, data, media, name, dated=None):
    q = {"name": name, "type": "document"}
    if dated:
        q["dated"] = dated
    code, _, raw = call("POST", f"{base}/vault/files?{urllib.parse.urlencode(q)}", data,
                        content_type=media)
    try:
        return code, json.loads(raw or b"null")
    except ValueError:
        return code, raw.decode(errors="replace")


def setup():
    ROOT.mkdir(parents=True, exist_ok=True)
    git(ROOT, "init", "-q", "-b", "main")
    (ROOT / "README.md").write_text("Scratch project for the vault sweep.\n", encoding="utf-8")
    git(ROOT, "add", "README.md")
    git(ROOT, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(ROOT), "name": "vaultsweep"})
    say("open", (code, project.get("id") if isinstance(project, dict) else project))
    base = f"/projects/{project['id']}"
    code, runner = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    say("runner", (code, runner.get("id")))
    code, agent = api("POST", f"{base}/agents", {"name": "scout", "runner_id": runner["id"]})
    say("agent", (code, str(agent)[:200]))
    for job in JOBS:
        code, out = api("PATCH", f"{base}/manager/jobs/{job}",
                        {"enabled": True, "runner_id": runner["id"]})
        say(f"enable {job}", (code, out))
    save({"pid": project["id"], "base": base, "runner": runner["id"], "agent": "scout"})


def burst():
    """Text, PDF, PNG and a private note uploaded back to back, nothing awaited between them."""
    s = load()
    base = s["base"]
    pdf = make_pdf(TMP / "update.pdf")
    png = make_png(TMP / "settings.png")
    t0 = time.time()
    code, text = api("POST", f"{base}/vault/sources", {"name": "Acme refunds January",
                     "type": "transcript", "content": TEXT, "dated": "2026-01-10"})
    say("text", (code, text))
    code, p = upload_file(base, pdf, "application/pdf", "Acme refund update", "2026-03-01")
    say("pdf", (code, p))
    code, i = upload_file(base, png, "image/png", "Shop settings")
    say("png", (code, i))
    code, n = api("POST", f"{base}/vault/sources", {"name": "Account manager note",
                  "type": "note", "content": PRIVATE, "visibility": "private"})
    say("private", (code, n))
    say("burst seconds", f"{time.time() - t0:.1f}")
    s.update(text=text["id"], pdf=p["id"], png=i["id"], note=n.get("id"))
    save(s)


def watch():
    s = load()
    base = s["base"]
    facts = records(ROOT / "knowledge" / "facts", "fct")
    for key in ("text", "pdf", "png", "note"):
        mine = [(f["id"], f.get("claim")) for f in facts if s.get(key) in (f.get("sources") or [])]
        say(f"facts of {key}", mine)
    say("contradictions", [(c.get("id"), c.get("facts"), c.get("presumed"), c.get("status"))
                           for c in records(ROOT / "knowledge" / "contradictions", "ctr")])
    _, act = api("GET", f"{base}/manager/activity")
    for f in act.get("firings", []):
        say("firing", {k: f.get(k) for k in ("job", "trigger", "outcome", "detail", "subject",
                                             "model", "started_at", "duration_ms")})
    _, m = api("GET", f"{base}/vault/map")
    for e in m.get("entries", []):
        say("map", {k: e.get(k) for k in ("id", "kind", "name", "media_type", "disputed", "presumed",
                                          "superseded_by", "fetches", "sources")})



def payload(fact_id):
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Refund limits",
        "summary": "Refunds below a limit go through without a manager's approval.",
        "problem": "Every refund waits for a manager today, however small.",
        "scope": {"in_scope": ["The approval rule for refunds"], "non_goals": ["Partial refunds"]},
        "requirements": [
            {"key": "small-refunds", "statement": "Refunds up to 300 euros MUST need no manager approval.",
             "modal": "MUST", "rationale": "Agreed with Acme in January.", "party": None,
             "facts": [fact_id]},
            {"key": "free-shipping", "statement": "Orders of 50 euros or more MUST ship free.",
             "modal": "MUST", "rationale": None, "party": None},
        ],
        "acceptance_criteria": [],
        "tasks": [{
            "key": "rule", "title": "Apply the rule", "description": "Skip approval below the limit.",
            "requirements": ["small-refunds", "free-shipping"], "depends_on": [], "files": ["refunds.py"],
            "from": None, "reviewer": None,
        }],
        "algorithms": [], "design": "One comparison against the limit.",
        "evidence": {"checked": ["refunds.py always asks a manager"], "limits": []},
        "lifecycle": "", "open_questions": [],
        "delivery": {"mode": "none", "agent": None, "reviewer": None,
                     "stop_when_queue_empties": False, "stop_at": None, "cron": "*/5 * * * *"},
    }


def spec():
    """A change citing the disputed 300 fact; R2 contradicts the image's 75-euro fact."""
    s = load()
    base = s["base"]
    fact300 = next(f["id"] for f in records(ROOT / "knowledge" / "facts", "fct")
                   if "300" in f.get("claim", ""))
    s["fact300"] = fact300
    s["fact500"] = next(f["id"] for f in records(ROOT / "knowledge" / "facts", "fct")
                        if "500" in f.get("claim", ""))
    save(s)
    q = urllib.parse.quote(DOC)
    say("create", api("POST", f"{base}/project/documents",
                      {"title": "Refund limits", "kind": "change-spec", "path": DOC}))
    say("content", api("PUT", f"{base}/project/documents/{DOC}/content", {"document": payload(fact300)}))
    say("journey", api("POST", f"{base}/project/documents/journey?path={q}",
                       {"size": "small", "step": "intake", "reason": "sweep"}))
    say("warnings before propose", api("GET", f"{base}/vault/warnings?path={q}"))
    say("close", api("POST", f"{base}/project/documents/close-exploration?path={q}"))
    say("propose", api("POST", f"{base}/project/documents/propose?path={q}"))


def approve():
    s = load()
    base = s["base"]
    q = urllib.parse.quote(DOC)
    say("warnings", api("GET", f"{base}/vault/warnings?path={q}"))
    phase = f"{base}/project/documents/phase?path={q}&to=approved"
    say("approve", api("POST", phase, {"reason": "sweep"}))
    say("approve anyway", api("POST", phase, {"reason": "sweep", "approve_anyway": True}))



def ask():
    """The agent reads the vault and reports the PDF's 500 fact as withdrawn (vault-reports)."""
    s = load()
    run_id, status, outputs = turn(s["base"], s["agent"], (
        "Using the project knowledge vault only: what refund amount needs no manager approval, "
        "and above what order value is shipping free? Say if anything is disputed. Then, because "
        "our Acme contact told me by phone the PDF update was withdrawn, report vault fact "
        f"{s['fact500']} to the manager with vault_report saying the March update was withdrawn. "
        "Do nothing else."))
    say("turn", (run_id, status))
    for kind, content, data in outputs:
        if kind in ("tool_use", "text"):
            say(kind, f"{(content or '')[:200]} {(data or '')[:300]}")
    poll(lambda: any(r.get("status") != "pending"
                     for r in api("GET", f"{s['base']}/vault/reports")[1]["reports"]), 180, every=3)
    say("reports", api("GET", f"{s['base']}/vault/reports"))


def resolve():
    """The operator rules the 300 fact stands; then the document's warnings (F588)."""
    s = load()
    base = s["base"]
    ctr = api("GET", f"{base}/vault/contradictions")[1]["contradictions"][0]
    say("resolve", api("POST", f"{base}/vault/contradictions/{ctr['id']}/resolve",
                       {"stands": s["fact300"], "note": "Acme withdrew the March update by phone."}))
    say("warnings", api("GET", f"{base}/vault/warnings?path={urllib.parse.quote(DOC)}"))


def redistil():
    """Distil the ruled-on transcript again (F586, F587)."""
    s = load()
    base = s["base"]
    say("distil", api("POST", f"{base}/vault/sources/{s['text']}/distil"))
    time.sleep(60)
    say("contradictions", api("GET", f"{base}/vault/contradictions"))
    say("warnings", api("GET", f"{base}/vault/warnings?path={urllib.parse.quote(DOC)}"))


def runner_gone():
    """A runner a job uses is deleted; an upload then gets no firing (F589)."""
    s = load()
    base = s["base"]
    _, spare = api("POST", f"{base}/runners", {"name": "Gone", "cli": "claude", "model": HAIKU})
    api("PATCH", f"{base}/manager/jobs/vault-distillation", {"runner_id": spare["id"]})
    say("delete", api("DELETE", f"{base}/runners/{spare['id']}"))
    before = ro("select count(*) from event_logs where event_type='manager_job_fired'")[0][0]
    _, src = api("POST", f"{base}/vault/sources", {"name": "Opening hours", "type": "note",
                 "content": "The shop opens at 9 and closes at 18 on weekdays.\n"})
    time.sleep(20)
    after = ro("select count(*) from event_logs where event_type='manager_job_fired'")[0][0]
    say("firings for the upload", after - before)
    say("distil", api("POST", f"{base}/vault/sources/{src['id']}/distil"))
    api("PATCH", f"{base}/manager/jobs/vault-distillation", {"runner_id": s["runner"]})


def teardown():
    s = load()
    for job in JOBS:
        api("PATCH", f"{s['base']}/manager/jobs/{job}", {"enabled": False})
    say("delete project", api("DELETE", f"/projects/{s['pid']}"))


if __name__ == "__main__":
    globals()[sys.argv[1]]()
