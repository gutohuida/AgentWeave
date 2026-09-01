"""Sweep row 1 — Projects.

The representative path from the e2e-loop coverage matrix: open a folder as a project, read and
write its settings, ask for the main-branch suggestion, browse the filesystem, list and read
workspace files, then provoke every refusal the four routers can produce and judge whether each
one says what would work instead.

Surfaces: projects, fs_browse, workspace, project_workspace.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 scripts/drive/t_sweep_row1_projects.py <dir>

Creates a project. Prints its id at the end so the caller can clean it up.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api, show  # noqa: E402

FIXTURE = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\huida\Documents\drive-row1-0901"

results = []


def check(label, ok, detail=""):
    results.append((label, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


print("=" * 78)
print("ROW 1 — PROJECTS.  fixture:", FIXTURE)
print("=" * 78)

# ---------------------------------------------------------------- 1. open
code, opened = api("POST", "/projects/open", {"path": FIXTURE})
show("POST /projects/open", code, opened)
check("open a real git directory returns 200", code == 200, f"got {code}")
if code != 200:
    sys.exit(1)
PID = opened["id"]
print("PROJECT_ID:", PID)

# `ProjectSummary` carries no `main_branch`, so F4's adoption is only observable through
# settings. Asserting it off the open response is what the first version of this script did, and
# it reported a regression that had not happened.
_, s_after_open = api("GET", f"/projects/{PID}/settings")
check(
    "open adopts the repository's branch (F4)",
    s_after_open.get("main_branch") == "main",
    f"settings.main_branch={s_after_open.get('main_branch')!r}",
)
check(
    "directory_state is healthy on a fresh open",
    opened.get("directory_state") == "available",
    f"directory_state={opened.get('directory_state')!r}",
)

# ---------------------------------------------------------------- 2. read back
code, detail = api("GET", f"/projects/{PID}")
check("GET /projects/{id} returns the project", code == 200 and detail.get("id") == PID, f"{code}")
code, settings0 = api("GET", f"/projects/{PID}/settings")
show("GET settings", code, settings0)
check("GET settings returns 200", code == 200, f"{code}")

# ---------------------------------------------------------------- 3. suggestion
code, sug = api("GET", f"/projects/{PID}/main-branch-suggestion")
show("GET main-branch-suggestion", code, sug)
check(
    "suggestion names the repository's branch and reports it as a repository",
    code == 200 and sug.get("suggestion") == "main" and sug.get("is_repository") is True,
    str(sug),
)
check(
    "chosen already equals the suggestion after open (no degraded window)",
    sug.get("chosen") == sug.get("suggestion"),
    f"chosen={sug.get('chosen')!r} suggestion={sug.get('suggestion')!r}",
)

# ---------------------------------------------------------------- 4. partial settings write
# The merge rule: a client that submits only the fields it knows about must not reset the rest.
before = dict(settings0) if isinstance(settings0, dict) else {}
code, after = api("PUT", f"/projects/{PID}/settings", {"main_branch": "main"})
show("PUT settings (one field)", code, after)
check("partial settings write returns 200", code == 200, f"{code}")
if code == 200 and before:
    reset = [k for k, v in before.items() if k != "main_branch" and k in after and after[k] != v]
    check(
        "a one-field settings write resets nothing else",
        not reset,
        f"changed: {reset}",
    )

# a value the model must refuse
code, bad = api("PUT", f"/projects/{PID}/settings", {"checkpoint_threshold_tokens": -5})
show("PUT settings (invalid)", code, bad)
check("an invalid settings value is refused", code >= 400, f"{code}")
check(
    "the settings refusal names the field",
    "checkpoint" in str(bad).lower(),
    str(bad)[:200],
)

# ---------------------------------------------------------------- 5. fs browse
code, roots = api("GET", "/fs/roots")
check(
    "GET /fs/roots returns at least one root",
    code == 200 and len(roots.get("roots", [])) > 0,
    f"{code} {len(roots.get('roots', [])) if code == 200 else ''}",
)
code, listing = api("GET", f"/fs/list?path={FIXTURE.replace(chr(92), '%5C')}")
names = [e["name"] for e in listing.get("entries", [])] if code == 200 else []
show(
    "GET /fs/list",
    code,
    {"path": listing.get("path"), "entries": names} if code == 200 else listing,
)
check(
    "GET /fs/list lists the fixture's subdirectories",
    code == 200 and "src" in names,
    f"{code} {names}",
)
check(
    "/fs/list offers a parent so the picker can walk up",
    code == 200 and bool(listing.get("parent")),
    f"parent={listing.get('parent') if code == 200 else None!r}",
)

# `/fs/list` deliberately answers 200 with an empty listing and a `reason` rather than erroring:
# the picker has to keep showing a navigable parent while telling the operator why this rung is
# empty. So the assertion is on the reason reaching the caller, not on the status.
code, miss = api("GET", "/fs/list?path=C:%5CUsers%5Chuida%5Cno-such-directory-row1")
show("GET /fs/list (missing)", code, miss)
check(
    "a missing directory answers with a reason and a walkable parent, not an error",
    code == 200
    and miss.get("entries") == []
    and bool(miss.get("reason"))
    and bool(miss.get("parent")),
    f"{code} reason={str(miss.get('reason'))[:80]!r}",
)
code, filepath = api("GET", "/fs/list?path=" + (FIXTURE + r"\README.md").replace(chr(92), "%5C"))
show("GET /fs/list (a file, not a directory)", code, filepath)
check(
    "a file path answers with a reason rather than an empty directory",
    code == 200 and filepath.get("entries") == [] and bool(filepath.get("reason")),
    f"{code} reason={str(filepath.get('reason'))[:80]!r}",
)
code, rel = api("GET", "/fs/list?path=zzz-not-absolute")
check("a relative path IS refused outright", code == 400, f"{code} {str(rel)[:120]}")

# ---------------------------------------------------------------- 6. workspace paths
code, paths = api("GET", f"/projects/{PID}/workspace/paths")
if code != 200:
    code, paths = api("GET", f"/workspace/paths?project_id={PID}")
show("GET /workspace/paths", code, paths)
check("GET /workspace/paths returns 200", code == 200, f"{code} {str(paths)[:200]}")
if code == 200 and isinstance(paths, list):
    norm = {p.replace("\\", "/") for p in paths}
    check("tracked files are listed", "src/calc.py" in norm, str(sorted(norm)))
    check("untracked-but-not-ignored files are listed", "NOTES.md" in norm, str(sorted(norm)))
    check(
        "ignored files are NOT listed",
        "build/out.txt" not in norm and "scratch.log" not in norm,
        str(sorted(norm)),
    )
    # F170. The Hub writes `.agentweave/project.json` into a repository it did not create and
    # `repo_hygiene.EXCLUDE_PATTERNS` does not cover it, so git reports it as untracked and the
    # composer's `@path` picker offers the Hub's own marker as a project file.
    check(
        "F170: the Hub's own project marker is not offered as a workspace path",
        ".agentweave/project.json" not in norm,
        str(sorted(norm)),
    )

# ---------------------------------------------------------------- 7. workspace file
code, f = api("GET", f"/projects/{PID}/workspace/file?path=src/calc.py")
if code == 404 and isinstance(f, dict) and "workspace" not in str(f):
    code, f = api("GET", f"/workspace/file?project_id={PID}&path=src/calc.py")
show("GET /workspace/file", code, f)
check(
    "a tracked file reads back with its content",
    code == 200 and "def add" in str(f.get("content", "")),
    f"{code}",
)

code, ign = api("GET", f"/projects/{PID}/workspace/file?path=build/out.txt")
show("GET /workspace/file (ignored)", code, ign)
check("an ignored file is not readable through the workspace", code >= 400, f"{code}")

code, esc = api("GET", f"/projects/{PID}/workspace/file?path=../../../Windows/win.ini")
show("GET /workspace/file (traversal)", code, esc)
check("a traversal out of the workspace is refused", code >= 400, f"{code}")

# ---------------------------------------------------------------- 8. open refusals
code, r = api("POST", "/projects/open", {"path": r"C:\Users\huida\Documents\no-such-dir-row1"})
show("POST /projects/open (missing dir)", code, r)
check("opening a missing directory is refused", 400 <= code < 500, f"{code}")
check(
    "the missing-directory refusal names the path",
    "no-such-dir-row1" in str(r),
    str(r)[:200],
)

code, r = api("POST", "/projects/open", {"path": FIXTURE + r"\README.md"})
show("POST /projects/open (a file)", code, r)
check("opening a file rather than a directory is refused", 400 <= code < 500, f"{code}")

code, again = api("POST", "/projects/open", {"path": FIXTURE})
show("POST /projects/open (same path twice)", code, again)
check(
    "re-opening the same path returns the same project rather than a duplicate",
    code == 200 and again.get("id") == PID,
    f"{code} id={again.get('id') if code == 200 else None}",
)

code, r = api("POST", "/projects/create", {"path": FIXTURE})
show("POST /projects/create (over an existing project)", code, r)
check("create over an already-registered directory is refused", code >= 400, f"{code}")

# ---------------------------------------------------------------- 9. relocate
moved = FIXTURE + "-moved"
subprocess.run(["cmd", "/c", "move", FIXTURE, moved], capture_output=True)
code, missing = api("GET", f"/projects/{PID}")
show("GET /projects/{id} after the directory moved", code, missing)
check(
    "a project whose directory vanished stays listable so its repair is reachable",
    code == 200,
    f"{code}",
)
check(
    "the vanished directory is reported as a typed state, not silence",
    code == 200 and missing.get("directory_state") not in (None, "ok", "healthy", "present"),
    f"directory_state={missing.get('directory_state') if code == 200 else None!r}",
)
code, rel = api("POST", f"/projects/{PID}/relocate", {"path": moved})
show("POST relocate", code, rel)
check("relocate to the new path succeeds", code == 200, f"{code} {str(rel)[:200]}")
code, s = api("GET", f"/projects/{PID}/main-branch-suggestion")
check(
    "the relocated project still reads as a repository",
    code == 200 and s.get("is_repository") is True,
    str(s),
)

# ---------------------------------------------------------------- summary
print()
print("=" * 78)
bad = [r for r in results if not r[1]]
print(f"ROW 1: {len(results) - len(bad)}/{len(results)} passed")
for label, _, detail in bad:
    print("  FAIL:", label, "—", detail)
print("PROJECT_ID:", PID)
print("DIR:", moved)
