"""Projects x Runners & models sweep 2026-10-20, API phases (scratch Hub :8147, profile p1020).

    fs       -- the in-app folder browser: GET /fs/roots, GET /fs/list over awkward paths, and
                whether a slow listing (an unreachable UNC share) holds up every other request
    runners  -- create per CLI, aliases stored as written, undeclared refused, every door
    fs-block / open-block -- a UNC path to a blackholed host: does the whole Hub wait?
    holders  -- delete a runner an agent, a manager job and the checkpoint setting hold

    py -3.11 scripts/drive/s1020_p_api.py fs|runners|holders
"""

import sys
import threading
import time
import urllib.parse

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1020_p_lib import P, req, show  # noqa: E402


def ls(path, limit=500):
    started = time.time()
    status, res = req("GET", "/fs/list?path=" + urllib.parse.quote(path, safe=""))
    took = time.time() - started
    if isinstance(res, dict) and "entries" in res:
        names = [e["name"] for e in res["entries"]]
        print(
            f"--- {path!r} -> {status} {took:.2f}s path={res['path']!r} parent={res['parent']!r}"
            f" reason={res['reason']!r}\n    entries[{len(names)}]: {str(names)[:limit]}"
        )
    else:
        print(f"--- {path!r} -> {status} {took:.2f}s {str(res)[:limit]}")
    return status, res


def fs():
    show("GET", "/fs/roots")
    for path in [
        "C:\\",
        "/",
        "~",
        "C:\\Users\\huida",
        "C:\\Users\\huida\\Application Data",
        "C:\\Users\\huida\\Documents\\aw-p-1020",
        "C:\\does\\not\\exist",
        "C:\\Windows\\notepad.exe",
        "relative\\path",
        "C:\\Users\\..\\Users",
        "C:\\System Volume Information",
        "C:",
        "c:\\users",
        "C:\\Users\\huida\\Documents\\x\ty",
        "\\\\localhost\\c$",
    ]:
        ls(path)


UNC_BLACKHOLE = "\\\\10.255.255.1\\share"


def blocking(label, call):
    """Does one slow call hold the whole Hub? Time /health while *call* runs."""
    done = {}

    def slow():
        started = time.time()
        done["result"] = call()
        print(f"  {label} returned after {time.time() - started:.2f}s: {str(done['result'])[:300]}")

    worker = threading.Thread(target=slow)
    worker.start()
    time.sleep(0.5)
    for _ in range(6):
        started = time.time()
        status, _ = req("GET", "/health")
        print(f"  /health meanwhile -> {status} in {time.time() - started:.2f}s")
        if not worker.is_alive():
            break
        time.sleep(1)
    worker.join()


def fs_block(path=UNC_BLACKHOLE):
    blocking(f"GET /fs/list {path}", lambda: ls(path))


def open_block(path=UNC_BLACKHOLE + "\\proj"):
    blocking(f"POST /projects/open {path}", lambda: req("POST", "/projects/open", {"path": path}))
    blocking(
        f"POST /projects/create {path}", lambda: req("POST", "/projects/create", {"path": path})
    )
    blocking(
        f"POST /projects/{P}/relocate {path}",
        lambda: req("POST", f"/projects/{P}/relocate", {"path": path}),
    )


def catalog():
    status, res = req("GET", "/model-catalog")
    for prov in res.get("providers", []):
        models = [(m.get("id"), m.get("aliases"), m.get("default")) for m in prov.get("models", [])]
        print(f"catalog {prov.get('id')}: {models}")
    return res


