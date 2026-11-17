"""Live drive for `a-project-with-no-specs-is-offered-a-start` ac-map-reviewable and ac-decline
(PNSOS-4), 2026-11-17: a real Haiku turn writes a system map and its capability drafts on a small
fixture repository; then the operator approves one draft and folds it into a new capability, and
archives another.

Reuses `corpus_start_drive.py`'s Hub, project and browser helpers: it starts its own Hub from THIS
checkout's `hub/` on a scratch port and a fresh database (default :8028; AW_DRIVE_PORT moves it), and
refuses :8000, :8010 and any port that already answers. Everything is arranged and acted on through
the Hub's routes, as the operator's app does.

Checks, printed in the `drive_baseline` shape:
  ac-map-reviewable  before the operator acts: a system map proposing titles, at least one draft
                     (a change-spec with no tasks creating a proposed title), zero current
                     capabilities; after approving one draft and folding it into a capability
                     created for it: exactly one current capability, holding that draft's
                     requirement keys, and every other draft still not a capability.
  ac-decline         archiving another draft from exploring is accepted, creates no capability,
                     and the map's page shows that row `declined`.

Screenshots of the map and the first draft go to testbed/capability-drafts-drive/<HHMMSS>/.

    py -3.11 scripts/drive/capability_drafts_drive.py
"""

import os
import pathlib
import sys
import time
import urllib.parse

os.environ.setdefault("AW_DRIVE_PORT", "8028")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import corpus_start_drive as cs  # noqa: E402

OUT = cs.REPO / "testbed" / "capability-drafts-drive" / cs.STAMP
cs.OUT = OUT

FILES = {
    "README.md": "Shopfront: a tiny shop backend. Billing issues invoices, accounts log users in, "
    "and reports summarise sales.\n",
    "shop/billing.py": (
        "TAX = 0.2\n\n\n"
        "def invoice_total(lines):\n"
        '    """The invoice total: each line\'s price times quantity, plus tax."""\n'
        "    net = sum(line['price'] * line['qty'] for line in lines)\n"
        "    return round(net * (1 + TAX), 2)\n\n\n"
        "def refund(total, reason):\n"
        "    if not reason:\n"
        "        raise ValueError('a refund needs a reason')\n"
        "    return -total\n"
    ),
    "shop/accounts.py": (
        "import hashlib\n\n"
        "USERS = {}\n\n\n"
        "def register(name, password):\n"
        "    if name in USERS:\n"
        "        raise ValueError('name taken')\n"
        "    USERS[name] = hashlib.sha256(password.encode()).hexdigest()\n\n\n"
        "def login(name, password):\n"
        "    return USERS.get(name) == hashlib.sha256(password.encode()).hexdigest()\n"
    ),
    "tests/test_billing.py": (
        "from shop.billing import invoice_total\n\n\n"
        "def test_total_includes_tax():\n"
        "    assert invoice_total([{'price': 10, 'qty': 2}]) == 24.0\n"
    ),
}

AGENT = "Mapper"


def documents(project):
    return project.documents()


def current_capabilities(project):
    return [d for d in documents(project) if d.get("kind") == "capability" and d.get("phase") == "current"]


def read(project, path):
    code, out = cs.api("GET", f"{project.base}/project/spec?path={urllib.parse.quote(path)}")
    cs.expect(code, (200,), f"read {path}", out)
    return out


def requirement_keys(project, path):
    code, out = cs.api(
        "GET", f"{project.base}/project/spec/requirements?document={urllib.parse.quote(path)}&include_retired=false"
    )
    cs.expect(code, (200,), f"requirements of {path}", out)
    return sorted(r["key"] for r in out["requirements"])


def drafts_of(project, proposed):
    """Change documents with no tasks whose `capabilities.creates` holds a proposed title."""
    wanted = {t.casefold() for t in proposed}
    found = []
    for doc in documents(project):
        if doc.get("kind") != "change-spec":
            continue
        creates = [c["title"] for c in ((doc.get("capabilities") or {}).get("creates") or [])]
        if creates and all(t.casefold() in wanted for t in creates):
            found.append((doc, creates))
    return found


