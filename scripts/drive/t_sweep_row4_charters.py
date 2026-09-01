"""Sweep row 4 — Charters.

The representative path from the e2e-loop coverage matrix (`SURVEY.md:26`): charter CRUD and the
nine seeded starters. Routes are `hub/hub/api/v1/charters.py` — POST/GET/GET{id}/PATCH{id}/
DELETE{id} under `/projects/{pid}/charters` — plus the two read paths on the agents router that
serve charter content (`/agents/context?charter=` and `/agents/{name}/context`).

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 scripts/drive/t_sweep_row4_charters.py <pid> [other-pid]

Reads an existing project (created by the caller) and leaves behind only what it created; the
caller cleans up the project itself. Prints a PASS/FAIL table and exits non-zero on any FAIL.

Written to be run TWICE against the same project: row 1's F172 and row 2's F177 were both found
by a second run against state the first left. Names carry a run tag so a second run creates fresh
rows rather than colliding, and the duplicate-name probe deliberately reuses run 1's name when it
can see it — which is the only way to observe that the charter surface has no uniqueness rule at
all, rather than one that happens not to fire.

The failures this harness holds open on purpose are the open findings — see FINDINGS.md's
"row 4 of 19" section. A green run here means those findings were fixed.
"""

import json
import os
import pathlib
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api, show  # noqa: E402

PID = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AW_PROJECT", "")
if not PID:
    sys.exit("usage: t_sweep_row4_charters.py <project-id> [other-project-id]")

#: Any *other* project on the same Hub, to prove a charter id cannot be read across the boundary.
#: Read-only under that scope: this harness only lists its charters and then addresses THIS
#: project's charter ids under it, which must 404.
OTHER = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("AW_OTHER_PROJECT", "")

TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
HAIKU = "claude-haiku-4-5-20251001"

results = []


def check(label, ok, detail=""):
    results.append((label, bool(ok), detail))
    shown = detail if len(detail) <= 300 else detail[:300] + f"... ({len(detail)} chars)"
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {shown}" if shown else ""))


def detail_of(body):
    """The Hub answers a 400/404/409 with {"detail": ...} and a 422 with a list of errors."""
    if isinstance(body, dict):
        d = body.get("detail")
        if isinstance(d, list):
            return " | ".join(str(e.get("msg", e)) for e in d)
        if isinstance(d, dict):
            return str(d.get("message", d))
        if d is not None:
            return str(d)
    return str(body)


def names_what_would_work(text, *needles):
    """A refusal earns its keep only if it names a permitted value or a repair."""
    low = (text or "").lower()
    return any(n.lower() in low for n in needles)


A = f"/projects/{PID}"
B = f"/projects/{OTHER}" if OTHER else None
print("=" * 78)
print(f"ROW 4 — CHARTERS.  project: {PID}  other: {OTHER or '(none)'}  tag: {TAG}")
print("=" * 78)

created = []  # charter ids this run made, for teardown

# ------------------------------------------------------------------ 1. the seeded starters

code, seeded = api("GET", f"{A}/charters")
check("the project's charters are readable", code == 200, f"got {code}")
seeded = seeded if isinstance(seeded, list) else []

manifest_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "hub",
    "hub",
    "data",
    "charters",
    "charters.json",
)
manifest = json.loads(pathlib.Path(manifest_path).read_text(encoding="utf-8"))
want_names = {m["name"] for m in manifest["charters"].values()}

