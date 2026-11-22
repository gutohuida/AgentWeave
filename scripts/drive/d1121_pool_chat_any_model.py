"""Drive the profile model pool, a chat's model choice and the profiles home (F1200, F1204, F1207).

Two modes.

--assert (the acceptance drive of spec/changes/a-profile-s-pool-and-a-new-chat-can-use-any-model-
of-any-provider, task acceptance-drive): starts a fresh Hub from this checkout's hub/ (AW_DRIVE_PORT,
default 8037, a new database; or reuses one named by AW_HUB, AW_KEY and AW_DB -- never :8000 or
:8010), opens two scratch projects and measures every row the criteria name. Prints one line per
row and one verdict line per criterion (`check <key>: reached=... failed_at_assertion=...`), and
exits 1 on any failure. `--shots <prefix>` also writes
testbed/drive1121-pool/shots/<prefix>-*.png in dark, light and narrow (ac-screens-reviewed, which
the operator judges). About five short real turns: Haiku 4.5 (chat), Haiku 4.5 at High (chat),
Sonnet 5.5 (chat), one Codex turn on gpt-6-luna when the Hub accepts it, and Builder's task run on
its pool default (Haiku 5.5). Roughly 10-15 minutes.

    py -3.11 scripts/drive/d1121_pool_chat_any_model.py --assert [--shots after]

The setup:
  project "pooldrive"   runner Haiku (claude/claude-haiku-5-5); Builder, QA and Old on it, Old
                        archived; Scout with an empty pool (No model); a spec document with one
                        task for Builder, approved and built as a flow (cron once a year: the drive
                        fires it), so Builder has a task in a build
  project "pooldrive-empty"  no profiles: the empty Profiles index, both creation dialogs and
                        Add a builder and a checker (ac-setup-unused-model)

What the rows assume of the built change, where the criteria leave it open (the tasks that turn
this green may adjust a selector, never an assertion):
  - a pool entry by model is `{"provider": <cli>, "model": <catalog id>, "effort": ...}` inside
    PATCH /agents/{name} `pool`, beside today's `{"runner_id": ...}` entries;
  - a chat turn names its model as `overrides: {"model": <catalog id>}` (and `effort`) on
    POST /agent/trigger, as the trigger already documents;
  - the profile page is `[data-testid=profile-page]`, its tabs the radiogroup "<name> sections"
    (Profile, Models, ...), its switcher "<name>. Switch profile", its rows
    `[data-slot=profile-row][data-profile=<name>]` (the accepted mock's components);
  - a name link has the accessible name "Open <name>'s profile" (straight or curly apostrophe);
  - menus are the app's MenuSelect ([role=menu] / [role=menuitemradio]) or a listbox of options.

Without --assert: the original observation (edits nothing). Needs a fresh drive Hub:
  AW_HUB, AW_KEY, AW_PROJECT   the Hub, its key, a project with runners `haiku`/`haiku45` and a
                               profile Builder whose pool holds both (see testbed/drive1121-pool/ids.json)
"""
import datetime
import json
import os
import pathlib
import re
import secrets
import sys
import urllib.parse

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

SHOTS = "testbed/drive1121-pool/shots"
POP = r"""()=>{const e=document.querySelector('[role=listbox],[role=menu]');return e?e.innerText.replace(/\n/g,' | '):'(no popup)'}"""

# Every visible option of every open popup: its first line, accessible name, whether it can be
# chosen, the group it sits under, and the popup's own text (for its footer).
POPUP = r"""() => {
  const shown = e => !!e && e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden';
  const pops = [...document.querySelectorAll('[role=listbox],[role=menu]')].filter(shown);
  const out = {open: pops.length > 0, items: [], text: ''};
  for (const pop of pops) {
    out.text += ' | ' + (pop.closest('.aw-pool-popover') || pop.parentElement || pop).innerText.replace(/\n/g, ' | ');
    let heading = '';
    const walker = document.createTreeWalker(pop, NodeFilter.SHOW_ELEMENT);
    while (walker.nextNode()) {
      const e = walker.currentNode;
      const role = e.getAttribute('role') || '';
      if (!shown(e)) continue;
      if (role === 'option' || role.startsWith('menuitem')) {
        const grp = e.closest('[role=group]');
        out.items.push({
          text: (e.innerText || '').split('\n').map(s => s.trim()).filter(Boolean)[0] || '',
          all: (e.innerText || '').replace(/\n/g, ' '),
          label: e.getAttribute('aria-label') || '',
          disabled: e.getAttribute('aria-disabled') === 'true' || e.hasAttribute('data-disabled'),
          submenu: e.getAttribute('aria-haspopup') === 'menu',
          group: (grp && (grp.getAttribute('aria-label') || '')) || heading,
        });
      } else if (/^H[1-6]$/.test(e.tagName) || e.matches('[data-slot=menu-label], [role=presentation], .aw-pool-group-head, .aw-menu-label')) {
        const t = (e.innerText || '').trim();
        if (t && !e.querySelector('[role=option],[role^=menuitem]')) heading = t;
      }
    }
  }
  return out;
}"""

FOCUS = """() => { const e = document.activeElement; return e ? {tag: e.tagName,
  profile: e.getAttribute('data-profile') || '', label: e.getAttribute('aria-label') || '',
  text: (e.innerText || '').trim().slice(0, 60)} : null }"""

PROFILE_LINK = re.compile(r"^Open Builder[’']s profile$")


def link_name(name):
    return re.compile(rf"^Open {re.escape(name)}[’']s profile$")


