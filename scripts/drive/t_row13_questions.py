"""Row 13 (Questions) and row 14 (Permissions) — the two operator-in-the-loop surfaces.

Both need a real agent turn, so both were recorded "not reached"/"partial" by the
2026-08-28 sweep. Driven here on a cheap runner (Haiku) per the operator's standing
directive: these rows assert that a turn *starts, blocks on the operator, and resumes*,
not that the agent writes anything good.

Setup only in this module; the assertions live in the row_* functions.
"""

import json
import sys

from aw import api

WORKDIR = "C:\\Users\\huida\\Documents\\drive-2026-08-29"
PROJECT_NAME = "drive-2026-08-29"
HAIKU = "claude-haiku-4-5-20251001"


def show(label, code, body):
    text = body if isinstance(body, str) else json.dumps(body)
    print(f"{label:<38} -> {code} {text[:300]}")
    return body


def ensure_project():
    code, body = api("GET", "/projects")
    rows = body.get("projects") if isinstance(body, dict) else body
    for p in rows or []:
        if p.get("name") == PROJECT_NAME:
            print("project exists: {}".format(p["id"]))
            return p["id"]
    # /projects is GET-only; the operator's "open a folder" flow is /projects/create,
    # which takes `path`, not `working_directory`. Fetched from /openapi.json rather
    # than guessed — guessing cost two calls here already.
    code, body = api("POST", "/projects/open", {"path": WORKDIR, "name": PROJECT_NAME})
    show("POST /projects/open", code, body)
    if code >= 300:
        sys.exit("could not create project")
    return body["id"]


def ensure_runner(project):
    code, body = api("GET", f"/projects/{project}/runners")
    rows = body.get("runners") if isinstance(body, dict) else body
    for r in rows or []:
        if r.get("name") == "Haiku (cheap)":
            print("runner exists: {}".format(r["id"]))
            return r["id"]
    code, body = api(
        "POST",
        f"/projects/{project}/runners",
        {"name": "Haiku (cheap)", "cli": "claude", "model": HAIKU},
    )
    show("POST /runners", code, body)
    if code >= 300:
        sys.exit("could not create runner")
    return body["id"]


def ensure_agent(project, name, runner):
    code, body = api(
        "POST",
        f"/projects/{project}/agents",
        {"name": name, "runner_id": runner},
    )
    if code >= 300:
        code, body = api("GET", f"/projects/{project}/agents")
        rows = body.get("agents") if isinstance(body, dict) else body
        for a in rows or []:
            # The roster listing carries no `id` — agents are addressed by name there,
            # while POST /agents returns an id. Name is what /agent/trigger wants.
            if a.get("name") == name:
                print(f"agent exists: {name}")
                return name
        sys.exit(f"could not create or find agent {name}")
    show(f"POST /agents {name}", code, body)
    return body["id"]


if __name__ == "__main__":
    p = ensure_project()
    r = ensure_runner(p)
    a = ensure_agent(p, "asker", r)
    print(f"\nPROJECT={p} RUNNER={r} AGENT={a}")
