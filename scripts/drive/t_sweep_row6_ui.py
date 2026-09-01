"""Sweep row 6's screen half - what an operator sees of their conversations.

The API half measures what the Hub records. This asks the three questions it cannot:

  1. does the rail distinguish an OPEN conversation from an ARCHIVED one, and can the operator
     reach the archived ones at all;
  2. does a rename the Hub REFUSES reach the operator - F187/F173's shape, which by row 5 had
     appeared at six sites;
  3. what happens to an open conversation whose AGENT has been archived. `GET /conversations`
     returns it (measured), `GET /agents` does not list its owner, and the rail has two views
     built on opposite iterations: `AgentTree` maps over *agents* (`AgentTree.tsx:82`), the
     `RecencyView` maps over *conversations* (`RecencyView.tsx:55,66`). Both are driven here.

Run: AW_HUB=... AW_KEY=... AW_PROJECT=<project id> AW_AGENT=<an agent with a claude runner>
     AW_SHOTS=<dir> py -3.11 scripts/drive/t_sweep_row6_ui.py

Every assertion about text an operator must READ goes through `page.inner_text("body")`, never
`page.content()` - row 3 lost a real defect to a green row because a needle matched the markup.

The Hub on :8011 serves `hub/hub/static/ui`, a committed build artefact, so what this captures is
the shipped bundle rather than `hub/ui/src`.
"""

import json
import os
import pathlib
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
KEY = os.environ["AW_KEY"]
PROJECT = os.environ["AW_PROJECT"]
AGENT = os.environ["AW_AGENT"]
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
OUT = pathlib.Path(os.environ.get("AW_SHOTS", "."))
OUT.mkdir(parents=True, exist_ok=True)

SEED = f"""
sessionStorage.setItem('agentweave-session', {json.dumps(json.dumps({"apiKey": KEY, "hubUrl": HUB}))});
localStorage.setItem('agentweave-selected-project', {json.dumps(PROJECT)});
localStorage.setItem('aw.railView', {json.dumps("tree")});
"""

A = f"/projects/{PROJECT}"
results = []


def check(label, ok, detail=""):
    results.append((label, bool(ok), detail))
    shown = detail if len(detail) <= 300 else detail[:300] + f"... ({len(detail)} chars)"
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" - {shown}" if shown else ""))


# ---------------------------------------------------------------- state to look at
#
# Built here rather than assumed. Row 5's lesson twice over: create the condition under test, and
# do not inherit one from an earlier invocation.

code, convs = api("GET", f"{A}/conversations")
OPEN_ROWS = convs.get("conversations", []) if isinstance(convs, dict) else []
CONV = next((c["id"] for c in OPEN_ROWS if c.get("agent") == AGENT), None)
check("the project holds an open conversation for this agent to look at", bool(CONV), str(CONV))

code, arch_convs = api("GET", f"{A}/conversations?lifecycle=archived")
ARCHIVED_ROWS = arch_convs.get("conversations", []) if isinstance(arch_convs, dict) else []
ARCHIVED_CONV = next((c for c in ARCHIVED_ROWS if c.get("agent") == AGENT), None)
check(
    "and an archived one, so 'open' and 'archived' can be told apart on screen",
    bool(ARCHIVED_CONV),
    str(ARCHIVED_CONV and ARCHIVED_CONV["id"]),
)

# ---- the orphan: an OPEN conversation whose agent is archived.
ORPHAN_AGENT = f"orph{TAG}{time.strftime('%M%S')}"
code, runners = api("GET", f"{A}/runners")
RUNNER = runners[0]["id"] if code == 200 and runners else None
api("POST", f"{A}/agents", {"name": ORPHAN_AGENT, "runner_id": RUNNER})
code, otrig = api(
    "POST",
    f"{A}/agent/trigger",
    {"agent": ORPHAN_AGENT, "message": f"orphan thread {TAG} - reply with ok, no tools"},
)
ORPHAN_CONV = otrig.get("conversation_id") if code == 200 else None
time.sleep(3)
api("POST", f"{A}/agent/{ORPHAN_AGENT}/stop")
for _ in range(20):
    code, qstat = api("GET", f"{A}/queue/{ORPHAN_AGENT}/status")
    if isinstance(qstat, dict) and not qstat.get("running"):
        break
    time.sleep(2)
code, arch_agent = api("POST", f"{A}/agents/{ORPHAN_AGENT}/archive")
check("an agent owning an open conversation can be archived", code == 200, f"got {code}")

code, agents_now = api("GET", f"{A}/agents")
roster = [a["name"] for a in agents_now] if isinstance(agents_now, list) else []
check(
    "the archived agent leaves the roster the rail's tree iterates",
    ORPHAN_AGENT not in roster,
    str(roster),
)
code, convs_now = api("GET", f"{A}/conversations")
still_listed = [c for c in convs_now.get("conversations", []) if c.get("agent") == ORPHAN_AGENT]
check(
    "but its OPEN conversation is still returned by the list the rail is built on",
    bool(still_listed),
    f"{len(still_listed)} row(s) for an agent no longer on the roster",
)