class Drive:
    def __init__(self, d, pid, empty_pid, root, shots):
        self.d, self.pid, self.empty, self.root, self.shots = d, pid, empty_pid, root, shots
        self.rows = {}
        self.catalog = {}
        self.cli_label = {}
        self.ids = {}

    # -- plumbing -----------------------------------------------------------------------------
    def api(self, method, path, body=None, timeout=60):
        return self.d.api(method, path, body, timeout=timeout)

    def row(self, crit, label, reached, ok, detail=""):
        self.rows.setdefault(crit, []).append((label, bool(reached), bool(reached and ok), detail))
        state = "PASS" if reached and ok else ("FAIL" if reached else "NOT REACHED")
        print(f"  {state:11} {crit} [{label}] {str(detail)[:600]}", flush=True)

    def guard(self, crit, label, fn):
        """Runs one row; an exception the row did not expect is a failure at that row, reached
        when the setup it needed held (it did, or the row would not be running)."""
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 -- one row's break must not hide the others
            self.row(crit, label, True, False, f"raised {type(exc).__name__}: {str(exc)[:400]}")

    def url(self, pid=None, **params):
        q = {"project": pid or self.pid, **params}
        return f"{self.d.HUB}/?{urllib.parse.urlencode(q)}"

    def goto(self, pg, url, wait=2500):
        pg.goto(url)
        pg.wait_for_timeout(wait)

    def shot(self, pg, name):
        if self.shots:
            pg.screenshot(path=f"{SHOTS}/{self.shots}-{name}.png")

    def agent(self, name, pid=None):
        code, out = self.api("GET", f"/projects/{pid or self.pid}/agents/{name}")
        return out if code == 200 else None

    def pool(self, name, pid=None):
        a = self.agent(name, pid) or {}
        return sorted((e.get("runner_id"), e.get("effort"), bool(e.get("default"))) for e in a.get("pool") or [])

    def pool_full(self, name, pid=None):
        return (self.agent(name, pid) or {}).get("pool") or []

    def runners(self, pid=None):
        code, out = self.api("GET", f"/projects/{pid or self.pid}/runners")
        return out if code == 200 else []

    def set_pool(self, name, entries):
        return self.api("PATCH", f"/projects/{self.pid}/agents/{name}", {"pool": entries})

    def runs(self, conv=None, task=None):
        if conv:
            return self.d.ro("select id, model, effort, status, runner_id, task_id from runs "
                             "where conversation_id=? order by started_at", (conv,))
        return self.d.ro("select id, model, effort, status, runner_id, conversation_id from runs "
                         "where task_id=? and id not like 'run-d1029-%' order by started_at", (task,))

    def trigger(self, body):
        return self.api("POST", f"/projects/{self.pid}/agent/trigger", {"agent": "Builder", **body})

    def turn(self, body, conv=None):
        """One chat turn; waits for it. Returns (status, response, the run it launched or None)."""
        before = {r[0] for r in self.runs(conv)} if conv else set()
        code, out = self.trigger({**body, **({"conversation_id": conv} if conv else {})})
        if code != 200:
            return code, out, None
        c = out.get("conversation_id")
        run = None
        if self.d.poll(lambda: [r for r in self.runs(c) if r[0] not in before], 90, 1):
            self.d.wait_idle(self.pid, 6 * 60)
            run = next(r for r in reversed(self.runs(c)) if r[0] not in before)
        return code, out, run

    def labels(self, cli):
        return [m["label"] for m in self.catalog.get(cli, [])]

    # -- UI helpers ---------------------------------------------------------------------------
    @staticmethod
    def popup(pg):
        return pg.evaluate(POPUP)

    @staticmethod
    def close_popup(pg):
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(250)

    def menu_labels(self, pg, trigger):
        """Opens `trigger`, expands any submenu (a provider step), and returns every option seen."""
        trigger.click()
        pg.wait_for_timeout(500)
        seen = self.popup(pg)
        items = list(seen["items"])
        for sub in [i for i in seen["items"] if i["submenu"]]:
            try:
                pg.get_by_role("menuitem", name=sub["label"] or sub["text"]).first.hover()
                pg.wait_for_timeout(400)
                items += self.popup(pg)["items"]
            except Exception:  # noqa: BLE001 -- a submenu that will not open adds nothing
                pass
        self.close_popup(pg)
        return items, seen["text"]

    @staticmethod
    def choose(pg, trigger, text):
        """Opens `trigger` and picks the option whose first line is `text` (or starts with it).
        False when the control is disabled or offers no such option."""
        if not trigger.is_enabled():
            return False
        trigger.click()
        pg.wait_for_timeout(400)
        opts = pg.locator("[role=listbox] [role=option], [role=menu] [role^=menuitem]")
        for i in range(opts.count()):
            o = opts.nth(i)
            first = (o.inner_text() or "").strip().split("\n")[0].strip()
            if first == text or first.startswith(text + " "):
                o.click()
                pg.wait_for_timeout(400)
                return True
        pg.keyboard.press("Escape")
        return False

    @staticmethod
    def triggers(scope):
        return scope.locator("[data-slot=select-trigger], [role=combobox], button[aria-haspopup]")

    def trigger_named(self, scope, pattern):
        t = self.triggers(scope)
        for i in range(t.count()):
            e = t.nth(i)
            name = (e.get_attribute("aria-label") or "") + " " + (e.get_attribute("id") or "")
            if re.search(pattern, name, re.I):
                return e
        return None

    def missing_labels(self, items, clis):
        """Catalog models of `clis` with no option showing their display name."""
        texts = [i["text"] for i in items] + [i["label"] for i in items]
        need = {}
        for cli in clis:
            for label in self.labels(cli):
                need[label] = need.get(label, 0) + 1
        missing = []
        for label, n in need.items():
            have = sum(1 for t in texts if t == label or t.startswith(label + " ") or t.startswith(label + ","))
            if have < n:
                missing.append(label)
        return missing

    # -- the profile page, today's settings screen, and the way between them --------------------
    def open_profiles_tab(self, pg, pid=None):
        """Clicks the top bar's Profiles tab. Returns (found, placed after Tasks)."""
        self.goto(pg, self.url(pid))
        tabs = pg.evaluate("""() => [...document.querySelectorAll('header [role=tab], header a, header button, nav [role=tab], nav a, nav button')]
            .map(e => (e.innerText || '').trim().split('\\n')[0]).filter(Boolean)""")
        tab = pg.get_by_role("tab", name="Profiles")
        if not tab.count():
            tab = pg.get_by_role("button", name="Profiles", exact=True)
        if not tab.count():
            tab = pg.get_by_role("link", name="Profiles", exact=True)
        if not tab.count():
            return False, False, tabs
        tab.first.click()
        pg.wait_for_timeout(1500)
        after = "Tasks" in tabs and "Profiles" in tabs and tabs.index("Profiles") == tabs.index("Tasks") + 1
        return True, after, tabs

    def open_profile_page(self, pg, name, section=None):
        """Builder's page from the Profiles index, at `section` (a tab label). False when there is
        no index to come from."""
        found, _, _ = self.open_profiles_tab(pg)
        if not found:
            return False
        row = pg.locator(f"[data-slot=profile-row][data-profile='{name}']")
        if not row.count():
            return False
        row.first.click()
        pg.wait_for_timeout(1200)
        if section:
            tab = pg.get_by_role("radiogroup", name=f"{name} sections").get_by_role("radio", name=re.compile(rf"^{section}"))
            if not tab.count():
                return False
            tab.first.click()
            pg.wait_for_timeout(800)
        return pg.get_by_test_id("profile-page").count() > 0

    def on_profile_page(self, pg, name, section=None):
        page = pg.get_by_test_id("profile-page")
        if not page.count():
            return False, "no profile page"
        switch = page.get_by_label(f"{name}. Switch profile")
        if not switch.count():
            return False, f"the page is not {name}'s"
        if section:
            radio = pg.get_by_role("radiogroup", name=f"{name} sections").get_by_role("radio", name=re.compile(rf"^{section}"))
            if not radio.count() or radio.first.get_attribute("aria-checked") != "true":
                return False, f"{name}'s page is not on {section}"
        return True, "ok"

    def open_models(self, pg, name):
        """Builder's Models: its page's Models tab, or today's settings screen when there is no page."""
        if self.open_profile_page(pg, name, "Models"):
            return "profile page"
        self.goto(pg, self.url(agent=name, settings="running"))
        return "settings screen"

    def add_region(self, pg):
        """The pool editor's Add a model area: the nearest block holding the heading and a menu."""
        return pg.locator("section, fieldset, [role=group], div").filter(has_text="Add a model").filter(
            has=pg.locator("[data-slot=select-trigger], [role=combobox], button[aria-haspopup]")).last

    # -- the rows -----------------------------------------------------------------------------
    def api_rows(self):
        haiku = self.ids["haiku"]
        base = [{"runner_id": haiku, "default": True}]

        def unknown():
            before = self.pool("Builder")
            code, out = self.set_pool("Builder", base + [{"provider": "claude", "model": "not-a-model"}])
            after = self.pool("Builder")
            ok = 400 <= code < 500 and "not-a-model" in json.dumps(out) and after == before
            self.row("ac-api-unknown", "PATCH pool + {provider claude, model not-a-model}", True, ok,
                     f"{code} {json.dumps(out)[:300]}; pool unchanged={after == before}")
        self.guard("ac-api-unknown", "unknown model", unknown)

        def reuse():
            code, sonnet = self.api("POST", f"/projects/{self.pid}/runners",
                                    {"name": "Sonnet", "cli": "claude", "model": "claude-sonnet-5-5"})
            if code not in (200, 201):
                self.row("ac-api-reuse", "a Sonnet runner exists", False, False, f"{code} {sonnet}")
                return
            count = len(self.runners())
            results = []
            for name in ("Builder", "QA"):
                c, out = self.set_pool(name, base + [{"provider": "claude", "model": "claude-sonnet-5-5"}])
                entry = next((e for e in self.pool_full(name) if e.get("model") == "claude-sonnet-5-5"), None)
                results.append((name, c, entry and entry.get("runner_id"), json.dumps(out)[:200]))
            after = len(self.runners())
            ok = all(r[1] == 200 and r[2] == sonnet["id"] for r in results) and after == count
            self.row("ac-api-reuse", "Sonnet 5.5 by provider+model to Builder and QA", True, ok,
                     f"runner {sonnet['id']}; {results}; runners {count} -> {after}")
            for name in ("Builder", "QA"):
                self.set_pool(name, base)
        self.guard("ac-api-reuse", "reuse", reuse)

    def pool_ui_rows(self, b):
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()

        def lists():
            where = self.open_models(pg, "Builder")
            region = self.add_region(pg)
            if not region.count():
                self.row("ac-pool-lists-catalog", f"Add a model on Builder's {where}", True, False, "no Add a model area")
                return
            trig = self.triggers(region)
            items = []
            provider = self.trigger_named(region, r"provider")
            if provider is not None:
                # A provider step: each provider's models are listed once it is chosen.
                for cli in self.catalog:
                    if self.choose(pg, provider, self.cli_label[cli]) or self.choose(pg, provider, cli.capitalize()):
                        model = self.trigger_named(region, r"model") or trig.nth(1)
                        got, _ = self.menu_labels(pg, model)
                        items += got
            else:
                got, _ = self.menu_labels(pg, trig.first)
                items += got
            self.shot(pg, "pool-add-open")
            missing = self.missing_labels(items, list(self.catalog))
            wanted = {cli: len(v) for cli, v in self.catalog.items()}
            ok = not missing and items and any(i["text"].startswith("Opus 5.5") for i in items)
            self.row("ac-pool-lists-catalog", f"Add a model on Builder's {where}", True, ok,
                     f"catalog {wanted}; {len(items)} options; missing {len(missing)}: {missing[:12]}; "
                     f"seen {[i['text'] for i in items][:10]}")
        self.guard("ac-pool-lists-catalog", "lists", lists)

        def adds():
            where = self.open_models(pg, "Builder")
            region = self.add_region(pg)
            if not region.count():
                self.row("ac-pool-adds-unused", where, True, False, "no Add a model area")
                return
            provider = self.trigger_named(region, r"provider")
            if provider is not None:
                self.choose(pg, provider, self.cli_label["claude"])
            model = self.trigger_named(region, r"model|runner") or self.triggers(region).first
            picked = self.choose(pg, model, "Opus 5.5")
            effort = self.trigger_named(region, r"effort")
            high = effort is not None and self.choose(pg, effort, "High")
            add = region.get_by_role("button", name=re.compile(r"^Add\b"))
            if picked and add.count():
                add.first.click()
                pg.wait_for_timeout(1500)
            listed = pg.get_by_label("Models Builder may run on").first
            shown = listed.inner_text() if listed.count() else ""
            entry = next((e for e in self.pool_full("Builder")
                          if e.get("model") == "claude-opus-5-5" and e.get("effort") == "high"), None)
            ok = picked and high and "Opus 5.5 · High" in shown and entry is not None
            self.row("ac-pool-adds-unused", f"Opus 5.5 at High on Builder's {where}", True, ok,
                     f"Opus 5.5 offered={picked} High chosen={high}; pool shows {shown[:160]!r}; "
                     f"GET entry={entry}")
            self.shot(pg, "pool-added")
        self.guard("ac-pool-adds-unused", "adds", adds)
        ctx.close()
        self.set_pool("Builder", [{"runner_id": self.ids["haiku"], "default": True}])

    def open_picker(self, pg):
        comp = pg.locator(".conversation-composer-surface")
        trig = comp.locator("button[aria-label^='Model:'], [role=combobox][aria-label^='Model']")
        if not trig.count():
            static = comp.get_by_text("Model:").count()
            return None, f"no model picker in the composer (a static 'Model:' label: {bool(static)})"
        trig.first.click()
        pg.wait_for_timeout(500)
        return self.popup(pg), "ok"

    def picker_row(self, b):
        def run():
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            self.goto(pg, self.url(agent="Builder"))
            pop, why = self.open_picker(pg)
            if pop is None:
                self.row("ac-picker-single-pool", "new chat of Builder (pool of one)", True, False, why)
                ctx.close()
                return
            self.shot(pg, "picker-new-chat")
            items = pop["items"]
            first = items[0] if items else {}
            others = [i for i in items if i["group"] != first.get("group")]
            missing = self.missing_labels(others, list(self.catalog))
            missing = [m for m in missing if m != "Haiku 5.5"]
            footer = re.search(r"this chat only", pop["text"], re.I) is not None
            ok = (bool(first) and "Builder" in first["group"] and first["text"].startswith("Haiku 5.5")
                  and not missing and footer)
            groups = list(dict.fromkeys(i["group"] for i in items))
            self.row("ac-picker-single-pool", "new chat of Builder (pool of one)", True, ok,
                     f"groups {groups}; first {first.get('text')!r} under {first.get('group')!r}; "
                     f"missing {len(missing)}: {missing[:10]}; footer 'this chat only'={footer}")
            ctx.close()
        self.guard("ac-picker-single-pool", "picker", run)

    def chat_rows(self, b):
        haiku45 = next(m["id"] for m in self.catalog["claude"] if m["label"] == "Haiku 4.5")
        codex = "gpt-6-luna" if any(m["id"] == "gpt-6-luna" for m in self.catalog.get("codex", [])) \
            else self.catalog["codex"][0]["id"]
        self.ids["codex_model"] = codex
        conv = None

        def off_pool():
            nonlocal conv
            before = self.pool("Builder")
            code, out, run = self.turn({"message": "Reply with just the word ok.", "overrides": {"model": haiku45}})
            after = self.pool("Builder")
            ok = code == 200 and run is not None and (run[1] or "").startswith("claude-haiku-4-5") and before == after
            self.row("ac-chat-off-pool", "new chat, first turn on Haiku 4.5", True, ok,
                     f"{code} {json.dumps(out)[:300]}; run={run}; pool unchanged={before == after}")
            if code == 200:
                conv = out["conversation_id"]
        self.guard("ac-chat-off-pool", "off pool", off_pool)
        if conv is None:
            # Today's refusal: start the chat on the pool's default so the started-chat rows can
            # still be judged (one extra Haiku 5.5 turn).
            code, out, run = self.turn({"message": "Reply with just the word ok."})
            print(f"  (fallback first turn on the pool default: {code} run={run})", flush=True)
            conv = out.get("conversation_id") if code == 200 else None
        self.ids["chat"] = conv
        reached = conv is not None

        def effort():
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            self.goto(pg, self.url(agent="Builder", conversation=conv), 3000)
            comp = pg.locator(".conversation-composer-surface")
            control = comp.locator("[aria-label^='Effort']")
            if not control.count():
                self.row("ac-effort-changes", "High in the composer's effort control", reached, False,
                         "no effort control in the composer")
                ctx.close()
                return
            chose = self.choose(pg, control.first, "High")
            before = {r[0] for r in self.runs(conv)}
            # The composer's field is a contenteditable textbox, not a textarea.
            box = comp.get_by_test_id("composer-input").first
            box.click()
            pg.keyboard.type("Reply with just the word ok.")
            box.press("Enter")
            pg.wait_for_timeout(1500)
            if not [r for r in self.runs(conv) if r[0] not in before]:
                send = comp.get_by_role("button", name=re.compile("send", re.I))
                if send.count():
                    send.first.click()
            got = self.d.poll(lambda: [r for r in self.runs(conv) if r[0] not in before], 60, 1)
            self.d.wait_idle(self.pid, 6 * 60)
            run = next((r for r in reversed(self.runs(conv)) if r[0] not in before), None)
            ok = chose and got and run is not None and run[2] == "high"
            self.row("ac-effort-changes", "High in the composer's effort control, second turn", reached, ok,
                     f"High chosen={chose}; run={run}")
            ctx.close()
        if reached:
            self.guard("ac-effort-changes", "effort", effort)

        def switch():
            before = self.pool("Builder")
            code, out, run = self.turn({"message": "Reply with just the word ok.",
                                        "overrides": {"model": "claude-sonnet-5-5"}}, conv)
            after = self.pool("Builder")
            ok = code == 200 and run is not None and run[1] == "claude-sonnet-5-5" and before == after
            self.row("ac-switch-same-cli", "started Claude chat, next turn on Sonnet 5.5", reached, ok,
                     f"{code} {json.dumps(out)[:300]}; run={run}; pool unchanged={before == after}")
        if reached:
            self.guard("ac-switch-same-cli", "switch", switch)

        def other_cli():
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            self.goto(pg, self.url(agent="Builder", conversation=conv), 3000)
            pop, why = self.open_picker(pg)
            codex_items = []
            if pop is not None:
                self.shot(pg, "picker-started-chat")
                names = set(self.labels("codex"))
                codex_items = [i for i in pop["items"] if i["text"] in names]
                self.close_popup(pg)
            ui_ok = bool(codex_items) and all(i["disabled"] and re.search(r"new chat", i["all"], re.I)
                                             for i in codex_items)
            code, out = self.trigger({"conversation_id": conv, "message": "Reply with just the word ok.",
                                      "overrides": {"model": codex}})
            api_ok = 400 <= code < 500 and "Claude Code" in json.dumps(out)
            self.row("ac-other-cli-refused", "started Claude chat: Codex in the picker, and a Codex turn",
                     reached, ui_ok and api_ok,
                     f"picker: {why}; codex options {len(codex_items)}/{len(self.labels('codex'))} "
                     f"all not choosable saying new chat={ui_ok}; turn {code} {json.dumps(out)[:300]}")
            ctx.close()
        if reached:
            self.guard("ac-other-cli-refused", "other cli", other_cli)

        def other_provider():
            code, out = self.trigger({"message": "Reply with just the word ok.", "overrides": {"model": codex}})
            text = json.dumps(out)
            pool_refusal = re.search(r"may run on|not among|pool", text, re.I) is not None
            ok = code == 200 or (not pool_refusal and re.search(r"unavailable|not installed|not found on|"
                                                                  r"cannot start|not available", text, re.I))
            self.row("ac-chat-other-provider", f"new chat, first turn on {codex}", True, bool(ok),
                     f"{code} {text[:300]}")
            if code == 200:
                self.d.wait_idle(self.pid, 4 * 60)
                r = self.runs(out["conversation_id"])
                print(f"  (Codex chat run: {r})", flush=True)
        self.guard("ac-chat-other-provider", "other provider", other_provider)

    def no_leak_row(self):
        def run():
            task = self.ids["task"]
            chat = self.ids.get("chat")
            stored = self.d.ro("select runtime_overrides from conversations where id=?", (chat,)) if chat else []
            code, out = self.api("POST", f"/projects/{self.pid}/jobs/{self.ids['job']}/run")
            started = self.d.poll(lambda: self.runs(task=task), 90, 2)
            self.d.wait_idle(self.pid, 8 * 60)
            flow_runs = self.runs(task=task)
            # The same task, started by the operator inside the chat whose override is stored.
            c2, o2 = self.trigger({"conversation_id": chat, "task_id": task,
                                   "message": "Reply with just the word ok. Change no file."})
            if c2 == 200:
                self.d.poll(lambda: len(self.runs(task=task)) > len(flow_runs), 60, 1)
                self.d.wait_idle(self.pid, 6 * 60)
            all_runs = self.runs(task=task)
            models = [r[1] for r in all_runs]
            ok = started and bool(models) and all(m == "claude-haiku-5-5" for m in models)
            self.row("ac-no-leak", "Builder's builder run after a Haiku 4.5 chat", True, ok,
                     f"chat override stored {stored}; job fired {code}; task runs {all_runs}; "
                     f"operator task turn in the chat {c2} {json.dumps(o2)[:200]}")
        self.guard("ac-no-leak", "no leak", run)

    def index_rows(self, b):
        held, _ = self.d.hold(self.pid, "Builder")
        con = __import__("sqlite3").connect(self.d.DB.as_posix(), timeout=30)
        con.execute("update runs set task_id=? where id=?", (self.ids["task"], held))
        con.commit()
        con.close()
        try:
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()

            def lists():
                found, after, tabs = self.open_profiles_tab(pg)
                if not found:
                    self.row("ac-index-lists", "the Profiles tab", True, False, f"no Profiles tab; top bar {tabs}")
                    return
                self.shot(pg, "profiles-index")
                rows = pg.evaluate("""() => [...document.querySelectorAll('[data-slot=profile-row]')].map(r => ({
                    name: r.getAttribute('data-profile'), text: r.innerText.replace(/\\n/g, ' | '),
                    status: (r.querySelector('.aw-pf-status') || {}).innerText || '',
                    archived: !!r.closest('[data-archived=true]')}))""")
                names = [r["name"] for r in rows if not r["archived"]]
                toggle = pg.locator("[data-slot=archived-toggle]")
                arch = toggle.inner_text() if toggle.count() else ""
                collapsed = toggle.count() and toggle.first.get_attribute("aria-expanded") == "false"
                want = ["Builder", "QA", "Scout"]
                statuses = {r["name"]: r["status"] for r in rows}
                bad = []
                if not after:
                    bad.append(f"Profiles is not right after Tasks: {tabs}")
                if names != want:
                    bad.append(f"order {names} != {want}")
                if not statuses.get("Builder", "").startswith("Working"):
                    bad.append(f"Builder reads {statuses.get('Builder')!r}")
                if statuses.get("QA") != "Idle":
                    bad.append(f"QA reads {statuses.get('QA')!r}")
                if statuses.get("Scout") != "No model":
                    bad.append(f"Scout reads {statuses.get('Scout')!r}")
                if not (collapsed and re.search(r"Archived\s*1", arch)):
                    bad.append(f"archived group {arch!r} collapsed={collapsed}")
                for r in rows:
                    if r["name"] == "Builder" and "Haiku 5.5" not in r["text"]:
                        bad.append("Builder's row has no model")
                self.row("ac-index-lists", "Profiles tab with working, idle, no-model, archived", True, not bad,
                         "; ".join(bad) or f"rows {rows}")
            self.guard("ac-index-lists", "index", lists)

            def page_now():
                if not self.open_profile_page(pg, "Builder"):
                    self.row("ac-page-now", "Builder's page while on its build task", True, False, "no profile page")
                    return
                now = pg.locator("section[aria-label=Now]")
                text = now.inner_text() if now.count() else ""
                bad = [] if self.ids["task_title"] in text else [f"Now strip {text[:120]!r}"]
                link = now.locator("[data-slot=open-task]")
                if link.count():
                    link.first.click()
                    pg.wait_for_timeout(1500)
                    if self.ids["task"] not in pg.url and self.ids["task_readable"] not in pg.url and \
                            not pg.get_by_text(self.ids["task_title"]).count():
                        bad.append(f"Open task led to {pg.url}")
                else:
                    bad.append("no Open task")
                self.open_profile_page(pg, "Builder")
                link = pg.locator("section[aria-label=Now] [data-slot=open-build]")
                if link.count():
                    link.first.click()
                    pg.wait_for_timeout(1500)
                    if self.ids["build"] not in pg.url:
                        bad.append(f"Open build led to {pg.url}")
                else:
                    bad.append("no Open build")
                self.row("ac-page-now", "Builder's page while on its build task", True, not bad, "; ".join(bad) or "ok")
            self.guard("ac-page-now", "now", page_now)
            ctx.close()
        finally:
            self.d.release(held)

    def index_states_row(self, b):
        def run():
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            bad = []
            found, _, tabs = self.open_profiles_tab(pg, self.empty)
            if not found:
                self.row("ac-index-states", "three states", True, False, f"no Profiles tab; top bar {tabs}")
                ctx.close()
                return
            empty = pg.get_by_test_id("profiles-empty")
            if not (empty.count() and empty.get_by_role("button", name="Add a builder and a checker").count()
                    and empty.get_by_role("button", name=re.compile("Add profile")).count()):
                bad.append("no profiles: no empty state offering both")
            self.shot(pg, "profiles-empty")
            self.open_profiles_tab(pg)
            pg.get_by_label("Filter profiles").fill("zzzz-nothing")
            pg.wait_for_timeout(500)
            if not pg.get_by_role("button", name="Clear filter").count():
                bad.append("filter matching none: no Clear filter")
            pg.route(re.compile(r".*/api/v1/projects/[^/]+/agents(\?.*)?$"),
                     lambda route: route.fulfill(status=500, body="drive: agents fail"))
            self.open_profiles_tab(pg)
            pg.wait_for_timeout(2500)
            if not pg.get_by_role("alert").get_by_role("button", name="Retry").count():
                bad.append("failed load: no Retry")
            self.row("ac-index-states", "no profiles / filter none / agents route fails", True, not bad,
                     "; ".join(bad) or "ok")
            ctx.close()
        self.guard("ac-index-states", "states", run)

    def page_row(self, b):
        def run():
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            if not self.open_profile_page(pg, "Builder", "Models"):
                self.row("ac-page-addressable", "Builder's page on Models", True, False, "no profile page with a Models tab")
                ctx.close()
                return
            bad = []
            address = pg.url
            self.shot(pg, "profile-models")
            pg.reload()
            pg.wait_for_timeout(2500)
            ok, why = self.on_profile_page(pg, "Builder", "Models")
            if not ok:
                bad.append(f"reload: {why}")
            other = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
            self.goto(other, address)
            ok, why = self.on_profile_page(other, "Builder", "Models")
            if not ok:
                bad.append(f"new window: {why}")
            other.context.close()
            groups = pg.locator("[data-testid=profile-page] [role=radiogroup]").count()
            navs = pg.locator("[data-testid=profile-page] nav, [data-testid=profile-page] [role=tablist], "
                              "[data-testid=profile-page] [role=navigation]").count()
            if groups != 1 or navs:
                bad.append(f"{groups} rows of tabs, {navs} other navigation")
            pg.get_by_label("Builder. Switch profile").click()
            pg.wait_for_timeout(400)
            pg.get_by_role("menuitem", name=re.compile("^QA")).first.click()
            pg.wait_for_timeout(1200)
            ok, why = self.on_profile_page(pg, "QA")
            if not ok:
                bad.append(f"switch to QA: {why}")
            self.open_profile_page(pg, "Builder")
            pg.locator("[data-testid=profile-page]").click(position={"x": 5, "y": 5})
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(800)
            focus = pg.evaluate(FOCUS)
            if pg.get_by_test_id("profile-page").count() or (focus or {}).get("profile") != "Builder":
                bad.append(f"Escape: focus {focus}")
            self.row("ac-page-addressable", "reload, new window, switcher, Escape, one tab row", True, not bad,
                     "; ".join(bad) or f"ok at {address}")
            ctx.close()
        self.guard("ac-page-addressable", "page", run)

    def one_home_row(self, b):
        def run():
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            bad = []
            self.goto(pg, self.url(agent="Builder", conversation=self.ids["chat"]), 3000)
            pg.get_by_test_id("conversation-more").click()
            pg.wait_for_timeout(300)
            pg.get_by_role("menuitem", name="Builder settings").first.click()
            pg.wait_for_timeout(1500)
            ok, why = self.on_profile_page(pg, "Builder")
            if not ok:
                bad.append(f"⋯ Builder settings -> {pg.url.split('?')[-1]} ({why})")
            self.goto(pg, self.url())
            pg.keyboard.press("Control+k")
            pg.wait_for_timeout(500)
            pg.keyboard.type("Builder settings")
            pg.wait_for_timeout(600)
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(1500)
            ok, why = self.on_profile_page(pg, "Builder")
            if not ok:
                bad.append(f"palette -> {pg.url.split('?')[-1]} ({why})")
            self.goto(pg, self.url())
            pg.get_by_test_id("agent-details-toggle-Builder").click()
            pg.get_by_text("Profile settings").first.click()
            pg.wait_for_timeout(1500)
            ok, why = self.on_profile_page(pg, "Builder")
            if not ok:
                bad.append(f"Overview Details -> {pg.url.split('?')[-1]} ({why})")
            self.row("ac-one-home", "⋯ menu, palette, Overview Details", True, not bad, "; ".join(bad) or "ok")
            ctx.close()
        self.guard("ac-one-home", "one home", run)

    def names_row(self, b):
        def run():
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            bad = []

            def follow(where, scope):
                link = scope.get_by_role("link", name=PROFILE_LINK)
                if not link.count():
                    bad.append(f"{where}: no 'Open Builder's profile' link")
                    return
                link.first.focus()
                pg.keyboard.press("Enter")
                pg.wait_for_timeout(1500)
                ok, why = self.on_profile_page(pg, "Builder")
                if not ok:
                    bad.append(f"{where}: {why}")

            self.goto(pg, self.url(agent="Builder", conversation=self.ids["chat"]), 3000)
            follow("thread bar", pg.get_by_test_id("conversation-header"))
            def open_board():
                # The task may be approved by now (QA reviews it once Builder finishes), and the
                # board hides finished tasks until asked: show them, so the card is there to read.
                self.goto(pg, self.url(tab="tasks"), 3000)
                finished = pg.get_by_test_id("board-show-finished")
                if finished.count() and not finished.first.is_checked():
                    finished.first.check(force=True)
                    pg.wait_for_timeout(600)

            open_board()
            card = pg.locator("[data-testid^=task-card], article, li").filter(has_text=self.ids["task_title"]).first
            follow("task card", card)
            open_board()
            pg.get_by_text(self.ids["task_title"]).first.click()
            pg.wait_for_timeout(1500)
            follow("task story", pg.locator("[role=dialog], main").last)
            self.goto(pg, self.url(tab="spec", view="build", focus=self.ids["build"]), 3000)
            follow("build page", pg.locator("main").first if pg.locator("main").count() else pg)
            self.goto(pg, self.url())
            row = pg.get_by_label(re.compile(r"^Open Builder, ")).first
            follow("Overview row", row.locator("xpath=ancestor::*[self::li or self::div][1]"))
            self.goto(pg, self.url())
            settings = pg.get_by_role("button", name="Builder settings")
            if settings.count():
                settings.first.click()
                pg.wait_for_timeout(1500)
                ok, why = self.on_profile_page(pg, "Builder")
                if not ok:
                    bad.append(f"Overview 'Builder settings': {why}")
            else:
                bad.append("Overview: no 'Builder settings' control")
            self.goto(pg, self.url())
            pg.get_by_label(re.compile(r"^Open Builder, ")).first.click()
            pg.wait_for_timeout(1500)
            if "agent=Builder" not in pg.url or pg.get_by_test_id("profile-page").count():
                bad.append(f"Overview row click -> {pg.url.split('?')[-1]}")
            self.row("ac-names-link", "thread bar, task card, story, build page, Overview", True, not bad,
                     "; ".join(bad) or "ok")
            ctx.close()
        self.guard("ac-names-link", "names", run)

    def open_create_dialog(self, pg, pid):
        """Create profile: the Profiles index's Add profile, or today's rail action."""
        found, _, _ = self.open_profiles_tab(pg, pid)
        btn = pg.get_by_role("button", name=re.compile(r"^Add profile$"))
        if not (found and btn.count()):
            self.goto(pg, self.url(pid))
            btn = pg.get_by_label(re.compile(r"^Add profile to "))
        btn.first.click()
        pg.wait_for_timeout(800)
        return pg.locator("[role=dialog]").last

    def open_setup_dialog(self, pg):
        found, _, _ = self.open_profiles_tab(pg, self.empty)
        btn = pg.get_by_role("button", name="Add a builder and a checker", exact=True)
        if not (found and btn.count()):
            self.goto(pg, self.url(self.empty))
            # Today's way in: the Overview's setup item for profiles ("Add both…").
            btn = pg.locator("button, a, [role=button]").filter(has_text=re.compile(r"builder and a checker|^Add both"))
        if not btn.count():
            return None
        btn.first.click()
        pg.wait_for_timeout(800)
        return pg.locator("[role=dialog]").last

    def inspect_dialog(self, pg, dialog, which):
        bad = []
        selects = dialog.locator("select").count()
        if selects:
            bad.append(f"{which}: {selects} native <select>")
        scope = dialog.locator("[data-testid=setup-profiles-builder]")
        scope = scope if scope.count() else dialog
        provider = self.trigger_named(scope, r"provider")
        if provider is None:
            bad.append(f"{which}: no provider control")
            return bad
        for cli in ("claude", "codex", "copilot"):
            if not self.choose(pg, provider, self.cli_label[cli]):
                bad.append(f"{which}: provider {self.cli_label[cli]} not offered")
                continue
            if not provider.locator("svg, img, [data-slot=provider-mark]").count():
                bad.append(f"{which}: no provider mark on {cli}")
            model = self.trigger_named(scope, r"model")
            if model is None:
                bad.append(f"{which}: no themed model control on {cli}")
                continue
            items, _ = self.menu_labels(pg, model)
            missing = self.missing_labels(items, [cli])
            if missing:
                bad.append(f"{which}/{cli}: {len(missing)} catalog models missing, e.g. {missing[:4]}")
            name = scope.locator("input").first
            ph = (name.get_attribute("placeholder") or "") if name.count() else ""
            if cli not in ph.lower():
                bad.append(f"{which}/{cli}: name placeholder {ph!r}")
        return bad

    def dialog_rows(self, b):
        def themed():
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            bad = []
            dialog = self.open_create_dialog(pg, self.empty)
            if dialog.count():
                self.shot(pg, "dialog-create-profile")
                bad += self.inspect_dialog(pg, dialog, "Create profile")
            else:
                bad.append("Create profile did not open")
            pg.keyboard.press("Escape")
            dialog = self.open_setup_dialog(pg)
            if dialog is not None and dialog.count():
                self.shot(pg, "dialog-setup-pair")
                bad += self.inspect_dialog(pg, dialog, "Add a builder and a checker")
            else:
                bad.append("Add a builder and a checker did not open")
            self.row("ac-dialogs-themed", "both creation dialogs, provider Claude/Codex/Copilot", True, not bad,
                     "; ".join(bad) or "ok")
            ctx.close()
        self.guard("ac-dialogs-themed", "dialogs", themed)

        def setup_unused():
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            dialog = self.open_setup_dialog(pg)
            if dialog is None or not dialog.count():
                self.row("ac-setup-unused-model", "Add a builder and a checker", True, False, "the dialog did not open")
                ctx.close()
                return
            bad = []
            for role, label in (("builder", "Opus 5.5"), ("checker", "Sonnet 5.5")):
                scope = dialog.locator(f"[data-testid=setup-profiles-{role}]")
                scope = scope if scope.count() else dialog
                provider = self.trigger_named(scope, r"provider")
                if provider is not None:
                    self.choose(pg, provider, self.cli_label["claude"])
                model = self.trigger_named(scope, r"model|runner")
                if model is None or not self.choose(pg, model, label):
                    bad.append(f"{role}: {label} not offered")
            names = {}
            for role in ("builder", "checker"):
                scope = dialog.locator(f"[data-testid=setup-profiles-{role}] input").first
                names[role] = scope.input_value() if scope.count() else None
            if not bad:
                dialog.get_by_role("button", name="Create both").click()
                pg.wait_for_timeout(2500)
                for role, model in (("builder", "claude-opus-5-5"), ("checker", "claude-sonnet-5-5")):
                    pool = self.pool_full(names[role] or "", self.empty)
                    default = next((e for e in pool if e.get("default")), None)
                    if not default or default.get("model") != model:
                        bad.append(f"{role} {names[role]}: pool default {default}")
            self.row("ac-setup-unused-model", "builder on Opus 5.5, checker on Sonnet 5.5", True, not bad,
                     "; ".join(bad) or f"created {names}")
            ctx.close()
        self.guard("ac-setup-unused-model", "setup", setup_unused)

    def screenshots(self, b):
        """ac-screens-reviewed: the operator's shots, dark, light and narrow."""
        if not self.shots:
            return
        for theme, width in (("dark", 1440), ("light", 1440), ("narrow", 760)):
            ctx = b.new_context(viewport={"width": width, "height": 900})
            pg = ctx.new_page()
            if theme == "light":
                self.goto(pg, self.url(), 1500)
                t = pg.get_by_role("button", name="Switch to light mode")
                if t.count():
                    t.first.click()
            if self.open_profiles_tab(pg)[0]:
                self.shot(pg, f"index-{theme}")
                for section in ("Profile", "Models", "Permissions", "Checkpoints", "Workspace"):
                    if self.open_profile_page(pg, "Builder", section):
                        self.shot(pg, f"page-{section.lower()}-{theme}")
            self.goto(pg, self.url(agent="Builder"))
            if self.open_picker(pg)[0] is not None:
                self.shot(pg, f"picker-new-{theme}")
            self.goto(pg, self.url(agent="Builder", conversation=self.ids["chat"]))
            if self.open_picker(pg)[0] is not None:
                self.shot(pg, f"picker-started-{theme}")
            ctx.close()

    CRITERIA = ("ac-pool-lists-catalog", "ac-pool-adds-unused", "ac-api-reuse", "ac-api-unknown",
                "ac-picker-single-pool", "ac-chat-off-pool", "ac-chat-other-provider", "ac-switch-same-cli",
                "ac-other-cli-refused", "ac-effort-changes", "ac-no-leak", "ac-index-lists", "ac-index-states",
                "ac-page-addressable", "ac-page-now", "ac-one-home", "ac-names-link", "ac-dialogs-themed",
                "ac-setup-unused-model")

    def report(self):
        failed = False
        print("\nverdict, one line per check:")
        for crit in self.CRITERIA:
            rows = self.rows.get(crit, [])
            reached = bool(rows) and all(r[1] for r in rows)
            ok = reached and all(r[2] for r in rows)
            failed |= not ok
            worst = next((r for r in rows if not r[2]), None)
            detail = f"{worst[0]}: {worst[3]}" if worst else f"{len(rows)} rows pass"
            print(f"check {crit}: reached={'yes' if reached else 'no'} "
                  f"failed_at_assertion={'yes' if reached and not ok else 'no'} -- {str(detail)[:500]}")
        print("check ac-screens-reviewed: operator -- shots in", SHOTS if self.shots else "(run with --shots)")
        print("RESULT:", "FAIL" if failed else "PASS")
        return 1 if failed else 0