def wait_for_turn(project, conversation, secs=1200):
    """Until a run in the start's conversation has ended and none is still running, or `secs` pass.
    Answers the ended runs' `(status, error)`, or None on a timeout."""
    end = time.time() + secs
    while time.time() < end:
        code, out = cs.api("GET", f"{project.base}/agent/{AGENT}/chat/{conversation}")
        runs = (out or {}).get("runs", {}) if code == 200 else {}
        if runs and all(r.get("status") not in ("started", "running") for r in runs.values()):
            return [(r.get("status"), r.get("error")) for r in runs.values()]
        time.sleep(10)
    return None


def main():
    if str(cs.PORT) in ("8000", "8010"):
        sys.exit("REFUSING: this drive starts its own Hub and never runs on :8000 or :8010")
    if cs.port_answers():
        sys.exit(f"REFUSED: :{cs.PORT} already answers; pick another AW_DRIVE_PORT")
    cs.SCRATCH.mkdir(parents=True, exist_ok=True)
    proc = cs.start_hub(cs.SCRATCH / "hub.log")
    try:
        run()
    except cs.Setup as exc:
        print(f"SETUP: {exc}", flush=True)
    finally:
        cs.stop_hub(proc)
    print("\n== drive_baseline")
    failed = False
    for key in ("ac-map-reviewable", "ac-decline"):
        reached, failed_here, detail = cs.checks.get(key, (False, False, "not run"))
        failed = failed or failed_here or not reached
        print(cs.baseline_line(key, reached, failed_here, detail))
    print(f"output: {OUT}")
    sys.exit(1 if failed else 0)


def run():
    project = cs.Project("drafts", files=FILES, agents=[(AGENT, None)]).open()
    print(f"project {project.pid} at {project.root}", flush=True)
    code, started = cs.api("POST", f"{project.base}/project/corpus/start", {"start": "existing-code", "agent": AGENT})
    cs.expect(code, (201,), "take the existing-code start", started)
    map_path = started["document"]["path"]
    conversation = started.get("conversation_id") or (started.get("conversation") or {}).get("id")
    print(f"start: map {map_path}, conversation {conversation}; waiting for {AGENT}'s Haiku turn", flush=True)
    ended = wait_for_turn(project, conversation)
    if ended is None:
        cs.record("ac-map-reviewable", False, False, "the Haiku turn did not finish within 20 minutes")
        return
    print(f"the turn ended: {ended}", flush=True)
    # The agent may rename the map, as the prompt's create-rename-submit sequence does for drafts.
    maps = [d for d in documents(project) if d.get("kind") == "system-map"]
    if len(maps) != 1:
        cs.record("ac-map-reviewable", False, False, f"{len(maps)} system maps after the turn, wanted one")
        return
    map_path = maps[0]["path"]
    reviewable(project, map_path)


