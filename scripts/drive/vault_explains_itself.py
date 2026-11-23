"""Acceptance drive for `a-vault-page-that-says-what-it-holds` (VPTSW-1), 2026-11-23: criterion
`drive-vault-explains-itself` of FR-1, written failing first, before the Overview, the facts' uses
route and the text search are built. VPTSW-5 runs it green.

Starts its own Hub from THIS checkout's `hub/` on the first free port from 8140 with a fresh
database under testbed/ (never :8000 or :8010), serving the bundle built into hub/hub/static/ui. It
opens a scratch git repository in the system temp directory as the project, with a Haiku runner on vault-distillation and one
agent on the same runner. Setup (any failure stops the drive, so nothing after it is guessed at):

  s0  the note a new project's vault starts with is archived, so the vault holds one source;
  s1  the transcript is uploaded; its line 3 says the refund limit without approval is 437 euros;
  s2  vault-distillation (Haiku) draws a fact whose claim holds 437 and cites line 3;
  s3  a change document is saved whose requirement lists that fact in `facts`, and the Hub mints
      the requirement's identifier;
  s4  a Haiku turn of the agent calls vault_read on the transcript exactly once, and the map then
      counts the transcript opened once, by that agent.

Then Chromium opens the Vault tab, freshly for each check, and finds everything by its accessible
name (the regions, buttons and radios VaultOverview and VaultLibrary name). Every check runs, so a
baseline names each one's own failure:

  overview          the region 'In the vault' says '1 source and <N> facts', N the facts the map
                    lists, and the button 'Transcripts: 1' is there;
  cited-by-spec     picking the radio 'Cited by a spec' lists the refund fact ('Open fact: <claim>')
                    saying 'Cited by <FR-n> of Refund limits';
  agents-open       the region 'What profiles open' lists 'Open transcript: <name>' with 'Opened 1x'
                    and 'by <agent>';
  search-facts      '437' typed in 'Search the vault': the region 'Facts holding 437' lists the
                    refund fact with 437 in a <mark>;
  search-documents  the region 'Documents holding 437' lists the transcript with 'Line 3';
  fact-line-3       opening that fact from the results shows the transcript's reader (article named
                    for it) with line 3 marked and no other line.

Today it fails at `overview`: the page has no Overview. Each check prints one line in the
`drive_baseline` shape,
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
and the drive exits 1 if any failed. Two Haiku calls are spent (the distillation and the turn).
Artefacts (hub.log, the map, screenshots) go to testbed/drive-vault-explains/<HHMMSS>/.

    py -3.11 scripts/drive/vault_explains_itself.py
"""

import json
import os
import pathlib
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
KEY = "aw_live_" + secrets.token_hex(16)
STAMP = time.strftime("%H%M%S")
TMP = REPO / "testbed" / "drive-vault-explains" / STAMP
DB = TMP / "hub.db"
HAIKU = "claude-haiku-4-5-20251001"
DISTIL = "vault-distillation"
AGENT = "reader"
WAIT = 4 * 60
DOC = "spec/changes/refund-limits/spec.json"
DOC_TITLE = "Refund limits"
REQ = "refund-limit"
NAME = "Acme refund call"
TRANSCRIPT = (
    "Refund policy call with Acme Retail, 2026-11-20.\n"
    "Present: Dana (Acme), Luis (us).\n"
    "Dana: the refund limit without approval is 437 euros.\n"
    "Luis: understood, anything above that goes to a manager.\n"
    "Dana: yes, and the manager answers within one working day.\n"
)
assert "437" in TRANSCRIPT.splitlines()[2]
CHECKS = ("overview", "cited-by-spec", "agents-open", "search-facts", "search-documents", "fact-line-3")
results = {}


def free_port():
    for port in range(8140, 8170):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return port
    sys.exit("no free port in 8140-8169")


PORT = free_port()
HUB = f"http://127.0.0.1:{PORT}"