# ---- a freshly generated title, so section 5 reads one the operator never typed.
GEN_CONV, GEN_TITLE = None, None
if not os.environ.get("AW_SKIP_TURN"):
    api("PUT", f"{A}/settings", {"conversation_title_mode": "generate"})
    code, gtrig = api(
        "POST",
        f"{A}/agent/trigger",
        {
            "agent": AGENT,
            "message": (
                "In one short sentence, say what a write-ahead log is for in a database. "
                "Do not use any tools."
            ),
        },
    )
    GEN_CONV = gtrig.get("conversation_id") if code == 200 else None
    seed_title = None
    if GEN_CONV:
        code, rows = api("GET", f"{A}/agent/{AGENT}/conversations")
        seed_title = next((c["title"] for c in rows if c["id"] == GEN_CONV), None)
        deadline = time.time() + 210
        while time.time() < deadline:
            code, rows = api("GET", f"{A}/agent/{AGENT}/conversations")
            now = next((c["title"] for c in rows if c["id"] == GEN_CONV), None)
            if now and now != seed_title:
                GEN_TITLE = now
                break
            time.sleep(4)
    api("PUT", f"{A}/settings", {"conversation_title_mode": "truncate"})
    check(
        "a worker generated a title for a fresh conversation, for the screen half to read",
        bool(GEN_TITLE),
        f"{seed_title!r} -> {GEN_TITLE!r}",
    )

