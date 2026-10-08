"""Browser half of `a-document-names-its-default-reviewer`'s drive: the approval bar says who reviews.

In Chromium on the bundle `:8010` serves, two proposed flow-delivered documents in a project that has
`critic` on its roster: one names `critic`, one names `ghost` (no such agent). The first bar reads
"Reviewed by @critic."; the second is amber and says the reviews will come to the operator. No agent
turn is spent.

Usage: py -3.11 scripts/drive/d1008_default_reviewer_bar.py <project id from the drive>
"""

import json
import pathlib
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

HUB = "http://127.0.0.1:8010"
KEY = (pathlib.Path.home() / ".agentweave/hub/profiles/trial/bootstrap-key.txt").read_text().strip()
OUT = pathlib.Path(__file__).resolve().parents[2] / "testbed/drive1008-defaultreviewer"
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""))


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{HUB}/api/v1{path}", data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:2000]


def proposed(P, title, reviewer):
    _, doc = api("POST", f"{P}/project/documents", {"title": title})
    path = doc["path"]
    payload = {
        "schema_version": 1, "kind": doc["kind"], "title": title, "summary": "s", "problem": "p",
        "scope": {"in_scope": ["x"], "non_goals": ["n"]},
        "requirements": [{"key": "r", "statement": "It MUST work.", "modal": "MUST"}],
        "acceptance_criteria": [{"key": "c", "requirement": "r", "given": "g", "when": "w", "then": "t"}],
        "tasks": [{"key": "t", "title": "t", "description": "d", "requirements": ["r"]}],
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [],
        "delivery": {"mode": "flow", "agent": "alice", "reviewer": reviewer,
                     "stop_when_queue_empties": True, "cron": "0 3 1 1 *"},
    }
    code, res = api("PUT", f"{P}/project/documents/{path}/content", {"document": payload})
    assert code == 200, res
    api("POST", f"{P}/project/documents/close-exploration?path={path}")
    _, res = api("POST", f"{P}/project/documents/propose?path={path}")
    assert res.get("phase") == "proposed", res
    return path


def main(pid):
    P = f"/projects/{pid}"
    named = proposed(P, "bar names critic", "critic")
    ghost = proposed(P, "bar names ghost", "ghost")
    seed = (
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
        " localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid)
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed)
        for path, expect, stale, shot in (
            (named, "Reviewed by @critic.", "false", "bar-critic.png"),
            (ghost, "which is not an agent on this project: its reviews will come to you", "true",
             "bar-ghost.png"),
        ):
            page.goto(f"{HUB}/?project={pid}&tab=spec&document={path}", wait_until="domcontentloaded")
            line = page.locator('[data-testid="delivery-reviewer"]')
            line.wait_for(timeout=30000)
            text = line.inner_text()
            check(f"{path}: the bar says who reviews", expect in text, text)
            check(f"{path}: stale={stale}", line.get_attribute("data-stale") == stale)
            page.screenshot(path=str(OUT / shot))
        browser.close()
    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed; shots in {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
