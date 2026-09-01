"""Sweep row 2 — Runners.

The representative path from the e2e-loop coverage matrix: create a runner per CLI, probe
launchability, read the model catalog. Then provoke every refusal the three surfaces can
produce and judge whether each says what would work instead.

Surfaces: runners, launchability, model_catalog.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 scripts/drive/t_sweep_row2_runners.py <project-id>

Reads an existing project (created by the caller) and leaves behind only what it created; the
caller cleans up the project itself. Prints a PASS/FAIL table and exits non-zero on any FAIL.

The failures this harness holds open on purpose are the open findings — see FINDINGS.md's
"row 2 of 19" section. A green run here means those findings were fixed.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api, show  # noqa: E402

PID = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AW_PROJECT", "")
if not PID:
    sys.exit("usage: t_sweep_row2_runners.py <project-id>")

#: Any *other* project on the same Hub, to prove a runner is not readable across the boundary.
#: Read-only: this harness only issues GET/PATCH/DELETE against ids it created, and the one call
#: it makes under this scope is expected to 404.
OTHER = os.environ.get("AW_OTHER_PROJECT", "")

results = []
created = []


def check(label, ok, detail=""):
    results.append((label, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def detail_of(body):
    """The Hub answers a 400/404/409 with {"detail": "..."} and a 422 with a list of errors."""
    if isinstance(body, dict):
        d = body.get("detail")
        if isinstance(d, list):
            return " | ".join(str(e.get("msg", e)) for e in d)
        if d is not None:
            return str(d)
    return str(body)


print("=" * 78)
print("ROW 2 — RUNNERS.  project:", PID)
print("=" * 78)

# ------------------------------------------------------------------ 1. the catalog
code, cat = api("GET", "/model-catalog")
show("GET /model-catalog", code, cat, limit=400)
check("the catalog is readable with operator auth alone", code == 200, f"got {code}")
providers = {p["provider"]: p for p in cat.get("providers", [])} if code == 200 else {}
check(
    "the catalog declares exactly the two spawnable providers",
    set(providers) == {"claude", "codex"},
    str(sorted(providers)),
)
for name, prov in providers.items():
    defaults = [m for m in prov["models"] if m["default"]]
    check(f"{name} declares exactly one default model", len(defaults) == 1, str(len(defaults)))
    check(
        f"{name} declares a context window for every model",
        all(m["context_window"] for m in prov["models"]),
        str([m["id"] for m in prov["models"] if not m["context_window"]]),
    )
    control_ids = {c["id"] for c in prov["controls"]}
    check(
        f"{name} declares the effort and permission controls",
        {"effort", "permission_mode"} <= control_ids,
        str(sorted(control_ids)),
    )
    for control in prov["controls"]:
        permitted = {v["id"] for v in control["values"]}
        check(
            f"{name}.{control['id']} default is one of its own values",
            control["default"] in permitted,
            f"default={control['default']!r} of {sorted(permitted)}",
        )
        check(
            f"{name}.{control['id']} declares a renderable apply style",
            control["apply"]["style"] in ("flag", "config", "none"),
            control["apply"]["style"],
        )

# The Codex half of the catalog is a hand-copied snapshot of the CLI's own server-synced
# `models_cache.json` (model_catalog.py's docstring names that file as its source). Nothing
# re-checks it, so this does — the drift is F174.
cache_path = os.path.expanduser("~/.codex/models_cache.json")
if os.path.exists(cache_path) and "codex" in providers:
    with open(cache_path, encoding="utf-8") as fh:
        cache = json.load(fh)
    listed = {m["slug"] for m in cache["models"] if m.get("visibility") == "list"}
    declared = {m["id"] for m in providers["codex"]["models"]}
    print(
        f"    codex cache fetched_at={cache.get('fetched_at')} client={cache.get('client_version')}"
    )
    print(f"    cache lists: {sorted(listed)}")
    print(f"    catalog declares: {sorted(declared)}")
    check(
        "every codex model the catalog offers is one the installed CLI lists (F174)",
        declared <= listed,
        f"offered but not listed: {sorted(declared - listed)}",
    )
    default_codex = next(m["id"] for m in providers["codex"]["models"] if m["default"])
    check(
        "the codex default model is one the installed CLI lists (F174)",
        default_codex in listed,
        f"default={default_codex!r}",
    )
else:
    print("    (no ~/.codex/models_cache.json — drift check skipped)")

# ------------------------------------------------------------------ 2. what a fresh project seeds
code, seeded = api("GET", f"/projects/{PID}/runners")
show("GET /runners (seeded)", code, seeded, limit=800)
check("listing runners returns 200", code == 200, f"got {code}")
seeded_clis = [r["cli"] for r in seeded] if code == 200 else []
check(
    "a fresh project seeds one runner per supported CLI",
    sorted(seeded_clis) == ["claude", "codex"],
    str(seeded_clis),
)
check(
    "the seeded runners state no model, so the CLI's own default runs",
    all(r["model"] is None for r in seeded),
    str([(r["name"], r["model"]) for r in seeded]),
)

# ------------------------------------------------------------------ 3. create one per CLI
code, claude_runner = api(
    "POST",
    f"/projects/{PID}/runners",
    {"name": "Haiku drive", "cli": "claude", "model": "claude-haiku-4-5-20251001"},
)
check(
    "create a claude runner on a declared model", code == 201, f"{code}: {detail_of(claude_runner)}"
)
if code == 201:
    created.append(claude_runner["id"])
    check(
        "a declared model is not flagged unrecognised",
        claude_runner["model_unrecognised"] is False,
        str(claude_runner["model_unrecognised"]),
    )

code, codex_runner = api(
    "POST",
    f"/projects/{PID}/runners",
    {"name": "Codex exec", "cli": "codex", "model": "gpt-5.5", "flags": ["--no-app-server"]},
)
check("create a codex runner with flags", code == 201, f"{code}: {detail_of(codex_runner)}")
if code == 201:
    created.append(codex_runner["id"])
    check(
        "flags round-trip verbatim",
        codex_runner["flags"] == ["--no-app-server"],
        str(codex_runner["flags"]),
    )

code, fetched = api("GET", f"/projects/{PID}/runners/{claude_runner['id']}")
check(
    "GET /runners/{id} returns the runner",
    code == 200 and fetched["id"] == claude_runner["id"],
    f"{code}",
)

code, listed_now = api("GET", f"/projects/{PID}/runners")
# Flaky by construction, and that IS the finding: the router orders by `created_at` alone, two
# creations land in the same ~15.6ms Windows clock tick about half the time, and on a tie SQLite
# feeds the sorter from `ix_runners_project_name` — so the list silently falls back to
# alphabetical. "Codex exec" sorts before "Haiku drive"; run this enough times and it flips. F177.
check(
    "the list is ordered by creation, not by name, even on a created_at tie (F177)",
    [r["id"] for r in listed_now][-2:] == created,
    f"{[r['name'] for r in listed_now]} "
    f"(created_at tie: {claude_runner['created_at'] == codex_runner['created_at']})",
)

# ------------------------------------------------------------------ 4. edit
code, patched = api(
    "PATCH",
    f"/projects/{PID}/runners/{claude_runner['id']}",
    {"name": "Haiku drive (renamed)", "model": "claude-sonnet-5"},
)
check(
    "PATCH renames and re-models",
    code == 200
    and patched["name"] == "Haiku drive (renamed)"
    and patched["model"] == "claude-sonnet-5",
    f"{code}: {detail_of(patched)}",
)
code, patched2 = api(
    "PATCH",
    f"/projects/{PID}/runners/{claude_runner['id']}",
    {"model": "claude-haiku-4-5-20251001"},
)
check(
    "PATCH puts the drive model back",
    code == 200 and patched2["model"] == "claude-haiku-4-5-20251001",
    f"{code}",
)

# ------------------------------------------------------------------ 5. refusals, and their legibility
code, body = api("POST", f"/projects/{PID}/runners", {"name": "kimi", "cli": "kimi"})
msg = detail_of(body)
check("an unsupported CLI is refused", code == 422, f"{code}: {msg}")
check("...and the refusal names the CLIs that would work", "claude" in msg and "codex" in msg, msg)

code, body = api(
    "POST", f"/projects/{PID}/runners", {"name": "x", "cli": "claude", "model": "claude-opus-9"}
)
msg = detail_of(body)
check("an undeclared model is refused", code == 400, f"{code}: {msg}")
check(
    "...and the refusal names a model that would work (F175)",
    any(m["id"] in msg or m["label"] in msg for m in providers["claude"]["models"]),
    msg,
)

code, body = api(
    "POST", f"/projects/{PID}/runners", {"name": "x", "cli": "claude", "model": "gpt-5.5"}
)
check(
    "one provider's model is refused on the other's CLI", code == 400, f"{code}: {detail_of(body)}"
)

# The catalog publishes `aliases` per model over /model-catalog, and the UI's own type carries
# the field — but no input path accepts one. F175.
alias = next(m["aliases"][0] for m in providers["claude"]["models"] if m["aliases"])
code, body = api(
    "POST", f"/projects/{PID}/runners", {"name": "alias", "cli": "claude", "model": alias}
)
msg = detail_of(body)
if code == 201:
    created.append(body["id"])
check(
    f"an alias the catalog itself publishes ({alias!r}) is either accepted or refused truthfully (F175)",
    code == 201 or "alias" in msg.lower(),
    f"{code}: {msg}",
)

code, body = api("POST", f"/projects/{PID}/runners", {"name": "no-cli"})
check("a runner with no CLI is refused", code == 422, f"{code}: {detail_of(body)}")

code, body = api(
    "POST", f"/projects/{PID}/runners", {"name": "extra", "cli": "claude", "colour": "red"}
)
check(
    "an unknown field is named rather than absorbed",
    code == 422 and "colour" in json.dumps(body),
    f"{code}: {detail_of(body)}",
)

code, body = api("PATCH", f"/projects/{PID}/runners/{claude_runner['id']}", {"cli": "codex"})
check("a runner's CLI cannot be changed after creation", code == 422, f"{code}: {detail_of(body)}")
# Not asserted, recorded: the refusal is `RequestModel`'s generic "Extra inputs are not
# permitted" with `cli` in `loc`, so the field IS named — but the reason given is "unknown
# field" where the truth is "known field, deliberately fixed after creation". Noted at
# severity D in FINDINGS.md rather than held open here.
print(f"    (PATCH cli -> {code}: {detail_of(body)})")

code, body = api("PATCH", f"/projects/{PID}/runners/{claude_runner['id']}", {"model": "nope-1"})
check("PATCH refuses an undeclared model too", code == 400, f"{code}: {detail_of(body)}")
code, unchanged = api("GET", f"/projects/{PID}/runners/{claude_runner['id']}")
check(
    "a refused PATCH leaves the stored model untouched",
    unchanged["model"] == "claude-haiku-4-5-20251001",
    str(unchanged["model"]),
)

code, body = api("GET", f"/projects/{PID}/runners/runner-does-not-exist")
check("an unknown runner id is a 404", code == 404, f"{code}: {detail_of(body)}")
code, body = api("DELETE", f"/projects/{PID}/runners/runner-does-not-exist")
check("deleting an unknown runner is a 404", code == 404, f"{code}: {detail_of(body)}")

code, body = api("POST", f"/projects/{PID}/runners", {"name": "", "cli": "claude"})
if code == 201:
    created.append(body["id"])
check(
    "a runner cannot be created nameless (the dialog refuses it; the API should too) (F176)",
    code != 201,
    f"{code}: created runner named {body.get('name')!r}" if code == 201 else str(code),
)

if OTHER:
    code, body = api("GET", f"/projects/{OTHER}/runners/{claude_runner['id']}")
    check(
        "a runner is not readable from another project's scope",
        code == 404,
        f"{code}: {detail_of(body)}",
    )

# ------------------------------------------------------------------ 6. launchability
code, launch = api("GET", f"/projects/{PID}/runners/launchability")
show("GET /runners/launchability", code, launch, limit=900)
check("launchability answers 200", code == 200, f"{code}")
verdicts = launch.get("runners", {}) if code == 200 else {}
check(
    "every runner in the project gets a verdict",
    set(verdicts) == {r["id"] for r in listed_now} | set(created) - {None},
    f"{len(verdicts)} verdicts for {len(listed_now)} runners at list time",
)
for rid, verdict in verdicts.items():
    check(
        f"{rid} states a reason whenever it is not runnable",
        verdict["runnable"] or bool(verdict["reason"]),
        json.dumps(verdict),
    )
    check(
        f"{rid} reports runnable only when present and authorized",
        verdict["runnable"] == (verdict["present"] and verdict["authorized"]),
        json.dumps(verdict),
    )

code, byprov = api("GET", f"/projects/{PID}/runners/launchability-by-provider")
show("GET /runners/launchability-by-provider", code, byprov, limit=600)
check(
    "provider launchability covers every catalog provider",
    code == 200 and set(byprov["providers"]) == set(providers),
    f"{code}: {sorted(byprov.get('providers', {}))}",
)
check(
    "the claude CLI is present on this machine, so the drive below is meaningful",
    byprov["providers"]["claude"]["runnable"] is True,
    json.dumps(byprov["providers"]["claude"]),
)

# `launchability` is a literal path segment declared before `/{runner_id}` — prove the router
# still resolves it as the collection endpoint rather than as a runner lookup.
check(
    "the launchability route is not shadowed by the runner-id route",
    isinstance(launch, dict) and "runners" in launch,
    str(type(launch)),
)

# ------------------------------------------------------------------ 7. deleting a bound runner
code, agent = api(
    "POST",
    f"/projects/{PID}/agents",
    {"name": "row2-probe", "runner_id": claude_runner["id"]},
)
check("an agent can be created bound to a runner", code == 201, f"{code}: {detail_of(agent)}")

code, body = api("DELETE", f"/projects/{PID}/runners/{claude_runner['id']}")
msg = detail_of(body)
check("deleting a bound runner is refused", code == 409, f"{code}: {msg}")
check(
    "...and the refusal names the agent and the way forward",
    "row2-probe" in msg and "nbind" in msg,
    msg,
)

code, _ = api("DELETE", f"/projects/{PID}/agents/row2-probe")
if code not in (200, 204):
    # No operator delete for agents is a row-3 concern; archive is the offered path.
    code, _ = api("POST", f"/projects/{PID}/agents/row2-probe/archive")
    print(f"    (agent archived instead of deleted: {code})")
    code, _ = api("PATCH", f"/projects/{PID}/agents/row2-probe", {"runner_id": None})
    print(f"    (agent unbound: {code})")

code, body = api("DELETE", f"/projects/{PID}/runners/{claude_runner['id']}")
check("an unbound runner deletes", code == 204, f"{code}: {detail_of(body)}")
code, body = api("GET", f"/projects/{PID}/runners/{claude_runner['id']}")
check("...and is gone afterwards", code == 404, f"{code}")

# ------------------------------------------------------------------
print()
print("=" * 78)
failed = [r for r in results if not r[1]]
print(f"ROW 2 RESULT: {len(results) - len(failed)}/{len(results)} passed")
for label, _, det in failed:
    print(f"  FAIL  {label} — {det}")
print("=" * 78)
sys.exit(1 if failed else 0)
