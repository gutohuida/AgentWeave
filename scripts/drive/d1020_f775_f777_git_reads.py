"""F775 + F777 + F760 drive: what the Hub reads out of git.

  F777  an untracked `notes café.md` reaches the `@` picker as itself, and /workspace/file reads it.
  F760  operator evidence with a commit carrying non-ASCII content and a non-ASCII path: the diff
        route answers 200 with the real text and the real path and its patch.
  F775  a real Haiku turn commits its own work (clean tree at the end); a checkpoint of the
        conversation names the file in files_changed.

  py -3.11 scripts/drive/d1020_f775_f777_git_reads.py <project-id> <project-dir>

(after `e2e.py hub-up <profile> <port>` and `e2e.py setup <name>`, on a port that is not 8000/8010)
"""

import json
import pathlib
import subprocess
import sys
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

P, DIR = sys.argv[1], pathlib.Path(sys.argv[2])
B = f"/projects/{P}"
SPEC = f"{B}/project"
SFX = time.strftime("%H%M%S")
failures = []


def say(label, obj=""):
    print(f"--- {label}: {json.dumps(obj, default=str, ensure_ascii=False)[:1500]}", flush=True)


def check(label, ok):
    print(("PASS " if ok else "FAIL ") + label, flush=True)
    if not ok:
        failures.append(label)


def git(*args):
    return subprocess.run(
        ["git", "-C", str(DIR), *args], capture_output=True, text=True, encoding="utf-8"
    ).stdout.strip()


# --- F777 ---------------------------------------------------------------------------------------
(DIR / "notes café.md").write_text("accent\n", encoding="utf-8")
st, paths = e2e.request("GET", f"{B}/workspace/paths")
say("paths", paths if st != 200 else [p for p in paths if "caf" in p])
check("the picker lists the file as itself", st == 200 and "notes café.md" in paths)
st, f = e2e.request("GET", f"{B}/workspace/file?path=" + urllib.parse.quote("notes café.md"))
say("file", (st, f))
check("the file reads", st == 200 and (f or {}).get("content") == "accent\n")

# --- F760 ---------------------------------------------------------------------------------------
(DIR / "todo").mkdir(exist_ok=True)
(DIR / "todo" / "ñandú.py").write_text('name = "Ángel → café"\n', encoding="utf-8")
git("add", "todo")
git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "work")
sha = git("rev-parse", "HEAD")
git("branch", f"work-{SFX}")  # the piece's commit stays reachable on a line of work
git("reset", "-q", "--hard", "HEAD~1")
DOC = f"spec/changes/f760-{SFX}/spec.json"
reqs = [{"key": "alpha", "statement": "It MUST list.", "modal": "MUST"}]
payload = {
    "schema_version": 1, "kind": "change-spec", "title": "F760 " + SFX,
    "scope": {"in_scope": ["list"], "non_goals": ["sync"]}, "requirements": reqs,
    "acceptance_criteria": [{"key": "c-alpha", "requirement": "alpha", "given": "g", "when": "w", "then": "t"}],
    "delivery": {"mode": "none"},
}
e2e.request("POST", f"{SPEC}/documents", {"path": DOC, "title": "F760 " + SFX})
st, out = e2e.request("PUT", f"{SPEC}/documents/{DOC}/content", {"document": payload})
ident = ((out or {}).get("identifiers") or {}).get("alpha", "FR-1")
st, ev = e2e.request("POST", f"{SPEC}/spec/evidence", {
    "identifier": ident, "document": DOC, "summary": "lists", "commit": sha,
    "locator": "todo/ñandú.py", "covers": "full"})
say("evidence", (st, (ev or {}).get("id")))
st, d = e2e.request("GET", f"{SPEC}/spec/evidence/{ev['id']}/diff")
say("diff", (st, [(x["path"], x["patch"][-80:]) for x in (d or {}).get("files", [])], (d or {}).get("reason")))
check("the diff answers 200", st == 200)
files = (d or {}).get("files", [])
check("the path is itself", [x["path"] for x in files] == ["todo/ñandú.py"])
check("the patch carries the real text", any('+name = "Ángel → café"' in x["patch"] for x in files))

# --- F775 ---------------------------------------------------------------------------------------
e2e.cmd_agent(P, "builder", "-", "claude", "claude-haiku-4-5-20251001")
rid = e2e.ro().execute("select runner_id from agents where project_id=? and name='builder'", (P,)).fetchone()[0]
e2e.request("PUT", f"{B}/settings", {"checkpoint_runner_id": rid})
st, task = e2e.request("POST", f"{B}/tasks", {"title": "Add hello", "assignee": "builder",
                                              "description": "Write hello.txt."})
run = e2e.cmd_turn(
    P, "builder",
    "Create a file hello.txt containing the word hello, then run `git add hello.txt` and "
    "`git commit -m \"add hello\"` (you may need -c user.name=t -c user.email=t@t). Then reply 'done'.",
    task=task["id"], fresh=True, perm="workspace",
)
final = e2e.wait_for(run, 10)
say("run", final)
row = dict(e2e.ro().execute(
    "select id, status, conversation_id, snapshot_commit_sha, workspace_dir from runs where id=?", (run,)).fetchone())
say("run row", row)
check("the turn left no snapshot (it committed itself)", not row["snapshot_commit_sha"])
conv = row["conversation_id"]
st, cp = e2e.request("POST", f"{B}/conversations/{conv}/checkpoint", {})
say("checkpoint", (st, (cp or {}).get("files_changed")))
check("the checkpoint names the committed file", st in (200, 201) and "hello.txt" in ((cp or {}).get("files_changed") or []))

print("\nFAILED: " + ", ".join(failures) if failures else "\nALL PASS")
sys.exit(1 if failures else 0)
