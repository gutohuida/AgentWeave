"""2026-10-22 day sweep: Knowledge vault x Manager jobs x CLI & lifecycle, scratch Hub
(hub-up vt1022 8115). Phases (each a fresh process; state in testbed/scratch/s1022_vt_state.json):

  setup     project under testbed/drive1022v (two notes that disagree, a PDF, a PNG, a .docx,
            a docs/ folder), haiku runner, alpha, a second project with its own runner
  manager   manager-job doors: unknown key, foreign runner, undeclared model, a model set and
            then the runner swapped to another CLI, an empty runner id, a vault job on with no
            runner and what an upload / Distil / by-path add then say
  refuse    vault refusals: dated format, whitespace text, name length, 415, fake PDF, 413 file
            and text, private location inside the repo / on a missing drive
  distil    distillation on (haiku runner): two dated notes that disagree -> a contradiction
  agent     one alpha turn that reads the vault and files a report (vault_map/vault_read/
            vault_report), and adds a file by path
  state     map, contradictions, reports, manager activity
  off       every manager job off

  py -3.11 scripts/drive/s1022_vt_drive.py <phase>
"""

import json
import os
import pathlib
import sys
import time

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-vt1022.json")
ROOT = pathlib.Path(__file__).resolve().parents[2]
os.environ.setdefault("AW_E2E_ROOT", str(ROOT / "testbed" / "drive1022v"))
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STATE_FILE = ROOT / "testbed" / "scratch" / "s1022_vt_state.json"
S = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
HAIKU = "claude-haiku-4-5-20251001"
JOBS = ("conversation-titles", "vault-distillation", "vault-reports", "spec-vault-check")

NOTE_A = (
    "Export decision, 2026-10-01: the nightly export keeps the ORIGINAL file names, even when two "
    "files share one; the second gets a numeric suffix.\n\nOther notes: the export runs at 02:00 "
    "and writes to the shared drive.\n"
)
NOTE_B = (
    "Export decision, 2026-10-15: the nightly export RENAMES every file to its content hash; "
    "original file names are dropped.\n\nOther notes: the export now runs at 03:00.\n"
)


def save():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(S, indent=2))


def api(method, path, body=None, **kw):
    if path.startswith("~"):
        path = f"/projects/{S['P']}" + path[1:]
    return e2e.request(method, path, body, **kw)


def say(label, obj=""):
    text = obj if isinstance(obj, str) else json.dumps(obj, default=str, ensure_ascii=False)
    print(f"--- {label}: {text[:1800]}", flush=True)


def ro(sql, args=()):
    c = e2e.ro()
    try:
        return [dict(r) for r in c.execute(sql, args)]
    finally:
        c.close()


def job(key, **body):
    st, out = api("PATCH", f"~/manager/jobs/{key}", body)
    keep = ("key", "enabled", "runner_id", "model", "detail")
    say(f"PATCH {key} {body}", (st, {k: out.get(k) for k in keep if k in out} if isinstance(out, dict) else out))
    return st, out


def fixtures(d):
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    (d / "docs" / "nested").mkdir(parents=True, exist_ok=True)
    (d / "docs" / ".hidden").mkdir(parents=True, exist_ok=True)
    (d / "README.md").write_text("# export\n", encoding="utf-8")
    (d / "docs" / "kickoff.md").write_text(NOTE_A, encoding="utf-8")
    (d / "docs" / "nested" / "followup.md").write_text(NOTE_B, encoding="utf-8")
    (d / "docs" / ".hidden" / "secret.md").write_text("token=abc\n", encoding="utf-8")
    (d / "docs" / "café notes.txt").write_text("Les fichiers gardent leur nom d'origine. ✓\n", encoding="utf-8")
    pdf = canvas.Canvas(str(d / "docs" / "retention.pdf"), pagesize=A4)
    pdf.setFont("Helvetica", 18)
    pdf.drawString(72, 760, "Retention policy: exports are kept for 30 days.")
    pdf.drawString(72, 730, "After 30 days they are deleted from the shared drive.")
    pdf.showPage()
    pdf.save()
    image = Image.new("RGB", (900, 200), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=36)
    draw.text((30, 20), "Export owner: Dana (team Atlas)", fill="black", font=font)
    draw.text((30, 110), "Escalate failures within 4 hours", fill="black", font=font)
    image.save(d / "docs" / "owner.png")
    # A Word document is a zip; neither the path door nor the drop dialog lists it as a type.
    import zipfile

    with zipfile.ZipFile(d / "docs" / "minutes.docx", "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document>Minutes: keep names.</w:document>")
    (d / "big.txt").write_text("x" * (1_048_576 + 10), encoding="utf-8")
    with open(d / "huge.pdf", "wb") as fh:
        fh.write(b"%PDF-1.4\n" + b"0" * (10 * 1_048_576 + 10))
    (d / "fake.pdf").write_bytes(b"this is not a pdf at all")