def runners():
    catalog()
    base = f"/projects/{P}/runners"
    made = {}
    for name, cli, model in [
        ("r-sonnet", "claude", "sonnet"),
        ("r-haiku", "claude", "haiku"),
        ("r-haiku-id", "claude", "claude-haiku-4-5-20251001"),
        ("r-none", "claude", None),
        ("r-cop", "copilot", "claude-haiku-4.5"),
        ("r-cop-alias", "copilot", "haiku"),
        ("r-codex", "codex", None),
        ("r-bad", "claude", "gpt-9"),
        ("r-bad-cli", "bogus", None),
        ("r-case", "claude", "Haiku"),
        ("r-space", "claude", " haiku"),
        ("", "claude", "haiku"),
        ("x" * 200, "claude", "haiku"),
    ]:
        body = {"name": name, "cli": cli}
        if model is not None:
            body["model"] = model
        status, res = req("POST", base, body)
        print(f"POST runner {name[:20]!r} {cli} {model!r} -> {status} "
              f"{res.get('model', '') if status < 300 else str(res)[:400]!s}")
        if status < 300:
            made[name] = res["id"]
    status, res = req("GET", base)
    print("labels:", [(r["name"][:20], r["cli"], r["model"]) for r in res])
    status, res = req("GET", f"{base}/launchability")
    print("launchability:", str(res)[:1200])
    rid = made["r-haiku"]
    for model in ("opus", "gpt-9", None):
        status, res = req("PATCH", f"{base}/{rid}", {"model": model})
        print(f"PATCH r-haiku model={model!r} -> {status} {res.get('model', '') if status < 300 else str(res)[:300]!s}")
    req("PATCH", f"{base}/{rid}", {"model": "haiku"})
    # The Add-agent door: provider + model, alias and undeclared.
    for name, model in [("a-alias", "haiku"), ("a-id", "claude-haiku-4-5-20251001"), ("a-bad", "gpt-9")]:
        status, res = req("POST", f"/projects/{P}/agents", {"name": name, "provider": "claude", "model": model})
        print(f"Add-agent {name} model={model!r} -> {status} {res if status >= 300 else res.get('runner_id')}")
    status, res = req("GET", base)
    print("runners after Add-agent:", [(r["name"][:24], r["model"]) for r in res])
    # The per-run door: overrides on a trigger (a refusal is all that is wanted here; no turn runs
    # for a bad model, and the alias case is checked against the stored conversation, not a run).
    for model in ("gpt-9", "Haiku"):
        status, res = req("POST", f"/projects/{P}/agent/trigger",
                          {"agent": "a-alias", "message": "reply ok", "overrides": {"model": model}})
        print(f"trigger overrides model={model!r} -> {status} {str(res)[:400]}")
    # The manager-job door and the checkpoint setting.
    for model in ("haiku", "gpt-9"):
        status, res = req("PATCH", f"/projects/{P}/manager/jobs/conversation-titles",
                          {"runner_id": rid, "model": model, "enabled": False})
        print(f"manager titles model={model!r} -> {status} {str(res)[:300]}")
    for model in ("haiku", "gpt-9"):
        status, res = req("PUT", f"/projects/{P}/settings", {"checkpoint_runner_id": rid, "checkpoint_model": model})
        print(f"settings checkpoint model={model!r} -> {status} {str(res)[:300] if status >= 300 else (res.get('checkpoint_runner_id'), res.get('checkpoint_model'))}")
    return made


def runner_named(name):
    return next(r for r in req("GET", f"/projects/{P}/runners")[1] if r["name"] == name)


def holders():
    base = f"/projects/{P}/runners"
    rid = runner_named("r-haiku")["id"]
    print("r-haiku is", rid)
    status, res = req("DELETE", f"{base}/{rid}")
    print("DELETE held runner ->", status, res)
    # Release the holders one at a time and read the sentence each time.
    status, res = req("PATCH", f"/projects/{P}/manager/jobs/conversation-titles", {"runner_id": None})
    print("titles runner -> None:", status, res.get("runner_id") if status < 300 else res)
    print("DELETE ->", *req("DELETE", f"{base}/{rid}"))
    status, res = req("PUT", f"/projects/{P}/settings", {"checkpoint_runner_id": None})
    print("checkpoint runner -> None:", status, res.get("checkpoint_runner_id") if status < 300 else res)
    print("DELETE ->", *req("DELETE", f"{base}/{rid}"))
    status, res = req("POST", f"/projects/{P}/agents/a-alias/archive")
    if status == 404 or status == 405:
        status, res = req("PATCH", f"/projects/{P}/agents/a-alias", {"lifecycle": "archived"})
    print("archive a-alias:", status, str(res)[:300])
    print("DELETE (only an archived agent holds it) ->", *req("DELETE", f"{base}/{rid}"))
    print("archived agent now:", [a for a in req("GET", f"/projects/{P}/agents")[1] if a.get("name") == "a-alias"][:1])
    print("GET deleted runner ->", *req("GET", f"{base}/{rid}"))
    print("DELETE again ->", *req("DELETE", f"{base}/{rid}"))
    print("DELETE a default runner ->", *req("DELETE", f"{base}/{runner_named('Codex (default)')['id']}"))


if __name__ == "__main__":
    phase = sys.argv[1]
    if phase == "fs":
        fs()
    elif phase == "fs-block":
        fs_block(*sys.argv[2:])
    elif phase == "runners":
        runners()
    elif phase == "holders":
        holders()
    elif phase == "open-block":
        open_block(*sys.argv[2:])
    else:
        raise SystemExit(f"unknown phase {phase}")