class Stop(Exception):
    """A setup step failed; the checks after it would only guess."""


def setup(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    if not ok:
        raise Stop(name)


def record(key, reached, passed, detail):
    results[key] = passed
    print(f"check {key}: reached={'yes' if reached else 'no'} "
          f"failed_at_assertion={'no' if passed or not reached else 'yes'} -- "
          f"{'PASS' if passed else 'FAIL'}: {detail}", flush=True)


def api(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:2000]
    except urllib.error.URLError as exc:
        return 0, str(exc)


def ro(sql, args=()):
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                   cwd=root, check=True, capture_output=True)


def poll(fn, secs=15.0, every=0.5):
    end = time.time() + secs
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001 -- a locator mid-render or a file mid-write
            pass
        time.sleep(every)
    return False


def start_hub():
    TMP.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(TMP / "hub.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    if not poll(lambda: api("GET", "/projects")[0] == 200, 90):
        proc.kill()
        sys.exit(f"hub did not come up; see {TMP / 'hub.log'}")
    return proc


def stop_hub(proc):
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


def main():
    print(f"hub on :{PORT}, artefacts {TMP}", flush=True)
    proc = start_hub()
    base = None
    try:
        base, seeded = seed()
        browse(seeded)
    except Stop:
        pass
    finally:
        if base:  # never leave the job enabled
            api("PATCH", f"{base}/manager/jobs/{DISTIL}", {"enabled": False})
        stop_hub(proc)
    bad = [key for key in CHECKS if not results.get(key)]
    print(f"\n{len(CHECKS) - len(bad)} of {len(CHECKS)} checks passed"
          + (f"; failed: {', '.join(bad)}" if bad else "") + f"  (artefacts: {TMP})")
    sys.exit(1 if bad else 0)


def payload(fact_id):
    return {
        "schema_version": 1, "kind": "change-spec", "title": DOC_TITLE,
        "summary": "Refunds below the agreed limit go through without a manager's approval.",
        "problem": "Every refund waits for a manager today, however small.",
        "scope": {"in_scope": ["The approval rule for refunds"], "non_goals": ["Partial refunds"]},
        "requirements": [
            {"key": REQ, "statement": "Refunds up to 437 euros MUST need no manager approval.",
             "modal": "MUST", "rationale": "Agreed with Acme on 2026-11-20.", "party": None,
             "facts": [fact_id]},
        ],
        "acceptance_criteria": [],
        "tasks": [{
            "key": "rule", "title": "Apply the rule", "description": "Skip approval below the limit.",
            "requirements": [REQ], "depends_on": [], "files": ["refunds.py"],
            "from": None, "reviewer": None,
        }],
        "algorithms": [],
        "design": "One comparison against the limit.",
        "evidence": {"checked": ["refunds.py always asks a manager"], "limits": []},
        "lifecycle": "",
        "open_questions": [],
        "delivery": {"mode": "none", "agent": None, "reviewer": None,
                     "stop_when_queue_empties": False, "stop_at": None, "cron": "*/5 * * * *"},
    }


def operator_map(base):
    code, body = api("GET", f"{base}/vault/map")
    if code != 200:
        raise Stop(f"GET /vault/map answered {code}: {str(body)[:300]}")
    return body["entries"]


def refund_facts(entries, source_id):
    return [e for e in entries if e.get("kind") == "fact" and source_id in (e.get("sources") or [])
            and "437" in (e.get("opening") or e.get("name") or "")]


def cites_line_3(root, fact_id):
    path = root / "knowledge" / "facts" / f"{fact_id}.json"
    if not path.is_file():
        return False, "no fact record"
    cited = json.loads(path.read_text(encoding="utf-8")).get("citations") or []
    lines = [(c.get("line_start"), c.get("line_end")) for c in cited]
    return any(s is not None and s <= 3 <= (e or s) for s, e in lines), f"citations={lines}"


def vault_reads():
    """Every entry id the agents' entry route answered 200 for at offset 0, from the Hub's access
    log: what the agent asked for, apart from what the Hub counted (d1027's recipe)."""
    log = (TMP / "hub.log").read_text(encoding="utf-8", errors="replace")
    pattern = r'"GET /api/v1/agent-actions/vault/entries/([\w-]+)(?:\?offset=0)? HTTP/1\.1" 200'
    return re.findall(pattern, log)


def seed():
    # Outside the repository: a project inside a task checkout is refused (invalid_project_path).
    root = pathlib.Path(tempfile.mkdtemp(prefix="aw-vault-explains-")) / "proj"
    root.mkdir(parents=True)
    print(f"project at {root}", flush=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the vault-explains-itself drive.\n",
                                    encoding="utf-8")
    (root / "refunds.py").write_text("# every refund asks a manager\n", encoding="utf-8")
    git(root, "add", "README.md", "refunds.py")
    git(root, "commit", "-q", "-m", "seed")

    code, project = api("POST", "/projects/open", {"path": str(root), "name": "vaultexplains"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    assert code in (200, 201), (code, haiku)
    code, out = api("POST", f"{base}/agents", {"name": AGENT, "runner_id": haiku["id"]})
    assert code in (200, 201), (code, out)
    # A new project's vault starts with the Hub's own data note. Archived before distillation is
    # on (so it is never distilled): the vault then holds only the transcript, and an archived
    # source is counted nowhere (FR-1).
    seeded_notes = [e for e in operator_map(base) if e.get("kind") != "fact"]
    for note in seeded_notes:
        code, out = api("POST", f"{base}/vault/sources/{note['id']}/archive")
        setup(f"s0 the seeded note {note.get('name')!r} is archived", code == 200, f"{code} {str(out)[:200]}")
    code, out = api("PATCH", f"{base}/manager/jobs/{DISTIL}", {"enabled": True, "runner_id": haiku["id"]})
    assert code == 200, (code, out)

    # s1, s2: the transcript and its refund fact.
    code, source = api("POST", f"{base}/vault/sources",
                       {"name": NAME, "type": "transcript", "content": TRANSCRIPT, "dated": "2026-11-20"})
    setup("s1 the transcript is uploaded", code == 201 and isinstance(source, dict),
          f"{code} {str(source)[:300]}")
    sid = source["id"]
    got = poll(lambda: refund_facts(operator_map(base), sid), WAIT, every=3)
    entries = operator_map(base)
    # Haiku may draw more than one fact holding 437 (the limit, and what happens above it); the
    # refund fact is the one resting on line 3.
    cited = {f["id"]: cites_line_3(root, f["id"]) for f in refund_facts(entries, sid)}
    facts = [f for f in refund_facts(entries, sid) if cited[f["id"]][0]]
    setup("s2 Haiku distils a fact holding 437 that cites line 3", got and facts,
          f"claims={[e.get('opening') or e.get('name') for e in entries if e.get('kind') == 'fact']} "
          f"citations={[c for _, c in cited.values()]}")
    fact = facts[0]

    # s3: the document whose requirement lists the fact.
    code, out = api("POST", f"{base}/project/documents",
                    {"title": DOC_TITLE, "kind": "change-spec", "path": DOC})
    assert code == 201, (code, out)
    code, out = api("PUT", f"{base}/project/documents/{DOC}/content", {"document": payload(fact["id"])})
    saved = json.loads((root / DOC).read_text(encoding="utf-8")) if (root / DOC).is_file() else {}
    kept = next((r for r in saved.get("requirements", []) if r.get("key") == REQ), {}).get("facts")
    identifier = ((saved.get("aw_identity") or {}).get("requirements") or {}).get(REQ)
    setup("s3 the document is saved, its requirement lists the fact and has an identifier",
          code == 200 and kept == [fact["id"]] and bool(identifier),
          f"{code} {str(out)[:200]} facts={kept} identifier={identifier}")

    # s4: the agent opens the transcript once.
    known = {r for (r,) in ro("select id from runs")}
    code, run = api("POST", f"{base}/agent/trigger", {"agent": AGENT, "message": (
        f"Use the knowledge vault tool vault_read exactly once, with entry_id {sid}. Do not call "
        "vault_map or any other tool, and do not read it a second time. Then reply 'done'.")})
    assert code in (200, 202), (code, run)
    run_id = (run or {}).get("run_id") if isinstance(run, dict) else None
    if not run_id:
        poll(lambda: {r for (r,) in ro("select id from runs where agent=?", (AGENT,))} - known, 60)
        fresh = {r for (r,) in ro("select id from runs where agent=?", (AGENT,))} - known
        run_id = next(iter(fresh), None)
    assert run_id, (code, run)
    ended = poll(lambda: ro("select status from runs where id=?", (run_id,))[0][0]
                 not in ("running", "queued", "starting"), 6 * 60, every=2)
    reads = vault_reads()
    entries = operator_map(base)
    (TMP / "map.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
    mine = next((e for e in entries if e["id"] == sid), {})
    readers = [r.get("agent") for r in mine.get("readers") or []]
    setup("s4 the agent's turn reads the transcript once and the map counts it",
          ended and reads == [sid] and mine.get("fetches") == 1 and readers == [AGENT],
          f"run={run_id} ended={ended} reads={reads} fetches={mine.get('fetches')} readers={readers}")

    sources = [e for e in entries if e.get("kind") != "fact"]
    setup("s5 the map lists one source", len(sources) == 1, f"sources={[e.get('name') for e in sources]}")
    seeded = {
        "pid": pid, "sid": sid, "fact": fact["id"], "claim": fact.get("opening") or fact["name"],
        "identifier": identifier,
        "facts": sum(1 for e in entries if e.get("kind") == "fact"),
    }
    (TMP / "seeded.json").write_text(json.dumps(seeded, indent=2), encoding="utf-8")
    return base, seeded


def browse(seeded):
    from playwright.sync_api import sync_playwright

    pid = seeded["pid"]
    init = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_init_script(init)
        for key in CHECKS:
            page = context.new_page()
            try:
                reached = open_vault(page, pid)
                if not reached:
                    record(key, False, False, "the Vault tab did not render its search box within 30 s")
                else:
                    passed, detail = globals()["check_" + key.replace("-", "_")](page, seeded)
                    record(key, True, passed, detail)
            except Exception as exc:  # noqa: BLE001 -- a drive error is a check not reached
                record(key, False, False, f"drive error: {exc!r}"[:400])
            finally:
                try:
                    page.screenshot(path=str(TMP / f"shot_{key}.png"), full_page=True)
                except Exception:  # noqa: BLE001
                    pass
                page.close()
        browser.close()


def open_vault(page, pid):
    page.goto(f"{HUB}/?project={pid}&tab=vault", wait_until="domcontentloaded")
    search = page.get_by_role("searchbox", name="Search the vault")
    box = page.get_by_role("textbox", name="Search the vault")
    if not poll(lambda: search.count() == 1 or box.count() == 1, 30):
        return False
    # The map is in once the transcript's row is listed somewhere on the page.
    poll(lambda: page.get_by_text(NAME).count() > 0, 15)
    return True


def search_box(page):
    search = page.get_by_role("searchbox", name="Search the vault")
    return search if search.count() == 1 else page.get_by_role("textbox", name="Search the vault")


def region(page, name):
    return page.get_by_role("region", name=name, exact=True)


def fact_button(scope, seeded):
    """The refund fact's row, by its accessible name (FactRow names it for the claim)."""
    return scope.get_by_role("button", name=f"Open fact: {seeded['claim']}", exact=True)


def check_overview(page, seeded):
    lead = region(page, "In the vault")
    if not poll(lambda: lead.count() == 1, 15):
        return False, "no region 'In the vault': the page has no Overview"
    text = " ".join(lead.inner_text().split())
    n = seeded["facts"]
    want = f"1 source and {n:,} {'fact' if n == 1 else 'facts'}"
    kind = page.get_by_role("button", name="Transcripts: 1", exact=True)
    ok = want in text and kind.count() == 1
    return ok, f"lead={text[:200]!r}, wanted {want!r}; 'Transcripts: 1' buttons={kind.count()}"


def check_cited_by_spec(page, seeded):
    radio = page.get_by_role("radio", name=re.compile(r"^Cited by a spec"))
    if not poll(lambda: radio.count() == 1, 15):
        return False, "no radio 'Cited by a spec' (Important facts by) on the page"
    radio.click()
    important = region(page, "Important facts")
    row = fact_button(important, seeded)
    if not poll(lambda: row.count() == 1, 10):
        return False, f"'Cited by a spec' lists no refund fact; region text={important.inner_text()[:300]!r}"
    text = " ".join(row.inner_text().split())
    want = f"Cited by {seeded['identifier']} of {DOC_TITLE}"
    return want in text, f"row={text[:300]!r}, wanted {want!r}"


def check_agents_open(page, seeded):
    section = region(page, "What profiles open")
    if not poll(lambda: section.count() == 1, 15):
        return False, "no region 'What profiles open' on the page"
    row = section.get_by_role("button", name=f"Open transcript: {NAME}", exact=True)
    if not poll(lambda: row.count() == 1, 10):
        return False, f"the transcript is not listed; region text={section.inner_text()[:300]!r}"
    text = " ".join(row.inner_text().split())
    ok = "Opened 1×" in text and f"by {AGENT}" in text
    return ok, f"row={text[:300]!r}, wanted 'Opened 1×' and 'by {AGENT}'"


def type_437(page):
    search_box(page).fill("437")


def check_search_facts(page, seeded):
    type_437(page)
    section = region(page, "Facts holding 437")
    if not poll(lambda: section.count() == 1, 15):
        return False, "no region 'Facts holding 437': the search lists no facts"
    row = fact_button(section, seeded)
    if not poll(lambda: row.count() == 1, 10):
        return False, f"the refund fact is not listed; region text={section.inner_text()[:300]!r}"
    marked = [m.inner_text() for m in row.locator("mark").all()]
    return marked == ["437"], f"marked={marked}, wanted ['437']"


def check_search_documents(page, seeded):
    type_437(page)
    section = region(page, "Documents holding 437")
    if not poll(lambda: section.count() == 1, 15):
        return False, "no region 'Documents holding 437': the search lists no documents"
    row = section.get_by_role("button", name=f"Open transcript: {NAME}", exact=True)
    ok = poll(lambda: row.count() == 1 and "Line 3" in row.inner_text(), 15)
    text = " ".join(row.inner_text().split()) if row.count() == 1 else ""
    return ok, f"row={text[:300]!r}, wanted the transcript with 'Line 3'"


def check_fact_line_3(page, seeded):
    type_437(page)
    section = region(page, "Facts holding 437")
    row = fact_button(section, seeded)
    if not poll(lambda: row.count() == 1, 15):
        return False, "no refund fact under 'Facts holding 437' to open"
    row.click()
    reader = page.get_by_role("article", name=NAME, exact=True)
    if not poll(lambda: reader.count() == 1, 10):
        return False, "opening the fact shows no reader for the transcript"
    lit = reader.locator("[data-testid^=vault-line-][data-highlighted=true]")
    if not poll(lambda: lit.count() > 0, 10):
        return False, "the transcript opens with no line marked"
    marked = [el.get_attribute("data-testid") for el in lit.all()]
    return marked == ["vault-line-3"], f"marked={marked}, wanted ['vault-line-3']"


if __name__ == "__main__":
    main()