def reviewable(project, map_path):
    from playwright.sync_api import sync_playwright

    key = "ac-map-reviewable"
    view = read(project, map_path)
    proposed = [c["title"] for c in ((view.get("capabilities") or {}).get("creates") or [])]
    drafts = drafts_of(project, proposed)
    caps_before = current_capabilities(project)
    print(f"map proposes {proposed}; drafts {[(d['path'], c) for d, c in drafts]}; "
          f"current capabilities {len(caps_before)}", flush=True)
    if not proposed or not drafts:
        everything = [(d["path"], d.get("kind"), d.get("capabilities")) for d in documents(project)]
        cs.record(key, False, False, f"the turn left no reviewable drafts: proposed {proposed}; documents {everything}")
        return
    with sync_playwright() as play:
        browser = play.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_init_script(
            "try { sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s})); } catch (e) {}"
            % (cs.json.dumps(cs.KEY), cs.json.dumps(cs.HUB)))
        page = context.new_page()
        cs.goto(page, cs.url(project, document=map_path))
        cs.present(page, cs.MAP_ROW, 6000)
        cs.shot(page, "map-before")
        shown_before = [(r[0], r[1]) for r in cs.map_rows(page)]
        first, titles = drafts[0]
        cs.goto(page, cs.url(project, document=first["path"]))
        cs.shot(page, "draft-before")

        try:
            cs.need(len(caps_before) == 0, f"{len(caps_before)} current capabilities before the operator acted")
            cs.need(all(d.get("phase") == "exploring" for d, _ in drafts), "a draft is not exploring before review")
            cs.need(sorted(t.casefold() for t, _ in shown_before) == sorted(t.casefold() for t in proposed),
                    f"the map's page shows {shown_before}, the map proposes {proposed}")
            draft_keys = requirement_keys(project, first["path"])
            cs.need(draft_keys, f"the draft {first['path']} has no requirements")
            project.approve(first["path"])
            title = titles[0]
            slug = "".join(ch if ch.isalnum() else "-" for ch in title.lower()).strip("-")
            cap = project.create(title, "capability", f"spec/capabilities/{slug}/spec.json")
            project.fold(first["path"], cap)
            caps_after = current_capabilities(project)
            cs.need([c["path"] for c in caps_after] == [cap], f"current capabilities after the fold: {[c['path'] for c in caps_after]}")
            cap_keys = requirement_keys(project, cap)
            # A fold namespaces each key it carries with the change's slug (the fold's own policy),
            # so each of the draft's requirements is the capability key ending in its own key.
            carried = [k for k in draft_keys if sum(c == k or c.endswith("-" + k) for c in cap_keys) == 1]
            cs.need(len(cap_keys) == len(draft_keys) and carried == draft_keys,
                    f"the capability holds {cap_keys}, the draft had {draft_keys}")
            others = [d for d, _ in drafts[1:]]
            still = {d["path"]: next(x for x in documents(project) if x["path"] == d["path"]) for d in others}
            cs.need(all(x.get("kind") == "change-spec" and not x.get("folded_into") for x in still.values()),
                    f"another draft became part of a capability: {still}")
            cs.goto(page, cs.url(project, document=map_path))
            cs.present(page, cs.MAP_ROW, 6000)
            page.wait_for_timeout(1500)
            cs.shot(page, "map-after-fold")
            after = {t.casefold(): s for t, s, _ in cs.map_rows(page)}
            cs.need(after.get(title.casefold()) == "current", f"the folded draft's row reads {after}")
            cs.record(key, True, True,
                      f"before: {len(drafts)} drafts {[d['path'] for d, _ in drafts]}, 0 capabilities; after approving "
                      f"and folding {first['path']} into {cap}: capabilities {[c['path'] for c in caps_after]} with "
                      f"keys {cap_keys}; others unfolded {list(still)}; map rows {after}")
        except cs.Failed as exc:
            cs.record(key, True, False, str(exc))
        except (cs.Setup, cs.NotReached) as exc:
            cs.record(key, False, False, str(exc))

        decline(project, map_path, drafts[1:], page)
        context.close()
        browser.close()


def decline(project, map_path, rest, page):
    key = "ac-decline"
    if not rest:
        cs.record(key, False, False, "the turn wrote one draft, so there is no second draft to decline")
        return
    target, titles = rest[0]
    before = len(current_capabilities(project))
    try:
        code, out = cs.api("POST", f"{project.base}/project/documents/phase?path={urllib.parse.quote(target['path'])}&to=archived",
                           {"reason": "not how we see it"})
        cs.need(code == 200, f"archiving the exploring draft {target['path']} answered {code} {str(out)[:300]}")
        cs.need(len(current_capabilities(project)) == before, "archiving a draft created a capability")
        cs.goto(page, cs.url(project, document=map_path))
        cs.present(page, cs.MAP_ROW, 6000)
        page.wait_for_timeout(1500)
        cs.shot(page, "map-after-decline")
        rows = {t.casefold(): (s, d) for t, s, d in cs.map_rows(page)}
        row = rows.get(titles[0].casefold())
        cs.need(row == ("declined", target["path"]), f"the declined draft's row reads {row}")
        cs.record(key, True, True, f"{target['path']} archived; no capability created; its row reads {row}")
    except cs.Failed as exc:
        cs.record(key, True, False, str(exc))
    except cs.Setup as exc:
        cs.record(key, False, False, str(exc))


if __name__ == "__main__":
    main()
