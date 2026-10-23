"""2026-10-23 resilience drive, failure injection (scratch Hub :8113): inject one fault on disk,
call the routes the UI calls, print what each returns, restore the fault.

    py -3.11 scripts/drive/s1023_lc_fault.py <fault> [args]
faults: doc <path> | githead <task-id> | wtfile <task-id> | vaultfile | projjson | runner
"""

import json
import pathlib
import shutil
import sys
import time
import urllib.parse

from s1023_lc_lib import B, DIR, P, q, req

DOC = "spec/changes/silver-selkie/spec.json"


def battery(calls):
    for meth, path, body in calls:
        st, r = req(meth, path, body)
        print(f"{meth} {path[len(B):] if path.startswith(B) else path} -> {st} {json.dumps(r, ensure_ascii=False)[:600]}")


def doc(path=DOC):
    f = DIR / path
    good = f.read_bytes()
    qp = urllib.parse.quote(path)
    calls = [
        ("GET", f"{B}/project/spec?path={qp}", None),
        ("GET", f"{B}/project/documents", None),
        ("GET", f"{B}/project/specs", None),
        ("PUT", f"{B}/project/documents/{path}/content", {"document": {"title": "Corrupt me", "summary": "written while the file is invalid"}}),
        ("POST", f"{B}/project/documents/close-exploration?path={qp}", None),
        ("POST", f"{B}/project/documents/phase?path={qp}&to=approved", {"approve_anyway": True}),
        ("POST", f"{B}/project/documents/{path}/rigor", {"rigor": "standard"}),
        ("GET", f"{B}/project/documents/{path}/rigor-history", None),
        ("POST", f"{B}/project/documents/{path}/reconcile", {}),
        ("GET", f"{B}/project/spec/coverage", None),
        ("GET", f"{B}/project/spec/requirements", None),
        ("POST", f"{B}/project/spec/reindex", {}),
    ]
    f.write_text('{"title": "Corrupt me", "hub": {"phase": "exploring"', encoding="utf-8")
    try:
        battery(calls)
        print("FILE AFTER:", f.read_text(encoding="utf-8")[:300])
    finally:
        f.write_bytes(good)
        print("restored", path)
    battery(calls[:1])


def githead(tid):
    head = DIR / ".git" / "HEAD"
    good = head.read_bytes()
    head.write_text("garbage-not-a-ref\n", encoding="utf-8")
    try:
        battery([
            ("GET", f"{B}/worktrees", None),
            ("GET", f"{B}/worktrees/alpha", None),
            ("GET", f"{B}/worktrees/conflicts", None),
            ("GET", f"{B}/tasks/{tid}/integration-preview", None),
            ("GET", f"{B}/tasks/{tid}/story", None),
            ("POST", f"{B}/tasks/{tid}/checks/run", {}),
            ("POST", f"{B}/project/documents", {"title": "made while git is broken"}),
            ("GET", f"{B}/project/documents", None),
            ("GET", f"/projects/{P}", None),
            ("GET", "/projects", None),
        ])
    finally:
        head.write_bytes(good)
        print("restored .git/HEAD")


def wtfile(tid):
    wt = DIR / ".agentweave" / "tasks" / tid
    aside = wt.with_name(wt.name + "_aside")
    wt.rename(aside)
    wt.write_text("not a directory\n", encoding="utf-8")
    try:
        battery([
            ("GET", f"{B}/worktrees", None),
            ("GET", f"{B}/worktrees/alpha", None),
            ("GET", f"{B}/tasks/{tid}/integration-preview", None),
            ("GET", f"{B}/tasks/{tid}/story", None),
            ("POST", f"{B}/tasks/{tid}/checks/run", {}),
            ("GET", f"{B}/agent/sessions/alpha", None),
        ])
    finally:
        wt.unlink()
        aside.rename(wt)
        print("restored task checkout")


def vaultfile():
    st, s = req("GET", f"{B}/vault/settings")
    print("VAULT SETTINGS", json.dumps(s)[:400])
    k = DIR / "knowledge"
    existed = k.exists()
    aside = DIR / "knowledge_aside"
    if existed:
        k.rename(aside)
    k.write_text("not a directory\n", encoding="utf-8")
    try:
        battery([
            ("GET", f"{B}/vault/map", None),
            ("GET", f"{B}/vault/settings", None),
            ("POST", f"{B}/vault/sources", {"name": "Fault note", "type": "note", "content": "The deploy window is Tuesday."}),
            ("GET", f"{B}/vault/contradictions", None),
            ("GET", f"{B}/vault/reports", None),
            ("GET", f"{B}/vault/warnings", None),
        ])
        print("SOURCES", q("select * from vault_sources where project_id=?", P)[:3] if q("select name from sqlite_master where name='vault_sources'") else "no table")
    finally:
        k.unlink()
        if existed:
            aside.rename(k)
        print("restored knowledge/")