# Only the rows this run did not create. On a second run the list carries run 1's leftovers, so
# the seed assertions have to be made against the seeded subset rather than the whole list.
seed_rows = [c for c in seeded if c["name"] in want_names]
check(
    "a fresh project seeds exactly the manifest's starter charters",
    {c["name"] for c in seed_rows} == want_names,
    f"{len(seeded)} rows; missing {sorted(want_names - {c['name'] for c in seeded})}",
)
check(
    "the manifest declares nine starters and nine are present",
    len(want_names) == 9 and len({c["name"] for c in seed_rows}) == 9,
    f"manifest {len(want_names)}, seeded {len({c['name'] for c in seed_rows})} distinct "
    f"across {len(seed_rows)} rows",
)
check(
    "no seeded charter is empty — an empty one would contribute nothing to a turn",
    all((c.get("content") or "").strip() for c in seed_rows),
    ", ".join(c["name"] for c in seed_rows if not (c.get("content") or "").strip()),
)
# The content is supposed to come from the bundled markdown, not from a fixture or a default.
key0 = next(k for k, m in manifest["charters"].items() if m["name"] == sorted(want_names)[0])
disk0 = pathlib.Path(os.path.dirname(manifest_path), f"{key0}.md").read_text(encoding="utf-8")
# `min` by created_at, not `next`: a second run of this harness has already authored a row under
# this same name, and the seeded one is the older of the two — which is itself the defect.
row0 = min(
    (c for c in seed_rows if c["name"] == sorted(want_names)[0]), key=lambda c: c["created_at"]
)
check(
    "a seeded charter's content is the bundled markdown byte for byte",
    row0["content"] == disk0,
    f"{sorted(want_names)[0]}: {len(row0['content'])} vs {len(disk0)} chars",
)
check(
    "charters are listed in creation order",
    [c["id"] for c in seeded] == [c["id"] for c in sorted(seeded, key=lambda c: c["created_at"])],
    " -> ".join(c["name"] for c in seeded[:4]),
)

# Seeding SHALL run at most once per project (agent-charter:28-29). Re-opening the project is the
# cheapest way to re-enter the registration path.
code, proj = api("GET", f"{A}")
before_seed = len(seeded)
code, reopened = api(
    "POST",
    "/projects/open",
    {"path": proj.get("working_directory"), "name": proj.get("name")},
)
code, after = api("GET", f"{A}/charters")
check(
    "re-opening the project does not re-seed or duplicate the starters",
    code == 200 and len(after) == before_seed,
    f"{before_seed} -> {len(after) if code == 200 else code}",
)

# ------------------------------------------------------------------ 2. CRUD

code, made = api(
    "POST",
    f"{A}/charters",
    {"name": f"row4-authored-{TAG}", "content": "Line one.\n\nLine two."},
)
show("POST /charters", code, made, limit=400)
check("a charter is authorable", code == 201, f"got {code}: {detail_of(made)}")
CID = made.get("id") if code == 201 else None
if CID:
    created.append(CID)
check("the created charter carries a stable charter- id", str(CID).startswith("charter-"), str(CID))

code, got = api("GET", f"{A}/charters/{CID}")
check(
    "the charter reads back with the content it was authored with",
    code == 200 and got.get("content") == "Line one.\n\nLine two.",
    f"got {code}",
)
check(
    "the charter reports the project that owns it",
    code == 200 and got.get("project_id") == PID,
    str(got.get("project_id") if code == 200 else code),
)

code, patched = api("PATCH", f"{A}/charters/{CID}", {"name": f"row4-renamed-{TAG}"})
check(
    "a name-only edit changes the name and preserves the content",
    code == 200
    and patched.get("name") == f"row4-renamed-{TAG}"
    and patched.get("content") == "Line one.\n\nLine two.",
    f"got {code}: {detail_of(patched)}",
)
code, patched = api("PATCH", f"{A}/charters/{CID}", {"content": "Replaced."})
check(
    "a content-only edit changes the content and preserves the name",
    code == 200
    and patched.get("content") == "Replaced."
    and patched.get("name") == f"row4-renamed-{TAG}",
    f"got {code}: {detail_of(patched)}",
)
check(
    "an edit moves updated_at",
    code == 200 and patched.get("updated_at") != patched.get("created_at"),
    f"{patched.get('created_at')} -> {patched.get('updated_at')}" if code == 200 else str(code),
)
code, noop = api("PATCH", f"{A}/charters/{CID}", {})
check(
    "an empty edit is accepted as a no-op rather than blanking the record",
    code == 200
    and noop.get("name") == f"row4-renamed-{TAG}"
    and noop.get("content") == "Replaced.",
    f"got {code}: {detail_of(noop)}",
)

# ------------------------------------------------------------------ 3. the refusals