DOC = "spec/changes/pool-drive/spec.json"
TASK_TITLE = "Add pool.txt"


def doc_payload():
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Pool drive",
        "summary": "The repository says pool.", "problem": "The repository has no pool.txt.",
        "scope": {"in_scope": ["pool.txt"], "non_goals": ["Anything else"]},
        "requirements": [{"key": "pool", "modal": "MUST", "statement": "The repository MUST hold pool.txt."}],
        "acceptance_criteria": [{"key": "says-pool", "requirement": "pool", "given": "the repository",
                                 "when": "pool.txt is read", "then": "it reads pool",
                                 "how_to_check": "cat pool.txt", "checked_by": "agent"}],
        "tasks": [{"key": "t1", "title": TASK_TITLE, "requirements": ["pool"], "files": ["pool.txt"],
                   "description": "Reply with just the word ok and change no file: this is a drive.",
                   "builder": "Builder", "reviewer": "QA"}],
        "delivery": {"mode": "flow", "driver": "flow", "agent": "Builder", "builders": ["Builder"],
                     "level": "reviewed", "landing": "main", "stop_when_queue_empties": True,
                     "cron": "0 0 1 1 *", "reasons": {"mode": "One task.", "agent": "Builder."}},
    }


def setup_hub():
    """A fresh drive Hub and the two scratch projects the module docstring describes."""
    import d1029_build_plan_in_spec as d

    d.TMP = d.TMP.parent.parent / "drive1121-pool-assert" / d.STAMP
    if os.environ.get("AW_HUB"):
        d.HUB, d.KEY, d.DB = os.environ["AW_HUB"].rstrip("/"), os.environ["AW_KEY"], pathlib.Path(os.environ["AW_DB"])
        proc = None
    else:
        d.PORT = int(os.environ.get("AW_DRIVE_PORT") or 8037)
        if d.PORT in (8000, 8010):
            sys.exit("never the operator's or the trial Hub")
        d.HUB, d.KEY, d.DB = f"http://127.0.0.1:{d.PORT}", "aw_live_" + secrets.token_hex(16), d.TMP / "agentweave.db"
        proc = d.start_hub()
    try:
        return (d, proc) + _setup_projects(d)
    except BaseException:
        d.stop_hub(proc)
        raise