def phase_setup():
    d = pathlib.Path(os.environ["AW_E2E_ROOT"]) / "aw-vt1022"
    d.mkdir(parents=True, exist_ok=True)
    fixtures(d)
    S["P"] = e2e.cmd_setup("aw-vt1022")
    S["DIR"] = str(d)
    save()
    st, rn = api("POST", "~/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
    say("runner", (st, rn.get("id")))
    S["R"] = rn["id"]
    st, cp = api("POST", "~/runners", {"name": "copilot", "cli": "copilot"})
    say("copilot runner", (st, cp.get("id") if isinstance(cp, dict) else cp, cp.get("model") if isinstance(cp, dict) else None))
    S["RC"] = cp.get("id") if isinstance(cp, dict) else None
    st, out = api("POST", "~/agents", {"name": "alpha", "runner_id": rn["id"]})
    say("agent alpha", (st, out.get("name") if isinstance(out, dict) else out))
    other = pathlib.Path(os.environ["AW_E2E_ROOT"]) / "aw-vt1022-other"
    other.mkdir(parents=True, exist_ok=True)
    S["P2"] = e2e.cmd_setup("aw-vt1022-other")
    st, rn2 = e2e.request("POST", f"/projects/{S['P2']}/runners", {"name": "theirs", "cli": "claude", "model": HAIKU})
    S["R2"] = rn2["id"]
    save()
    st, jobs = api("GET", "~/manager/jobs")
    say("jobs", [(j["key"], j.get("enabled"), j.get("runner_id"), j.get("model")) for j in jobs.get("jobs", [])])
    st, vs = api("GET", "~/vault/settings")
    say("vault settings", (st, vs))
    say("ids", S)


def phase_manager():
    st, out = api("PATCH", "~/manager/jobs/nope", {"enabled": True})
    say("unknown job", (st, out))
    job("vault-distillation", runner_id=S["R2"])
    job("vault-distillation", model="gpt-5")
    job("vault-distillation", runner_id=S["R"], model="claude-haiku-4-5-20251001")
    if S.get("RC"):
        # The model was judged against the claude runner; now swap the runner to copilot.
        job("vault-distillation", runner_id=S["RC"])
        st, jobs = api("GET", "~/manager/jobs")
        say("after swap", [(j["key"], j.get("runner_id"), j.get("model")) for j in jobs["jobs"] if j["key"] == "vault-distillation"])
    job("vault-distillation", runner_id="")
    st, jobs = api("GET", "~/manager/jobs")
    say("after empty runner", [(j["key"], j.get("runner_id"), j.get("model")) for j in jobs["jobs"] if j["key"] == "vault-distillation"])
    job("vault-distillation", runner_id=None, model=None)
    job("conversation-titles", runner_id=S["R"])
    job("conversation-titles", runner_id=None)
    # A vault job on with no runner: what each door says.
    job("vault-distillation", enabled=True, runner_id=None)
    st, out = api("POST", "~/vault/sources", {"name": "probe", "type": "note", "content": "Probe text."})
    say("upload while job on, no runner", (st, out))
    if st == 201:
        S["probe"] = out["id"]
        save()
        st2, out2 = api("POST", f"~/vault/sources/{out['id']}/distil")
        say("distil while no runner", (st2, out2))
    st, out = api("POST", "~/vault/paths", {"paths": [str(pathlib.Path(S["DIR"]) / "README.md")], "distil": True})
    say("paths distil=true no runner", (st, out))
    job("vault-reports", enabled=True)
    st, out = api("POST", "~/vault/warnings/check?document=spec/changes/none/spec.json")
    say("warnings check unknown doc", (st, out))
    time.sleep(2)
    st, act = api("GET", "~/manager/activity")
    say("activity", (st, act))
    for key in JOBS:
        job(key, enabled=False)


def phase_refuse():
    base = "~/vault"
    cases = [
        ("dated 12/10/2026", {"name": "d", "type": "note", "content": "x", "dated": "12/10/2026"}),
        ("dated 2026-02-30", {"name": "d", "type": "note", "content": "x", "dated": "2026-02-30"}),
        ("whitespace content", {"name": "w", "type": "note", "content": "   \n  "}),
        ("blank name", {"name": "  ", "type": "note", "content": "x"}),
        ("name 201", {"name": "n" * 201, "type": "note", "content": "x"}),
        ("bad type", {"name": "t", "type": "memo", "content": "x"}),
        ("bad visibility", {"name": "v", "type": "note", "content": "x", "visibility": "public"}),
        ("decision upload", {"name": "dec", "type": "decision", "content": "We decided X."}),
    ]
    for label, body in cases:
        st, out = api("POST", f"{base}/sources", body)
        say(label, (st, out.get("detail") if isinstance(out, dict) and "detail" in out else
                    {k: out.get(k) for k in ("id", "name", "note")} if isinstance(out, dict) else out))
    big = (pathlib.Path(S["DIR"]) / "big.txt").read_text(encoding="utf-8")
    st, out = api("POST", f"{base}/sources", {"name": "big", "type": "note", "content": big}, timeout=120)
    say("text over 1 MiB", (st, out))
    st, out = api("POST", f"{base}/files?name=fake&type=document", raw=b"this is not a pdf", content_type="application/pdf")
    say("fake pdf bytes", (st, out))
    st, out = api("POST", f"{base}/files?name=zip&type=document", raw=b"PK\x03\x04", content_type="application/zip")
    say("415 zip", (st, out))
    huge = (pathlib.Path(S["DIR"]) / "huge.pdf").read_bytes()
    st, out = api("POST", f"{base}/files?name=huge&type=document", raw=huge, content_type="application/pdf", timeout=120)
    say("413 file", (st, out))
    for loc in (str(pathlib.Path(S["DIR"]) / "private-here"), "Q:/nowhere/vault", "relative/dir"):
        st, out = api("PUT", f"{base}/settings", {"private_location": loc})
        say(f"private location {loc}", (st, out))
    st, out = api("PUT", f"{base}/settings", {"default_visibility": "secret"})
    say("default visibility secret", (st, out))
    st, out = api("GET", f"{base}/entries/src-nope")
    say("unknown entry", (st, out))
    st, out = api("POST", f"{base}/sources/src-nope/distil")
    say("distil unknown", (st, out))
    st, out = api("POST", f"{base}/contradictions/ctr-nope/resolve", {"stands": None, "note": "x"})
    say("resolve unknown", (st, out))
    st, out = api("POST", f"{base}/reports/rep-nope/close", {"note": "x"})
    say("close unknown report", (st, out))
    # By path: unsupported type, outside path, hidden folder, a folder.
    d = pathlib.Path(S["DIR"])
    st, out = api("POST", f"{base}/paths", {"paths": [str(d / "docs" / "minutes.docx"), "C:/Windows/win.ini",
                                                       str(d / "docs" / ".hidden" / "secret.md")], "distil": False})
    say("paths refusals", (st, out))
    st, out = api("POST", f"{base}/paths", {"paths": [str(d / "docs")], "distil": False})
    say("paths folder", (st, {"counts": out.get("counts"), "results": [(r.get("path"), r.get("status"), r.get("reason"))
                                                                       for r in out.get("results", [])]} if isinstance(out, dict) else out))
    S["folder"] = [r["source"]["id"] for r in out.get("results", []) if r.get("status") == "added"]
    save()
    st, out = api("POST", f"{base}/paths", {"paths": [str(d / "docs")], "distil": False})
    say("paths folder again", (st, out.get("counts") if isinstance(out, dict) else out))


def phase_distil():
    job("vault-distillation", enabled=True, runner_id=S["R"])
    for key, text, day in (("A", NOTE_A, "2026-10-01"), ("B", NOTE_B, "2026-10-15")):
        st, out = api("POST", "~/vault/sources", {"name": f"Export note {key}", "type": "note", "content": text, "dated": day})
        say(f"note {key}", (st, {k: out.get(k) for k in ("id", "name", "dated", "note")}))
        S[f"note{key}"] = out["id"]
        save()
        time.sleep(1)
    end = time.time() + 420
    while time.time() < end:
        st, c = api("GET", "~/vault/contradictions")
        st2, act = api("GET", "~/manager/activity")
        rows = act.get("activity") or act.get("firings") or [] if isinstance(act, dict) else []
        if c.get("contradictions") and len(rows) >= 3:
            break
        time.sleep(10)
    say("contradictions", c)
    say("activity", act)


def phase_agent():
    job("vault-reports", enabled=True, runner_id=S["R"])
    msg = (
        "Use the AgentWeave vault. 1) Call vault_map. 2) Read the entry about the nightly export's file "
        "names with vault_read. 3) The repository's README says nothing about names; file ONE vault_report "
        "saying the vault's two export notes disagree about file names and asking which holds. "
        "4) Add the file docs/café notes.txt to the vault with vault_add (distil false). Then stop."
    )
    st, res = api("POST", "~/agent/trigger", {"agent": "alpha", "message": msg,
                                              "overrides": {"permission_mode": "workspace"}})
    say("trigger", (st, {k: res.get(k) for k in ("run_id", "status", "detail")}))
    S["run"] = res.get("run_id")
    save()
    if S["run"]:
        e2e.wait_for(S["run"], 12)
        e2e.dump_turn(S["run"])
    end = time.time() + 240
    while time.time() < end:
        st, r = api("GET", "~/vault/reports")
        if any(x.get("status") != "pending" for x in r.get("reports", [])):
            break
        time.sleep(10)
    say("reports", r)


def phase_state():
    st, m = api("GET", "~/vault/map")
    for e in m.get("entries", []):
        print(" ", e["id"], e["kind"], e.get("type"), e.get("visibility"), e.get("fetches"),
              (e.get("name") or e.get("claim") or "")[:70], "disputed" if e.get("disputed") else "",
              "presumed" if e.get("presumed") else "", e.get("superseded_by") or "")
    say("contradictions", api("GET", "~/vault/contradictions"))
    say("reports", api("GET", "~/vault/reports"))
    say("activity", api("GET", "~/manager/activity"))


def phase_off():
    for key in JOBS:
        job(key, enabled=False)


if __name__ == "__main__":
    globals()[f"phase_{sys.argv[1]}"]()