code, empty_name = api("POST", f"{A}/charters", {"name": "", "content": "x"})
check(
    "an empty name is refused",
    code == 422,
    f"got {code}: {detail_of(empty_name)}",
)
check(
    "the empty-name refusal names the constraint it broke",
    names_what_would_work(detail_of(empty_name), "at least 1", "min_length", "too_short"),
    detail_of(empty_name),
)
code, long_name = api("POST", f"{A}/charters", {"name": "n" * 257, "content": "x"})
check("a name past the column width is refused", code == 422, f"got {code}")
check(
    "the over-long-name refusal names the limit",
    names_what_would_work(detail_of(long_name), "256", "at most"),
    detail_of(long_name),
)
code, no_content = api("POST", f"{A}/charters", {"name": f"row4-nc-{TAG}"})
check("a charter with no content field at all is refused", code == 422, f"got {code}")

# An EMPTY content string is deliberately allowed — ChartersPage.tsx:171 renders a sentence for
# exactly that case. This asserts the permission and the sentence together.
code, blank = api("POST", f"{A}/charters", {"name": f"row4-blank-{TAG}", "content": ""})
check("a charter with empty content is allowed", code == 201, f"got {code}: {detail_of(blank)}")
if code == 201:
    created.append(blank["id"])

# The dialog disables Save on `name.trim()` being empty (`ChartersPage.tsx:262`), so a
# whitespace-only name is unreachable by hand — but the API is the product too, and an agent or a
# script reaches it. A row whose name renders as nothing is unpickable in the selector.
code, ws = api("POST", f"{A}/charters", {"name": "   ", "content": "x"})
if code == 201:
    created.append(ws["id"])
check(
    "a whitespace-only name is refused, as the dialog already refuses it",
    code != 201,
    f"got {code}: name={ws.get('name')!r}" if code == 201 else f"got {code}",
)

code, missing = api("GET", f"{A}/charters/charter-doesnotexist")
check("an unknown charter id reads 404", code == 404, f"got {code}")
check(
    "the not-found refusal says what was not found",
    names_what_would_work(detail_of(missing), "charter"),
    detail_of(missing),
)
code, missing_p = api("PATCH", f"{A}/charters/charter-doesnotexist", {"name": "x"})
check("editing an unknown charter is refused 404", code == 404, f"got {code}")
code, missing_d = api("DELETE", f"{A}/charters/charter-doesnotexist")
check("deleting an unknown charter is refused 404", code == 404, f"got {code}")

# ------------------------------------------------------------------ 4. duplicate names
#
# There is no uniqueness rule on `Charter.name` — not in the schema, not in the route, not in the
# table. The picker (`AgentSettingsControls.tsx:280-284`) renders `<option>{charter.name}</option>`
# and nothing else, so two charters with one name are indistinguishable at the only place the
# choice is made. The seeded set is the sharp case: an operator can author a second "Developer".
dup_target = sorted(want_names)[0]
code, dup = api("POST", f"{A}/charters", {"name": dup_target, "content": "Not the starter."})
if code == 201:
    created.append(dup["id"])
check(
    "a charter cannot be authored under the name of an existing one",
    code != 201,
    f"got {code} — a second '{dup_target}' now exists as {dup.get('id') if code == 201 else ''}",
)
code, dup_list = api("GET", f"{A}/charters")
same_named = [c for c in dup_list if c["name"] == dup_target] if code == 200 else []
check(
    "the charter list does not carry two rows under one name",
    len(same_named) <= 1,
    f"{len(same_named)} rows named '{dup_target}'",
)
# A rename can reach the same collision by a second door, so both are probed.
if CID:
    code, dup_rename = api("PATCH", f"{A}/charters/{CID}", {"name": dup_target})
    check(
        "a charter cannot be RENAMED onto the name of an existing one",
        code != 200,
        f"got {code}",
    )
    if code == 200:  # put it back so later assertions read the name they expect
        api("PATCH", f"{A}/charters/{CID}", {"name": f"row4-renamed-{TAG}"})

# ------------------------------------------------------------------ 5. cross-project isolation