CONV_URL = f"{HUB}/?project={PROJECT}&agent={AGENT}" + (f"&conversation={CONV}" if CONV else "")

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 950})
    console_errors = []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(str(e)))
    page.add_init_script(SEED)

    # ------------------------------------------------------ 1. the rail's tree
    page.goto(CONV_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)

    # Expand only if collapsed. The first version clicked unconditionally and CLOSED the project
    # the operator was already inside, then measured an empty rail — row 5's lesson (a harness
    # that inherits state reports the product broken) at a third site.
    def expand(testid, collapsed_marker="aria-label", collapsed_value="Expand"):
        try:
            el = page.query_selector(f'[data-testid="{testid}"]')
            if el is None:
                return False
            attr = el.get_attribute(collapsed_marker) or ""
            if attr.startswith(collapsed_value) or attr == "false":
                el.click()
                page.wait_for_timeout(1200)
            return True
        except Exception:  # noqa: BLE001
            return False

    expand(f"project-expander-{PROJECT}")
    expand(f"agent-expander-{PROJECT}-{AGENT}", "aria-expanded", "false")
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT / "row6-01-rail-tree.png"), full_page=False)
    text = page.inner_text("body")
    check("the rail renders and names the agent", AGENT in text, page.title())

    rail = ""
    try:
        rail = page.inner_text('[data-testid="sidebar"]')
    except Exception as exc:  # noqa: BLE001
        check("the sidebar is present", False, str(exc))
    # Scoped to THIS project's subtree, not the whole rail: an earlier drive left an agent
    # literally named `conv-probe` in another project, and the unscoped version of this
    # assertion was red for that. A harness bug, caught before it was written up as a finding.
    own_rail = ""
    try:
        own_rail = page.inner_text(f'[data-testid="rail-project-{PROJECT}"]')
    except Exception:  # noqa: BLE001
        own_rail = rail
    check(
        "the open conversation is on the rail by its title, never by its id",
        bool(own_rail) and "conv-" not in own_rail,
        " / ".join(line for line in own_rail.splitlines() if "conv-" in line)[:250],
    )
    # "Show archived (N)" lives in the agent row's menu, not on the rail at rest.
    agent_menu_text = ""
    try:
        page.click(f'[data-testid="agent-menu-{PROJECT}-{AGENT}"]', timeout=3000)
        page.wait_for_timeout(900)
        agent_menu_text = page.inner_text("body")
        page.screenshot(path=str(OUT / "row6-01b-agent-menu.png"), full_page=False)
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)
    except Exception as exc:  # noqa: BLE001
        check("the agent's row menu is reachable", False, str(exc))
    check(
        "THE RAIL OFFERS THE ARCHIVED CONVERSATIONS AND STATES HOW MANY - an archived thread the "
        "operator cannot reach is a thread they have lost",
        "archived" in agent_menu_text.lower(),
        " / ".join(line for line in agent_menu_text.splitlines() if "archiv" in line.lower())[:250],
    )

    # ------------------------------------------------------ 2. the orphan in the tree
    check(
        "AN OPEN CONVERSATION OWNED BY AN ARCHIVED AGENT IS REACHABLE IN THE TREE VIEW",
        ORPHAN_AGENT in rail,
        f"looking for {ORPHAN_AGENT!r}; rail names: "
        + ", ".join(sorted({line.strip() for line in rail.splitlines() if line.strip()}))[:220],
    )

    # ------------------------------------------------------ 3. the orphan in the recency view
    try:
        page.click('[data-testid="rail-view-toggle"]', timeout=3000)
        page.wait_for_timeout(2500)
    except Exception as exc:  # noqa: BLE001
        check("the rail's view toggle is reachable", False, str(exc))
    page.screenshot(path=str(OUT / "row6-02-rail-recency.png"), full_page=False)
    recency = page.inner_text('[data-testid="sidebar"]')
    orphan_needle = f"orphan thread {TAG}"
    check(
        "THE SAME CONVERSATION IS OR IS NOT IN THE RECENCY VIEW - the two rail views must agree "
        "about which threads exist",
        (orphan_needle.lower() in recency.lower()) == (ORPHAN_AGENT in rail),
        f"recency shows it: {orphan_needle.lower() in recency.lower()}; tree shows it: {ORPHAN_AGENT in rail}",
    )
    page.click('[data-testid="rail-view-toggle"]')
    page.wait_for_timeout(2000)

    # ------------------------------------------------------ 4. a rename the Hub refuses
    #
    # The rename input carries no maxLength, so a title past CONVERSATION_TITLE_MAX_LENGTH is
    # typeable and the Hub answers 400. Whether the operator ever learns that is the question.
    refused = False
    if CONV:
        try:
            page.click(f'[data-testid="rail-conversation-{CONV}-menu"]', timeout=3000)
            page.wait_for_timeout(800)
            page.click('text="Rename"', timeout=3000)
            page.wait_for_timeout(800)
            page.fill(f'[data-testid="rail-conversation-{CONV}-rename"]', "z" * 400)
            page.keyboard.press("Enter")
            page.wait_for_timeout(2500)
            refused = True
        except Exception as exc:  # noqa: BLE001
            check(
                "the rename control is reachable from the conversation's row menu", False, str(exc)
            )
    if refused:
        page.screenshot(path=str(OUT / "row6-03-rename-refused.png"), full_page=False)
        rail_after = page.inner_text('[data-testid="sidebar"]')
        check(
            "A RENAME THE HUB REFUSED SAYS SO ON SCREEN, in the Hub's own words",
            "120" in rail_after or "cannot exceed" in rail_after.lower(),
            " / ".join(line for line in rail_after.splitlines() if "z" not in line.lower())[:250],
        )
        code, after = api("GET", f"{A}/conversations")
        row = next(
            (c for c in after.get("conversations", []) if c["id"] == CONV),
            {},
        )
        check(
            "and the refused title was not stored",
            not (row.get("title") or "").startswith("zzzz"),
            repr(row.get("title")),
        )

    # ------------------------------------------------------ 5. a generated title on the rail
    if GEN_CONV and GEN_TITLE:
        page.goto(
            f"{HUB}/?project={PROJECT}&agent={AGENT}&conversation={GEN_CONV}",
            wait_until="domcontentloaded",
        )
        page.wait_for_timeout(4500)
        expand(f"project-expander-{PROJECT}")
        expand(f"agent-expander-{PROJECT}-{AGENT}", "aria-expanded", "false")
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "row6-04-generated-title.png"), full_page=False)
        shown = page.inner_text("body")
        check(
            "a worker-generated title is what the operator actually reads, not the raw first message",
            GEN_TITLE in shown,
            f"looking for {GEN_TITLE!r}",
        )
    else:
        check(
            "the project holds a generated title to look for on screen",
            False,
            "none - the titler produced nothing for this run",
        )

    # ------------------------------------------------------ 6. console
    #
    # Unfiltered: this harness provokes exactly one deliberate 4xx (the over-long rename), so the
    # 400 it produces is filtered by name and nothing else is expected.
    unexpected = [e for e in console_errors if "400" not in e and "Bad Request" not in e]
    check(
        "no unexpected console errors on the conversation surfaces",
        not unexpected,
        str(unexpected[:3]),
    )

    browser.close()

# ---------------------------------------------------------------- teardown of what this built
api("POST", f"{A}/agents/{ORPHAN_AGENT}/unarchive")
if ORPHAN_CONV:
    api("POST", f"{A}/agent/{ORPHAN_AGENT}/conversations/{ORPHAN_CONV}/archive")

print()
print("=" * 78)
passed = sum(1 for _, ok, _ in results if ok)
print(f"ROW 6 UI - {passed}/{len(results)} assertions passed")
for label, ok, detail in results:
    if not ok:
        print(f"  FAIL  {label}" + (f"  [{detail[:220]}]" if detail else ""))
print(f"screenshots: {OUT}")
print("=" * 78)
