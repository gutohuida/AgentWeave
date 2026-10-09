"""Acceptance drive for `a-spec-document-is-stored-as-its-payload` (spec.json storage), 2026-10-09.

The change's `drive` and `app-shows-same-page` criteria, written before the build and recorded
failing. Starts its own Hub on :8097 with a fresh database (never :8000 or :8010) serving the bundle
built into hub/hub/static/ui, opens a throwaway git project, and creates a capability, a roadmap
and a change linked to the roadmap's slice, indexed under a home, and records evidence on one
requirement. The Hub that recorded this failing (2026-10-09 iteration 2) created them as .html; the
Hub this drive accepts refuses an .html create (FR-5), so setup creates them as spec.json and turns
them into the legacy corpus with `convert?to=html` (FR-8), the files a pre-change Hub wrote. The
legacy page of each is its .html file's bytes (a legacy document is not served, design D4); the
Chromium baseline is taken before that, since the app does not list a legacy document. Then:

  1. POST /project/spec/convert?to=json answers 200 (no such route on a Hub before the build);
  2. only spec.json files exist under spec/, one per document, none with a spec.html beside it;
  3. the document list holds the same ids at .json paths and no legacy diagnostic;
  4. GET /spec for each returns the legacy page (compared with spec.json read as spec.html:
     the corpus navigation names paths, which are the one difference conversion makes);
  5. requirement identifiers and the recorded evidence are unchanged;
  6. Chromium: the change document, open beside the composer, shows its requirement statement and
     phase chip as before conversion (screenshots before and after);
  7. rewording one requirement and committing changes only that requirement's lines in git: its
     statement, and its digest in the identity block;
  8. moving the journey rewrites the file's hub block (step);
  9. converting back leaves only spec.html files, the original paths and unchanged capability and
     roadmap pages;
 10. converting to json again, twice: the second call changes nothing (tree and database paths).

Stops at the first failure. Run from anywhere:

    py -3.11 scripts/drive/d1010_spec_json.py
"""

import hashlib
import json
import os
import pathlib
import re
import secrets
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
PORT = 8097
HUB = f"http://127.0.0.1:{PORT}"
KEY = "aw_live_" + secrets.token_hex(16)
STAMP = time.strftime("%H%M%S")
TMP = REPO / "testbed" / "drive1010-spec-json" / STAMP
DB = TMP / "hub.db"
SHOT = TMP / "shot"
CAP = "spec/capabilities/pinger/spec"
ROADMAP = "spec/changes/ping-roadmap/spec"
CHANGE = "spec/changes/ping-route/spec"
OLD = "The service MUST answer GET /ping with 200 and the body pong."
NEW = "The service MUST answer GET /ping with 200 and the body pong, and nothing else."
results = []


class Stop(Exception):
    """A failed check the rest of the drive depends on."""