def projjson():
    f = DIR / ".agentweave" / "project.json"
    good = f.read_bytes()
    f.write_text("{not json", encoding="utf-8")
    try:
        battery([
            ("GET", "/projects", None),
            ("GET", f"/projects/{P}", None),
            ("GET", f"{B}/settings", None),
            ("GET", f"{B}/agents", None),
            ("GET", f"{B}/project/documents", None),
            ("POST", "/projects/open", {"path": str(DIR)}),
        ])
        print("FILE AFTER:", f.read_text(encoding="utf-8")[:300])
    finally:
        f.write_bytes(good)
        print("restored project.json")



def doc2(path=DOC):
    """Second pass: bodies the routes accept, against the invalid file."""
    f = DIR / path
    good = f.read_bytes()
    payload = json.loads(good)
    payload.pop("hub", None)
    payload["summary"] = "written while the file was invalid"
    qp = urllib.parse.quote(path)
    f.write_text('{"title": "Corrupt me", "hub": {"phase": "exploring"', encoding="utf-8")
    try:
        battery([
            ("POST", f"{B}/project/documents/{path}/rigor", {"rigor": "contract"}),
            ("POST", f"{B}/project/documents/propose?path={qp}", None),
            ("POST", f"{B}/project/documents/phase?path={qp}&to=proposed", {}),
            ("POST", f"{B}/project/documents/phase?path={qp}&to=archived", {"reason": "fault drive"}),
            ("PUT", f"{B}/project/documents/{path}/content", {"document": payload}),
        ])
        print("FILE AFTER:", f.read_text(encoding="utf-8")[:200].replace("\n", " "))
        print("DOCROW", q("select phase, rigor, step, explore_closed from spec_documents where path=?", path) if q("select name from sqlite_master where name='spec_documents'") else "?")
    finally:
        cur = f.read_text(encoding="utf-8")
        if cur.startswith('{"title": "Corrupt me", "hub"'):
            f.write_bytes(good)
            print("restored", path)
        else:
            print("left the Hub's own rewrite in place")
    battery([("GET", f"{B}/project/spec?path={qp}", None)])



def wtfile2(tid):
    """A project check run against a task checkout that has become a file."""
    show_ = lambda m, path, body=None: battery([(m, path, body)])
    show_("PUT", f"{B}/settings", {"checks": [{"name": "status", "command": "git status --short", "timeout_seconds": 10}]})
    show_("POST", f"{B}/tasks/{tid}/checks/run", {})
    time.sleep(8)
    show_("GET", f"{B}/tasks/{tid}/checks")
    wt = DIR / ".agentweave" / "tasks" / tid
    aside = wt.with_name(wt.name + "_aside")
    wt.rename(aside)
    wt.write_text("not a directory", encoding="utf-8")
    try:
        show_("POST", f"{B}/tasks/{tid}/checks/run", {})
        time.sleep(8)
        show_("GET", f"{B}/tasks/{tid}/checks")
    finally:
        wt.unlink()
        aside.rename(wt)
        print("restored task checkout")
        show_("PUT", f"{B}/settings", {"checks": None})



def projjson2():
    """A corrupt marker, then the remedy the identity-conflict screen offers."""
    f = DIR / ".agentweave" / "project.json"
    good = f.read_bytes()
    f.write_text("{not json", encoding="utf-8")
    try:
        battery([("POST", "/projects/open", {"path": str(DIR), "register_copy_as_new": True})])
        print("FILE AFTER:", f.read_text(encoding="utf-8")[:300])
        print("PROJECTS", q("select id, name, working_directory from projects"))
    finally:
        cur = f.read_text(encoding="utf-8")
        if cur.startswith("{not json"):
            f.write_bytes(good)
            print("restored project.json")
        else:
            print("Hub rewrote project.json; left in place")



def docdir(path="spec/changes/cobalt-selkie/spec.json"):
    """The document's file replaced by a directory of the same name."""
    f = DIR / path
    good = f.read_bytes()
    qp = urllib.parse.quote(path)
    f.unlink()
    f.mkdir()
    try:
        battery([
            ("GET", f"{B}/project/spec?path={qp}", None),
            ("GET", f"{B}/project/documents", None),
            ("PUT", f"{B}/project/documents/{path}/content", {"document": {k: v for k, v in json.loads(good).items() if k != "hub"}}),
            ("POST", f"{B}/project/documents/propose?path={qp}", None),
            ("POST", f"{B}/project/documents/{path}/rigor", {"rigor": "contract"}),
            ("POST", f"{B}/project/spec/reindex", {}),
        ])
    finally:
        f.rmdir()
        f.write_bytes(good)
        print("restored", path)


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