if OTHER:
    code, leak = api("GET", f"{B}/charters/{CID}")
    check(
        "another project cannot READ this project's charter by id",
        code == 404,
        f"got {code}: {detail_of(leak)}",
    )
    check(
        "the cross-project refusal does not admit the charter exists",
        code == 404 and "not found" in detail_of(leak).lower(),
        detail_of(leak),
    )
    code, leak_p = api("PATCH", f"{B}/charters/{CID}", {"content": "hijacked"})
    check("another project cannot EDIT this project's charter", code == 404, f"got {code}")
    code, leak_d = api("DELETE", f"{B}/charters/{CID}")
    check("another project cannot DELETE this project's charter", code == 404, f"got {code}")
    code, still = api("GET", f"{A}/charters/{CID}")
    check(
        "the charter survived every cross-project attempt intact",
        code == 200 and still.get("content") == "Replaced.",
        f"got {code}",
    )
    code, ctx_leak = api("GET", f"{B}/agents/context?charter={CID}")
    check(
        "the charter-content read path is project-scoped too",
        code == 404,
        f"got {code}: {detail_of(ctx_leak)}",
    )

# ------------------------------------------------------------------ 6. bound charters

code, runner = api(
    "POST", f"{A}/runners", {"name": f"row4-claude-{TAG}", "cli": "claude", "model": HAIKU}
)
check("a runner is creatable for the binding probes", code == 201, f"got {code}")
RUNNER = runner.get("id") if code == 201 else None

n_bound = f"b{TAG}"
code, agent = api("POST", f"{A}/agents", {"name": n_bound, "runner_id": RUNNER, "charter_id": CID})
check("an agent binds the authored charter", code == 201, f"got {code}: {detail_of(agent)}")

code, refused = api("DELETE", f"{A}/charters/{CID}")
check("deleting a bound charter is refused", code == 409, f"got {code}")
check(
    "the refusal names the agent that holds it",
    n_bound in detail_of(refused),
    detail_of(refused),
)
check(
    "the refusal names the repair that would clear it",
    names_what_would_work(detail_of(refused), "unbind"),
    detail_of(refused),
)

# Unbinding is the repair the refusal names, so it has to actually work.
code, unbound = api("PATCH", f"{A}/agents/{n_bound}", {"charter_id": None})
check("the named repair is available — an agent can be unbound", code == 200, f"got {code}")
code, deleted_ok = api("DELETE", f"{A}/charters/{CID}")
check("after the named repair, the delete succeeds", code == 204, f"got {code}")
if code == 204 and CID in created:
    created.remove(CID)
code, gone = api("GET", f"{A}/charters/{CID}")
check("the deleted charter is gone", code == 404, f"got {code}")

# ------------------------------------------------------------------ 7. an ARCHIVED holder
#
# `charters.py:96-98` selects blocking agents with no lifecycle filter, while the roster the
# operator reads hides archived agents. So an archived agent can block a charter delete by a name
# the operator cannot see — and the refusal never says the holder is archived.
code, ch_arch = api(
    "POST", f"{A}/charters", {"name": f"row4-archived-holder-{TAG}", "content": "held"}
)
ARCH_CID = ch_arch.get("id") if code == 201 else None
if ARCH_CID:
    created.append(ARCH_CID)
n_arch = f"a{TAG}"
code, _ = api("POST", f"{A}/agents", {"name": n_arch, "runner_id": RUNNER, "charter_id": ARCH_CID})
check("an agent is created to be archived while holding a charter", code == 201, f"got {code}")
code, archived = api("POST", f"{A}/agents/{n_arch}/archive", {})
check("that agent archives", code in (200, 204), f"got {code}: {detail_of(archived)}")

code, roster = api("GET", f"{A}/agents")
roster_names = {a["name"] for a in roster} if isinstance(roster, list) else set()
check(
    "the archived agent is not on the roster the operator reads",
    n_arch not in roster_names,
    sorted(roster_names),
)
code, arch_refusal = api("DELETE", f"{A}/charters/{ARCH_CID}")
blocked_by_archived = code == 409
check(
    "a charter held only by an ARCHIVED agent is deletable, or the refusal says the holder is "
    "archived",
    code == 204 or names_what_would_work(detail_of(arch_refusal), "archiv"),
    f"got {code}: {detail_of(arch_refusal)}",
)
if code == 204 and ARCH_CID in created:
    created.remove(ARCH_CID)
if blocked_by_archived:
    # The refusal names a repair; check whether the repair is reachable for an archived agent at
    # all. If unbinding an archived agent is itself refused, the operator is in a corner.
    code, unarch_bind = api("PATCH", f"{A}/agents/{n_arch}", {"charter_id": None})
    check(
        "the repair the refusal names is reachable for an archived holder",
        code == 200,
        f"PATCH charter_id=None on an archived agent got {code}: {detail_of(unarch_bind)}",
    )