def _setup_projects(d):
    ids = {}
    projects = {}
    for name in ("pooldrive", "pooldrive-empty"):
        root = d.TMP / name
        root.mkdir(parents=True, exist_ok=True)
        d.git(root, "init", "-q", "-b", "main")
        (root / "README.md").write_text("Scratch.\n", encoding="utf-8")
        (root / ".gitignore").write_text(".agentweave/\n", encoding="utf-8")
        d.git(root, "add", ".")
        d.git(root, "commit", "-q", "-m", "seed")
        code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"{name}-{d.STAMP}"})
        d.check(f"setup: project {name} opens", code in (200, 201), f"{code} {project}", fatal=True)
        projects[name] = (project["id"], root)
        d.api("PATCH", f"/projects/{project['id']}", {"main_branch": "main"})
    pid, root = projects["pooldrive"]
    empty, _ = projects["pooldrive-empty"]
    base = f"/projects/{pid}"
    _, agents = d.api("GET", f"/projects/{empty}/agents")
    d.check("setup: the empty project has no profiles", agents == [], str(agents), fatal=True)
    code, haiku = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": "claude-haiku-5-5"})
    d.check("setup: a Haiku 5.5 runner", code in (200, 201), f"{code} {haiku}", fatal=True)
    ids["haiku"] = haiku["id"]
    for name in ("Builder", "QA", "Scout", "Old"):
        code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": haiku["id"]})
        d.check(f"setup: profile {name}", code in (200, 201), f"{code} {out}", fatal=True)
    code, out = d.api("PATCH", f"{base}/agents/Scout", {"pool": []})
    d.check("setup: Scout has no model", code == 200, f"{code} {str(out)[:200]}", fatal=True)
    code, out = d.api("POST", f"{base}/agents/Old/archive", {})
    d.check("setup: Old is archived", code in (200, 201), f"{code} {str(out)[:200]}", fatal=True)

    quoted = urllib.parse.quote(DOC)
    code, out = d.api("POST", f"{base}/project/documents", {"title": "Pool drive", "kind": "change-spec", "path": DOC})
    d.check("setup: the document is created", code == 201, f"{code} {out}", fatal=True)
    code, out = d.api("PUT", f"{base}/project/documents/{DOC}/content", {"document": doc_payload()})
    d.check("setup: the document saves", code == 200, f"{code} {str(out)[:400]}", fatal=True)
    code, out = d.as_agent(pid, "QA", "POST", "/spec/documents/confirm-criteria", {
        "path": DOC, "confirmations": [{"criterion": "says-pool", "kind": "new"}]})
    d.check("setup: the criterion is confirmed", code == 200, f"{code} {str(out)[:300]}", fatal=True)
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    version = read.get("content_version") if isinstance(read, dict) else None
    code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                      {"reason": "drive", "approve_anyway": True, "content_version": version})
    d.check("setup: the document is approved", code == 200, f"{code} {str(out)[:400]}", fatal=True)
    code, out = d.api("POST", f"{base}/project/documents/build?path={quoted}",
                      {"driver": "flow", "level": "reviewed", "builders": ["Builder"], "landing": "main"})
    d.check("setup: built as a flow", code == 200, f"{code} {str(out)[:400]}", fatal=True)
    ids["build"] = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
    (doc_id,) = d.ro("select id from spec_documents where project_id=? and path=?", (pid, DOC))[0]
    task, loop, readable = d.ro("select id, loop_id, readable_id from tasks where spec_document_id=?", (doc_id,))[0]
    ids.update(task=task, task_readable=readable or task, task_title=TASK_TITLE,
               job=d.ro("select job_id from loops where id=?", (loop,))[0][0])
    d.check("setup: Builder has a task in a running build", bool(ids["build"] and ids["job"]), str(ids), fatal=True)
    return pid, empty, root, ids