def check(name, ok, detail="", fatal=True):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    if not ok and fatal:
        raise Stop(name)
    return bool(ok)


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
    done = subprocess.run(
        ["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
        cwd=root, check=True, capture_output=True, text=True, encoding="utf-8")
    return done.stdout


def poll(fn, secs=15.0):
    end = time.time() + secs
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001 -- a locator mid-render; try again
            pass
        time.sleep(0.25)
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
    proc = start_hub()
    try:
        drive()
    except Stop:
        pass
    finally:
        stop_hub(proc)
    bad = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed  (artefacts: {TMP})")
    sys.exit(1 if bad else 0)


def payload(kind, title, **more):
    body = {"schema_version": 1, "kind": kind, "title": title, "summary": title + ".",
            "scope": {"in_scope": ["a ping route"], "non_goals": ["anything else"]}}
    body.update(more)
    return body


def payloads(ext):
    requirement = {"key": "pong", "statement": OLD, "modal": "MUST"}
    return {
        f"{CAP}.{ext}": ("capability", payload("capability", "Pinger", requirements=[requirement])),
        f"{ROADMAP}.{ext}": ("roadmap", payload("roadmap", "The ping plan", slices=[
            {"key": "route", "title": "The route", "intent": "Answer ping", "done": "ping answers"}])),
        f"{CHANGE}.{ext}": ("change-spec", payload(
            "change-spec", "A ping route", requirements=[requirement],
            acceptance_criteria=[{"key": "c1", "requirement": "pong", "given": "the service runs",
                                  "when": "GET /ping", "then": "200 and pong"}],
            tasks=[{"key": "t1", "description": "Build the route", "requirements": ["pong"]}],
            delivery={"mode": "none"}, roadmap={"document": f"{ROADMAP}.{ext}", "slice": "route"})),
    }


def tree(root):
    """Every file under spec/ with a digest of its bytes."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((root / "spec").rglob("*")) if p.is_file()}


def doc_rows(base):
    return api("GET", f"{base}/project/documents")


def pages(base, ext):
    out = {}
    for stem in (CAP, ROADMAP, CHANGE):
        code, body = api("GET", f"{base}/project/spec?path={urllib.parse.quote(f'{stem}.{ext}')}")
        out[stem] = body.get("content") if code == 200 and isinstance(body, dict) else f"{code} {body}"
    return out


def legacy_diagnostics(base):
    """The `legacy_html_document` diagnostics the spec tree listing reports (FR-6)."""
    _, body = api("GET", f"{base}/project/specs")
    return [d["path"] for d in body["diagnostics"] if d.get("code") == "legacy_html_document"]


def legacy_pages(root):
    """Each document's legacy page: its .html file's bytes (a legacy document is not served, D4)."""
    out = {}
    for stem in (CAP, ROADMAP, CHANGE):
        file = root / f"{stem}.html"
        out[stem] = file.read_text(encoding="utf-8") if file.is_file() else f"missing {file.name}"
    return out


def evidence(base):
    code, body = api("GET", f"{base}/project/spec/evidence")
    if code != 200:
        return []
    rows = body if isinstance(body, list) else body.get("evidence", [])
    return sorted((r.get("id"), r.get("requirement_id"), r.get("digest"), r.get("summary"))
                  for r in rows)


def identifiers(base):
    _, body = api("GET", f"{base}/project/spec/requirements")
    return sorted(r["identifier"] for r in body.get("requirements", []))


def db_paths():
    return sorted(r[0] for r in ro("select path from spec_documents"))


def drive():
    root = TMP / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A tiny HTTP service.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")

    code, project = api("POST", "/projects/open", {"path": str(root), "name": "specjsondrive"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"

    # Setup: not checks of the change, so a refusal here is a broken drive. Created as spec.json (an
    # .html create is refused now, FR-5), indexed under a home so the pages carry corpus navigation.
    for path, (kind, body) in payloads("json").items():
        code, out = api("POST", f"{base}/project/documents",
                        {"title": body["title"], "kind": kind, "path": path})
        assert code == 201, (path, code, out)
        quoted = urllib.parse.quote(path)
        if kind == "capability":  # a capability's content changes only through a merge
            code, out = api("POST", f"{base}/project/documents/{quoted}/merge", {"payload": body})
        else:
            code, out = api("PUT", f"{base}/project/documents/{quoted}/content", {"document": body})
        assert code == 200, (path, code, out)
    code, out = api("POST", f"{base}/project/spec/reindex", {"home": CAP + ".json"})
    assert code == 200 and out["index"]["written"], (code, out)
    ids = {row["path"]: row["id"] for row in doc_rows(base)[1]["documents"]}
    assert len(ids) == 3, ids
    cap_ident = next(r["identifier"] for r in api(
        "GET", f"{base}/project/spec/requirements?document={urllib.parse.quote(CAP + '.json')}"
    )[1]["requirements"])
    code, out = api("POST", f"{base}/project/spec/evidence",
                    {"identifier": cap_ident, "kind": "manual_observation",
                     "summary": "drove GET /ping by hand", "document": CAP + ".json"})
    assert code == 201, (code, out)

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid))

    def panel(ext, label):
        """The change document open beside the composer: does the frame hold the statement and chip?"""
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.add_init_script(seed)
            page.goto(f"{HUB}/?project={pid}&tab=spec", wait_until="domcontentloaded")
            target = page.locator(f'[data-testid="spec-tree-document-{CHANGE}.{ext}"]')
            poll(lambda: page.locator("[data-testid^=spec-tree-directory-]").count() > 0, 20)
            closed = page.locator("[data-testid^=spec-tree-directory-][aria-expanded=false]")
            for _ in range(6):  # open collapsed directories, one at a time, until the document shows
                if target.count() or not closed.count():
                    break
                closed.first.click()
            poll(lambda: target.count() == 1, 10)
            target.click()

            def frame_text():
                frame = page.frame_locator("[data-testid=spec-frame]")
                return frame.locator("body").inner_text(timeout=2000)

            shown = poll(lambda: "answer GET /ping" in frame_text(), 20)
            text = frame_text()
            page.screenshot(path=f"{SHOT}_{label}.png", full_page=True)
            browser.close()
        return shown, "exploring" in text.lower()

    panel_before = panel("json", "before")
    print(f"baseline panel (statement shown, phase chip shown): {panel_before}", flush=True)

    # The legacy corpus: what a Hub before this change wrote, files and rows at .html paths.
    code, out = api("POST", f"{base}/project/spec/convert?to=html")
    assert code == 200 and len(out["converted"]) == 3, (code, out)
    assert not [f for f in tree(root) if f.endswith("spec.json")], tree(root)
    assert all(p.endswith("/spec.html") for p in db_paths()), db_paths()
    assert len(legacy_diagnostics(base)) == 3, legacy_diagnostics(base)  # FR-6, so check 3 can see one
    ids = {path.replace(".json", ".html"): doc_id for path, doc_id in ids.items()}
    before_pages = legacy_pages(root)
    assert all(page.startswith("<!DOCTYPE html>") for page in before_pages.values()), before_pages
    before_ids = identifiers(base)
    before_evidence = evidence(base)
    assert before_evidence, "setup recorded no evidence"
    git(root, "add", "spec")
    git(root, "commit", "-q", "-m", "documents as html")
    print(f"setup ok: {len(ids)} documents, requirements {before_ids}, evidence {before_evidence}",
          flush=True)

    # 1: the conversion exists and runs.
    code, out = api("POST", f"{base}/project/spec/convert?to=json")
    check("1 the conversion route answers 200", code == 200, f"{code} {str(out)[:300]}")

    # 2-3: only spec.json files; same ids at .json paths.
    files = tree(root)
    check("2 only spec.json files exist under spec/, none with a spec.html beside it",
          not [f for f in files if f.endswith("spec.html")]
          and {f for f in files if f.endswith("spec.json")}
          >= {f"{s}.json" for s in (CAP, ROADMAP, CHANGE)}, str(sorted(files)))
    _, listed = doc_rows(base)
    after_ids = {row["path"]: row["id"] for row in listed["documents"]}
    check("3 the document list holds the same ids at .json paths, with no legacy diagnostic",
          sorted(after_ids.values()) == sorted(ids.values())
          and all(p.endswith("/spec.json") for p in after_ids)
          and not legacy_diagnostics(base),
          f"{after_ids} legacy={legacy_diagnostics(base)}")

    # 4: the app's page is the page it had.
    after_pages = pages(base, "json")
    same = {s: after_pages[s].replace("/spec.json", "/spec.html") == before_pages[s]
            for s in before_pages}
    check("4 GET /spec returns the recorded page for every document", all(same.values()), str(same))

    # 5: identity and evidence.
    check("5 requirement identifiers and the recorded evidence are unchanged",
          identifiers(base) == before_ids and evidence(base) == before_evidence,
          f"{identifiers(base)} vs {before_ids}; {evidence(base)} vs {before_evidence}")

    # 6: Chromium.
    panel_after = panel("json", "after")
    check("6 the change document shows its statement and phase chip as before conversion",
          panel_before == (True, True) and panel_after == (True, True),
          f"before={panel_before} after={panel_after}")

    # 7: a reword is a one-line diff.
    git(root, "add", "spec")
    git(root, "commit", "-q", "-m", "documents as json")
    _, body = payloads("json")[f"{CHANGE}.json"]
    body["requirements"][0]["statement"] = NEW
    code, out = api("PUT", f"{base}/project/documents/{urllib.parse.quote(CHANGE + '.json')}/content",
                    {"document": body})
    check("7a the reword is accepted", code == 200, f"{code} {str(out)[:300]}")
    diff = [line for line in git(root, "diff", "-U0", "--", "spec").splitlines()
            if line[:1] in "+-" and not line.startswith(("+++", "---"))]
    # The reworded requirement's lines: its statement, and its semantic digest in the identity
    # block (`aw_identity.digests`), the one other value that is about that requirement alone.
    statement = [line for line in diff if OLD in line or NEW in line]
    digest = [line for line in diff if line not in statement]
    check("7b the diff holds only the requirement's lines: its statement and its digest",
          len(diff) == 4 and statement[0].startswith("-") and OLD in statement[0]
          and statement[1].startswith("+") and NEW in statement[1]
          and [line[0] for line in digest] == ["-", "+"]
          and all(re.match(r'"[A-Z]+-\d+": "', line[1:].strip()) for line in digest),
          str(diff))

    # 8: the journey is in the file.
    journey = f"{base}/project/documents/journey?path={urllib.parse.quote(CHANGE + '.json')}"
    api("POST", journey, {"size": "large"})
    code, out = api("POST", journey, {"step": "requirements"})
    stored = json.loads((root / f"{CHANGE}.json").read_text(encoding="utf-8"))
    check("8 the move rewrites the file's hub block",
          code == 200 and (stored.get("hub") or {}).get("step") == "requirements",
          f"{code} hub={stored.get('hub')}")

    # 9: and back.
    code, out = api("POST", f"{base}/project/spec/convert?to=html")
    files = tree(root)
    back = legacy_pages(root)
    check("9 the reverse leaves only spec.html files at the original paths, capability and roadmap "
          "pages as before",
          code == 200 and not [f for f in files if f.endswith("spec.json")]
          and all(p.endswith("/spec.html") for p in db_paths())
          and back[CAP] == before_pages[CAP] and back[ROADMAP] == before_pages[ROADMAP],
          f"{code} {sorted(files)} {db_paths()}")

    # 10: idempotent.
    api("POST", f"{base}/project/spec/convert?to=json")
    frozen, frozen_paths = tree(root), db_paths()
    code, out = api("POST", f"{base}/project/spec/convert?to=json")
    check("10 a second conversion changes nothing",
          code == 200 and tree(root) == frozen and db_paths() == frozen_paths, f"{code} {str(out)[:300]}")


if __name__ == "__main__":
    main()