# ------------------------------------------------------------------ 8. the charter in context

code, ch_ctx = api("POST", f"{A}/charters", {"name": f"row4-ctx-{TAG}", "content": f"CTXMARK{TAG}"})
CTX_CID = ch_ctx.get("id") if code == 201 else None
if CTX_CID:
    created.append(CTX_CID)
n_ctx = f"c{TAG}"
code, _ = api("POST", f"{A}/agents", {"name": n_ctx, "runner_id": RUNNER, "charter_id": CTX_CID})
check("an agent binds the context-probe charter", code == 201, f"got {code}")

code, ctx = api("GET", f"{A}/agents/agent-context?agent={n_ctx}")
body = json.dumps(ctx)
check(
    "the canonical context carries the bound charter's content",
    code == 200 and f"CTXMARK{TAG}" in body,
    f"got {code}",
)
check(
    "the canonical context names the charter it resolved",
    code == 200 and ctx.get("charter_name") == f"row4-ctx-{TAG}",
    str(ctx.get("charter_name") if code == 200 else code),
)
api("PATCH", f"{A}/charters/{CTX_CID}", {"content": f"EDITED{TAG}"})
code, ctx2 = api("GET", f"{A}/agents/agent-context?agent={n_ctx}")
check(
    "an edit to the charter is visible in the canonical context immediately",
    code == 200 and f"EDITED{TAG}" in json.dumps(ctx2) and f"CTXMARK{TAG}" not in json.dumps(ctx2),
    f"got {code}",
)

# An agent with NO charter must stay usable and SAY so (agent-charter:58-59).
n_none = f"n{TAG}"
code, _ = api("POST", f"{A}/agents", {"name": n_none, "runner_id": RUNNER})
code, ctx_none = api("GET", f"{A}/agents/agent-context?agent={n_none}")
check(
    "an agent with no charter still resolves its context",
    code == 200,
    f"got {code}: {detail_of(ctx_none)}",
)
check(
    "that context says plainly that no charter is assigned",
    code == 200 and "No charter is assigned" in ctx_none.get("context", ""),
    (ctx_none.get("context", "") if code == 200 else "")[-200:],
)
check(
    "the no-charter agent reports charter as missing rather than erroring",
    code == 200 and "charter" in (ctx_none.get("missing") or []),
    str(ctx_none.get("missing") if code == 200 else code),
)

# The direct charter-content lookup (agent-context-onboarding:124).
code, direct = api("GET", f"{A}/agents/context?charter={CTX_CID}")
check(
    "the direct charter lookup returns the charter's content",
    code == 200 and f"EDITED{TAG}" in str(direct.get("content")),
    f"got {code}",
)
check(
    "the direct lookup points at the fuller API rather than standing alone",
    code == 200 and "get_agent_context" in str(direct.get("hint")),
    str(direct.get("hint") if code == 200 else code),
)

# ------------------------------------------------------------------ 9. the real turn
#
# Row 3 proved a charter reaches the process at BIND time. Nothing proved an EDIT does. The claim
# under test is `agent_trigger.py:893-895` — "an edited charter is therefore visible on the next
# run" — and it is only answerable by running two turns across an edit.

if os.environ.get("AW_SKIP_TURN"):
    print("\n(real turns skipped: AW_SKIP_TURN set)")