def run_assert():
    shots = None
    if "--shots" in sys.argv:
        shots = sys.argv[sys.argv.index("--shots") + 1]
        os.makedirs(SHOTS, exist_ok=True)
    d, proc, pid, empty, root, ids = setup_hub()
    drive = Drive(d, pid, empty, root, shots)
    drive.ids.update(ids)
    try:
        _, cat = d.api("GET", "/model-catalog")
        for p in cat["providers"]:
            drive.catalog[p["provider"]] = [{"id": m["id"], "label": m.get("label") or m["id"]} for m in p["models"]]
            drive.cli_label[p["provider"]] = p.get("label") or p["provider"]
        print("catalog:", {k: len(v) for k, v in drive.catalog.items()}, drive.cli_label, flush=True)
        print(f"Hub {d.HUB}, project {pid}, empty project {empty}, ids {ids}", flush=True)
        drive.api_rows()
        with sync_playwright() as p:
            b = p.chromium.launch()
            drive.pool_ui_rows(b)
            drive.picker_row(b)
            drive.chat_rows(b)
            drive.no_leak_row()
            drive.index_rows(b)
            drive.index_states_row(b)
            drive.page_row(b)
            drive.one_home_row(b)
            drive.names_row(b)
            drive.dialog_rows(b)
            drive.screenshots(b)
            b.close()
    finally:
        print(f"(artefacts: {d.TMP}; finished {datetime.datetime.now():%H:%M:%S})", flush=True)
        d.stop_hub(proc)
    return drive.report()


