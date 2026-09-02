"""Which Hub routes does anything actually call? Static measurement for `DECISIONS.md` R-1.

R-1's evidence block asserted, for two days and without ever writing the list down, that
*"`GET /documents/{path}/rigor-history` … returns zero hits across `hub/ui/src`. Ten more
operator-only routes are 0-hit in both the source and the served bundle."* This enumerates them.
It changes no product code and reads no database — it is a grep with the ambiguities resolved.

    py -3.11 scripts/drive/n10_route_reachability.py

Method, and why each step is needed:

1. **Routes come from the app, not from the decorators.** `hub.main:app` is imported and its
   route table read, so a prefix composed at include time (`project_resources_router`) cannot be
   mis-transcribed. Method matters: a path whose GET is called and whose DELETE is not is a
   half-reached path, and a path-only sweep reports it as reached.

2. **UI call sites come from the URL literals.** `client.ts` helpers take a whole path beginning
   `/api/v1`, so every request the UI makes appears as a literal somewhere in `hub/ui/src`. Each
   is normalised: `${…}` becomes `*` when it is a whole segment and `~` when it is glued to one
   (a query string, or `agents${lifecycle ? … : ''}`). The distinction is load-bearing — treating
   a query-string suffix as a wildcard segment made `/projects/{id}/events` look reached by the
   roster fetch.

3. **A wildcard segment proves nothing on its own.** ``/projects/${action}`` matches
   `/projects/create`, `/projects/open` *and* `/projects/{project_id}`; only one of those readings
   can be right. Those are reported separately as `wildcard` and resolved by hand — see
   `HAND_RESOLVED` below, every entry of which names the line it was read off.

4. **The CLI is a second client.** `HttpTransport._request` takes a path *relative* to one of
   three prefixes (`transport/http.py:145-149`), so its calls never contain the string `/api/v1`
   and a naive sweep of the repo misses all of them. A route the CLI calls is not an operator
   gap; it is an operator route only if the operator's screen is the plausible client.

5. **The bundle is probed by string literal, never by symbol name.** Minification renames every
   local, so an absent hook name is not evidence; template literals survive intact
   (``/api/v1/projects/${n}/loops/${e}`` is in the shipped file verbatim). Controls that
   must be present are probed alongside the fragments expected to be absent, so a silent
   false-negative in the probe shows up as a failed control rather than as a finding.

The second question R-1 needs, and the reason step 5 exists: *no client calls it* and *a client
calls it but nothing renders the result* are different defects. The latter is F260's shape, and
Vite tree-shakes it, so the route's client code is absent from the shipped app while still passing
its unit tests.

**Known blind spot — the unrendered-hook pass is depth-1** and every number it produces is a floor.
It asks whether any *file* outside a hook's own names it, so a hook imported by a component that is
itself imported by nothing counts as consumed. F260 is exactly that: `useMessages` is imported, by
`MessagesFeed`, which nothing imports and which is not in the bundle. Finding a whole unreachable
subtree needs a reachability walk from `App.tsx`, which this does not attempt.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
UI_SRC = REPO / "hub" / "ui" / "src"
BUNDLE_DIR = REPO / "hub" / "hub" / "static" / "ui" / "assets"

# Wildcard matches resolved by reading the line, not by guessing. `True` = the computed segment
# really is this route; `False` = it cannot be, so the route has no UI caller.
HAND_RESOLVED = {
    # projects.ts:48-51 -- useProjectPathMutation(action: 'open' | 'create')
    ("POST", "/api/v1/projects/create"): True,
    ("POST", "/api/v1/projects/open"): True,
    # agents.ts:193 -- `${archived ? 'archive' : 'unarchive'}`, so exactly these two and no more
    ("POST", "/api/v1/projects/{project_id}/agents/{name}/archive"): True,
    ("POST", "/api/v1/projects/{project_id}/agents/{name}/unarchive"): True,
    ("POST", "/api/v1/projects/{project_id}/agents/{name}/context-usage"): False,
    ("POST", "/api/v1/projects/{project_id}/agents/{name}/heartbeat"): False,
    (
        "POST",
        "/api/v1/projects/{project_id}/agents/{name}/output",
    ): False,  # GET only, agents.ts:420
    # queue.ts:40 is `/queue/${agent}`; workspace.ts:84 is `/worktrees/${agent}`
    ("GET", "/api/v1/projects/{project_id}/queue/settings"): False,
    ("GET", "/api/v1/projects/{project_id}/worktrees/conflicts"): False,
}

# Composed by a helper rather than written at the call site, so step 2 cannot see them:
# agentChat.ts:213 `conversationPath()`, used at :235, :262 and :268.
HELPER_CALLED = {
    ("POST", "/api/v1/projects/{project_id}/agent/{agent}/conversations/{conversation_id}/archive"),
    (
        "POST",
        "/api/v1/projects/{project_id}/agent/{agent}/conversations/{conversation_id}/unarchive",
    ),
}

HELPER_VERB = {
    "getJson": "GET",
    "postJson": "POST",
    "patchJson": "PATCH",
    "putJson": "PUT",
    "deleteJson": "DELETE",
}
HELPER_RX = re.compile(
    r"\b(getJson|postJson|patchJson|putJson|deleteJson|fetchWithAuth|EventSource|fetch)\b"
)
METHOD_RX = re.compile(r"method:\s*'(\w+)'")


def declared_routes():
    """Every (method, path) the running app would serve under /api/v1."""
    code = (
        "from hub.main import app\n"
        "import json\n"
        "rs=[]\n"
        "for r in app.routes:\n"
        "    p=getattr(r,'path',None); ms=getattr(r,'methods',None)\n"
        "    if p and p.startswith('/api/v1'):\n"
        "        for m in sorted(ms or []):\n"
        "            if m in ('HEAD','OPTIONS'): continue\n"
        "            rs.append([m,p])\n"
        "print(json.dumps(sorted(set(map(tuple,rs)))))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO / "hub", capture_output=True, text=True
    )
    if out.returncode != 0:
        raise SystemExit(f"could not import the Hub app:\n{out.stderr}")
    return [tuple(r) for r in json.loads(out.stdout.strip().splitlines()[-1])]


def ui_sources():
    return {
        p.as_posix(): p.read_text(encoding="utf-8", errors="replace")
        for p in UI_SRC.rglob("*")
        if p.suffix in (".ts", ".tsx") and p.is_file() and "/__tests__/" not in p.as_posix()
    }


def literal_at(text, start):
    """The whole URL literal beginning at `start`, `${…}` interpolations included."""
    end = start
    while end < len(text) and text[end] not in "`'\"" and text[end] != "\n":
        if text.startswith("${", end):
            depth, j = 1, end + 2
            while j < len(text) and depth:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                j += 1
            end = j
        else:
            end += 1
    return text[start:end]


def normalise(url):
    out, i = [], 0
    while i < len(url):
        if url.startswith("${", i):
            depth, j = 1, i + 2
            while j < len(url) and depth:
                if url[j] == "{":
                    depth += 1
                elif url[j] == "}":
                    depth -= 1
                j += 1
            out.append("*" if (out and out[-1] == "/") else "~")
            i = j
        else:
            out.append(url[i])
            i += 1
    return "".join(out).split("?")[0].rstrip("/")


def ui_calls(src):
    """(verb, normalised path) -> {file:line}."""
    calls = {}
    for name, text in src.items():
        for m in re.finditer(r"/api/v1", text):
            url = normalise(literal_at(text, m.start()))
            if not url.startswith("/api/v1"):
                continue
            window = text[max(0, m.start() - 400) : m.start()]
            found = HELPER_RX.findall(window)
            verb = "?"
            if found:
                last = found[-1]
                if last in HELPER_VERB:
                    verb = HELPER_VERB[last]
                elif last == "EventSource":
                    verb = "GET"
                else:
                    mm = METHOD_RX.search(text[m.start() : m.start() + 400])
                    verb = mm.group(1).upper() if mm else "GET"
            line = text.count("\n", 0, m.start()) + 1
            calls.setdefault((verb, url), set()).add(f"{name}:{line}")
    return calls


def segments(path):
    return [s for s in path.split("/") if s]


def segment_match(route_seg, url_seg):
    if route_seg.startswith("{"):
        return "exact"
    if url_seg == route_seg:
        return "exact"
    if url_seg == "*":
        return "wildcard"
    if "~" in url_seg:
        return "exact" if url_seg.split("~")[0] == route_seg else None
    return None


def match(route, url):
    r, u = segments(route), segments(url)
    if "{path:path}" in r:
        i = r.index("{path:path}")
        head, tail = r[:i], r[i + 1 :]
        if len(u) < len(head) + len(tail) + 1:
            return None
        pairs = list(zip(head, u[: len(head)], strict=True)) + list(
            zip(tail, u[len(u) - len(tail) :], strict=True)
        )
    elif len(r) != len(u):
        return None
    else:
        pairs = list(zip(r, u, strict=True))
    wild = False
    for rs, us in pairs:
        verdict = segment_match(rs, us)
        if verdict is None:
            return None
        wild = wild or verdict == "wildcard"
    return "wildcard" if wild else "exact"


def cli_calls():
    """HttpTransport writes paths relative to one of three prefixes, so reconstruct all three."""
    text = (REPO / "src" / "agentweave" / "transport" / "http.py").read_text(
        encoding="utf-8", errors="replace"
    )
    out = set()
    for m in re.finditer(r'_request\(\s*"(\w+)",\s*f?"([^"]*)"', text, re.S):
        rel = re.sub(r"\{[^}]*\}", "{}", m.group(2).split("?")[0])
        for prefix in ("/api/v1/projects/{}", "/api/v1", "/api/v1/agent-actions"):
            out.add((m.group(1), prefix + rel))
    return out


def orphan_hooks(src):
    """Exported api/ symbols nothing outside their own file (and outside tests) names."""
    export = re.compile(r"^export\s+(?:async\s+)?function\s+(\w+)", re.M)
    all_src = {
        p.as_posix(): p.read_text(encoding="utf-8", errors="replace")
        for p in UI_SRC.rglob("*")
        if p.suffix in (".ts", ".tsx") and p.is_file()
    }
    found = []
    for path in sorted((UI_SRC / "api").glob("*.ts")):
        name = path.as_posix()
        for m in export.finditer(src.get(name, "")):
            symbol = m.group(1)
            consumers = [
                other
                for other, text in all_src.items()
                if other != name
                and "/__tests__/" not in other
                and re.search(rf"\b{re.escape(symbol)}\b", text)
            ]
            if not consumers:
                tests = sum(
                    1
                    for other, text in all_src.items()
                    if "/__tests__/" in other and re.search(rf"\b{re.escape(symbol)}\b", text)
                )
                found.append((name, symbol, tests))
    return found


def main():
    routes = declared_routes()
    src = ui_sources()
    calls = ui_calls(src)
    cli = cli_calls()
    bundle_file = sorted(BUNDLE_DIR.glob("index-*.js"))[0]
    bundle = bundle_file.read_text(encoding="utf-8", errors="replace")

    rows = []
    for method, path in routes:
        verdict, where = None, []
        for (verb, url), locs in calls.items():
            if verb != "?" and verb != method:
                continue
            m = match(path, url)
            if m == "exact":
                verdict, where = "exact", sorted(locs)
                break
            if m == "wildcard" and verdict is None:
                verdict, where = "wildcard", sorted(locs)
        if (method, path) in HELPER_CALLED:
            verdict, where = "exact", ["hub/ui/src/api/agentChat.ts:213 (conversationPath)"]
        elif (method, path) in HAND_RESOLVED:
            verdict = "exact" if HAND_RESOLVED[(method, path)] else "none"
        rows.append(
            {
                "method": method,
                "path": path,
                "ui": verdict or "none",
                "where": where[:2],
                "cli": (method, re.sub(r"\{[^}]*\}", "{}", path)) in cli,
            }
        )

    unresolved = [r for r in rows if r["ui"] == "wildcard"]
    if unresolved:
        print("UNRESOLVED wildcard matches — add each to HAND_RESOLVED after reading the line:")
        for r in unresolved:
            print(f"    {r['method']:6} {r['path']}  {r['where']}")
        print()

    operator = [r for r in rows if not r["path"].startswith("/api/v1/agent-actions")]
    reached = [r for r in operator if r["ui"] == "exact"]
    unreached = [r for r in operator if r["ui"] != "exact"]
    by_cli = [r for r in unreached if r["cli"]]
    orphans = [r for r in unreached if not r["cli"]]

    print(f"declared /api/v1 route+method pairs        {len(rows)}")
    print(f"  under /api/v1/agent-actions (agent API)  {len(rows) - len(operator)}")
    print(f"  everything else                          {len(operator)}")
    print(f"    reached from hub/ui/src, verb matched  {len(reached)}")
    print(f"    not reached from the UI                {len(unreached)}")
    print(f"      called by the CLI transport instead  {len(by_cli)}")
    print(f"      no client anywhere in the repo       {len(orphans)}")
    print(f"      distinct paths in that group         {len({r['path'] for r in orphans})}")

    print("\n--- called by the CLI, not by the UI ---")
    for r in sorted(by_cli, key=lambda r: (r["path"], r["method"])):
        print(f"  {r['method']:6} {r['path']}")

    print("\n--- no client anywhere ---")
    for r in sorted(orphans, key=lambda r: (r["path"], r["method"])):
        print(f"  {r['method']:6} {r['path']}")

    print("\n--- a client exists, nothing renders it (exported, no non-test consumer) ---")
    for name, symbol, tests in orphan_hooks(src):
        rel = Path(name).resolve().relative_to(REPO).as_posix()
        print(f"  {rel}: {symbol}  (tests naming it: {tests})")

    print(f"\n--- served bundle: {bundle_file.relative_to(REPO).as_posix()} ---")
    controls = ["/api/v1/projects", "/tasks/board", "/proposals", "/rigor", "/loops/"]
    probes = [
        "/rigor-history",
        "/spec/drift",
        "/spec/evidence",
        "/evidence-retention",
        "/spec/requirements",
        "/spec/reindex",
        "/documents/adopt",
        "/documents/arrange",
        "/agents/agent-context",
        "/agents/configured",
        "/agents/context",
        "/agents/register",
        "/agents/request",
        "/agents/launchability",
        # with the terminating backtick: `runners/launchability` is a PREFIX of
        # `runners/launchability-by-provider`, which is the variant that ships
        "/runners/launchability`",
        "/divergences/recent",
        "/compact`",
        "/new-session`",
        "/context-usage",
        "/heartbeat",
        "/queue/settings",
        "/worktrees/conflicts",
        "/dependencies",
        "/events/ticket",
    ]
    bad = [c for c in controls if bundle.count(c) == 0]
    print(
        f"  controls present: {len(controls) - len(bad)}/{len(controls)}"
        + (f"  MISSING {bad}" if bad else "")
    )
    for f in probes:
        print(f"  {f:26} {bundle.count(f)}")


if __name__ == "__main__":
    main()