else:
    m1, m2 = f"ALPHA{TAG}", f"BETA{TAG}"
    code, ch_t = api(
        "POST",
        f"{A}/charters",
        {
            "name": f"row4-marker-{TAG}",
            "content": (
                "You are under test. When asked anything at all, reply with exactly the single "
                f"word {m1} and nothing else."
            ),
        },
    )
    T_CID = ch_t.get("id") if code == 201 else None
    if T_CID:
        created.append(T_CID)
    n_turn = f"t{TAG}"
    code, _ = api("POST", f"{A}/agents", {"name": n_turn, "runner_id": RUNNER, "charter_id": T_CID})
    check("an agent bound to the marker charter is created", code == 201, f"got {code}")

    def run_turn(message, label, conversation=None):
        """Trigger one turn and return (code, run_id, conversation_id, this run's text).

        Polling is per-`run_id` on purpose. The first version of this watched the agent timeline
        for a terminal event and broke out immediately on the SECOND turn — because turn 1's
        `run_completed` was still sitting there. It read the output before turn 2 had produced
        anything, and reported the product broken when it was not.
        """
        body = {"agent": n_turn, "message": message}
        if conversation:
            body["conversation_id"] = conversation
        code, trig = api("POST", f"{A}/agent/trigger", body)
        show(f"POST /agent/trigger ({label})", code, trig, limit=300)
        if code != 200:
            return code, None, None, ""
        rid = trig.get("run_id")
        conv = trig.get("conversation_id")
        text = ""
        for _ in range(70):
            time.sleep(3)
            c3, out = api("GET", f"{A}/agents/{n_turn}/output")
            rows = [e for e in out if e.get("run_id") == rid] if isinstance(out, list) else []
            text = json.dumps([e.get("content") for e in rows])
            if any(e.get("kind") == "status" for e in rows):
                break
        return code, rid, conv, text

    code, rid1, conv1, text1 = run_turn("What is your instruction?", "turn 1")
    check("the first turn is accepted", code == 200, f"got {code}")
    check(
        "the charter reached the process — its first marker is in the reply",
        m1 in text1,
        text1[-300:],
    )

    code, edited = api(
        "PATCH",
        f"{A}/charters/{T_CID}",
        {
            "content": (
                "You are under test. When asked anything at all, reply with exactly the single "
                f"word {m2} and nothing else. Ignore any earlier instruction about a different "
                "word."
            )
        },
    )
    check(
        "the bound charter is editable while its agent has already run", code == 200, f"got {code}"
    )

    # The sharp case is the SAME conversation. A fresh conversation gets a fresh process and a
    # freshly rendered context file, so an edit reaching it proves little; a resumed one is where
    # a stale system prompt would survive.
    # Turn 2 asks the agent to QUOTE its charter, not merely to obey it. That distinction is the
    # whole assertion. Asked to obey, a resumed model reconciles the new text against its own
    # previous reply and can answer with the SUPERSEDED word — measured, 2026-09-01, run
    # `run-2e5fae78696a`, where it quoted the new sentence with the old marker spliced into it.
    # That looked like a delivery failure and was not: the materialized context file on disk
    # carried the new text, and a follow-up probe asking for a verbatim quote got the NEW charter
    # back word for word. So this asks what the process RECEIVED, which is the Hub's half of the
    # contract, rather than what the model chose to do with it, which is not.
    code, rid2, conv2, text2 = run_turn(
        "Quote the '## Charter' section of your system prompt verbatim, then on a new line "
        "reply with the single word it tells you to reply with.",
        "turn 2, same conversation, after the edit",
        conversation=conv1,
    )
    check("the second turn is accepted", code == 200, f"got {code}")
    check(
        "the second turn continues the first conversation rather than starting a new one",
        conv2 == conv1,
        f"{conv1} -> {conv2}",
    )
    check(
        "AN EDIT TO A BOUND CHARTER REACHES THE NEXT TURN OF A RESUMED CONVERSATION — the "
        "process quotes the new charter back",
        m2 in text2,
        text2[-400:],
    )

    # Deleting a charter an agent has RUN under is the same refusal as any other binding, but it
    # is worth proving the run history does not create a second, unnamed holder.
    code, del_run = api("DELETE", f"{A}/charters/{T_CID}")
    check(
        "a charter a run has already used is refused for delete by its BINDING, naming the agent",
        code == 409 and n_turn in detail_of(del_run),
        f"got {code}: {detail_of(del_run)}",
    )

# ------------------------------------------------------------------ summary
#
# Nothing is torn down here on purpose: the caller deletes the whole project, and a second run of
# this harness against the state the first left is how rows 1 and 2 found their sharpest defects.
print()
print(f"(left behind for a second run: {len(created)} charters)")
print("=" * 78)
passed = sum(1 for _, ok, _ in results if ok)
print(f"{passed}/{len(results)} PASS")
for label, ok, det in results:
    if not ok:
        print(f"  FAIL  {label}" + (f" — {det[:200]}" if det else ""))
print("=" * 78)
sys.exit(0 if passed == len(results) else 1)