def observe():
    from aw import api

    pid = os.environ["AW_PROJECT"]
    s = SHOTS + "/"
    u = f"{os.environ['AW_HUB']}/?project={pid}"
    print("model catalog:")
    _, cat = api("GET", "/model-catalog")
    for p in cat["providers"]:
        print(" ", p["provider"], len(p["models"]), "models;", {c["id"]: [v["id"] for v in c["values"]] for c in p["controls"]})
    _, runners = api("GET", f"/projects/{pid}/runners")
    print("runners:", [(r["name"], r["cli"], r["model"]) for r in runners])

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
        pg.goto(u + "&agent=Builder&settings=running")
        pg.wait_for_timeout(2500)
        print("Manage runners / Add a runner links:", pg.get_by_text("Manage runners").count(), pg.get_by_text("Add a runner").count())
        pg.get_by_label("Runner to add to Builder").click()
        pg.wait_for_timeout(500)
        print("Add a model lists:", pg.evaluate(POP))
        pg.screenshot(path=s + "13_pool_add_runner_open.png")
        pg.goto(u + "&agent=Builder")
        pg.wait_for_timeout(2500)
        pg.get_by_text("Model:").first.click()
        pg.wait_for_timeout(500)
        print("composer picker:", pg.evaluate(POP))
        pg.goto(u)
        pg.wait_for_timeout(2500)
        pg.get_by_label("Open Builder, Idle").click()
        pg.wait_for_timeout(1000)
        print("Overview row click ->", pg.url.split("//")[1])
        pg.goto(u)
        pg.wait_for_timeout(2500)
        pg.get_by_test_id("agent-details-toggle-Builder").click()
        pg.get_by_text("Profile settings").first.click()
        pg.wait_for_timeout(1000)
        print("Overview Details -> Profile settings ->", pg.url.split("//")[1])
        pg.goto(u)
        pg.wait_for_timeout(2500)
        pg.get_by_role("button", name="no charter").first.click()
        pg.wait_for_timeout(1000)
        print("Overview 'no charter' chip ->", pg.url.split("//")[1])
        pg.goto(u)
        pg.wait_for_timeout(2500)
        pg.get_by_label("Add profile to pooldrive").click()
        pg.wait_for_timeout(600)
        print("Create profile: native selects =", pg.locator("[role=dialog] select").count(),
              "| placeholder =", pg.locator("[role=dialog] input").first.get_attribute("placeholder"))

    for label, ov in [("off-pool model", {"model": "claude-opus-5-5"}), ("off-pool runner", {"runner_id": "runner-x"})]:
        c, body = api("POST", f"/projects/{pid}/agent/trigger", {"agent": "Builder", "message": "Reply with just the word ok.", "overrides": ov})
        print(label, "->", c, json.dumps(body))


if __name__ == "__main__":
    if "--assert" in sys.argv:
        sys.exit(run_assert())
    observe()
