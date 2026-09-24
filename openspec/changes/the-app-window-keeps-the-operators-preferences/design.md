# Design — the app window keeps the operator's preferences

## Operator review, 2026-09-24

The adversarial Opus review (`spec-queue/tracks/reviews/B11-2026-09-24.md`, section 2) found this
change **APPROVE WITH FIXES**. What changed here because of it:

- **One window folder per profile, and reset clears it** (the operator's decision on the review's
  LOW finding). R1's `HUB_DIR / "window"` was shared by every `--profile`, and `agentweave reset
  --profile x` left it behind. D1 now puts the folder inside the profile's own data directory, and
  D4 says how reset clears it.
- **R2 and R3 are copied into the round log below** (the review's MEDIUM process finding). They had
  been recorded only at bundle level (`spec-queue/tracks/B11.md`, R2 at `:423`, R3 at `:584`).
- **The pywebview 5.0 check is recorded** in the round log. The review checked the wheel; this pass
  repeated it and found one more thing (D5).
- **"Two app windows at once"** is in the human test guide.

**Built on the recommended answer to B11's F385 question** (ROUNDS.md D13, *"pywebview private
mode"*): **persist the window's profile, and let an unset appearance follow the system.** If the
operator answers only the first half, drop D2 and its requirement; if only the second, drop D1, D4
and their requirement. The halves are independent (F385's own text says so).

## Context — measured on `ce086b6`, re-verified on `09127ba`

| Fact | Where |
|---|---|
| Window opened with no profile arguments | `src/agentweave/cli.py:1025-1027` |
| `_open_app_window_native(url)` takes no profile. Its four callers: `_hub_native_start` (`:1077`, `:1195`; `profile` is a parameter, `:1049`) and `cmd_hub_start`'s Docker path (`:1270`, `:1363`; `profile` is a local, `:1229`) | `cli.py:1008` |
| A profile's data directory: `HUB_DIR/data` for the default, `HUB_DIR/profiles/<name>` for a named one | `cli.py:641-650` `_hub_profile_data_dir` |
| The Hub reaches that directory only through the database file in it | `cli.py:1089-1091` (`db_path = data_dir / "agentweave.db"`) |
| `reset` removes exactly that directory with `rmtree(..., ignore_errors=True)`, then prints `Deleted …` whether or not it went | `cli.py:1368-1451` (`data_dir` at `:1380`, rmtree at `:1433-1435`) |
| Existing reset tests: one profile only; bare reset never sweeps `profiles/` | `tests/test_hub_commands.py:649`, `:671` |
| `start(... private_mode=True, storage_path=None ...)` is pywebview's default | `inspect.signature(webview.start)` on pywebview 6.2.1, this machine; the same on the 5.0 wheel (round log) |
| The extra allows any pywebview from 5.0 | `pyproject.toml:67` `app = ["pywebview>=5.0"]` |
| The CLI already names the Hub's home | `cli.py:242` `HUB_DIR = Path.home() / ".agentweave" / "hub"` |
| Unset mode resolves to light | `hub/ui/src/store/configStore.ts:49` |
| The credential lives in `sessionStorage`, not `localStorage` | `configStore.ts:37-40` (`SESSION_STORAGE_KEY`) |
| The page's first paint is `data-mode="dark"` before the store applies a mode | `hub/ui/index.html:2`; applied at `App.tsx:150` |
| `index.html` is served with no validators, so a persistent HTTP cache cannot hold a stale page | `hub/hub/main.py:573-579` returns `HTMLResponse(... read_text())`, no `ETag` or `Last-Modified`; hashed `/assets` are immutable by name |
| The CLI tests stub `webview` for every test by default | `tests/conftest.py:33-42` |
| The native-window test builds a fake `start` that keeps only `icon` | `tests/test_cli.py:305-309` |

## D1 — A profile on disk, one per Hub profile, under the product's own home

```python
def _hub_profile_window_dir(profile: str = "default") -> Path:
    return _hub_profile_data_dir(profile) / "window"

def _open_app_window_native(url: str, profile: str = "default") -> bool:
    ...
    webview.start(
        icon=_app_icon_path(),
        private_mode=False,
        storage_path=str(_hub_profile_window_dir(profile)),
    )
```

The default profile's window folder is `~/.agentweave/hub/data/window`; a named profile's is
`~/.agentweave/hub/profiles/<name>/window`. All four callers pass the `profile` they already hold.

- **Why inside the profile's data directory, not a sibling `HUB_DIR / "window" / <profile>`.** The
  data directory is already the unit that `--profile` separates and that `reset` destroys
  (`app-lifecycle` *"A named profile selects a separate, deliberate instance"*). A folder inside it
  is separated and reset by the same code, so a later change to either cannot miss the window. A
  sibling tree would need its own resolver and its own line in `reset`, and a `reset` that forgot it
  would be silent. The Hub sees that directory only through the database file in it, so a subfolder
  beside `agentweave.db` changes nothing the Hub reads.
- **An explicit `DATABASE_URL`** moves the database, not the window folder: the window stays with
  the profile named on the command line, as the PID file does.
- **Why an explicit `storage_path`.** With `private_mode=False` alone, the backend picks a location
  of its own. The product should be able to name where its state is, both for the operator and for
  the reset button `R4` asks for, and so that `reset` clears it (D4).
- **What persists that did not.** Everything the Proposal lists. The most valuable is not the theme:
  it is the unsent composer draft, which `agent-conversation-workspace` *"Unsent composer text
  survives navigation and reload"* already protects within a session and which a window close
  destroys today.
- **What does not persist.** `sessionStorage` is per window session under either setting, so the
  session credential still does not outlive the window.
- **Stale pages.** A persistent profile keeps an HTTP cache. `index.html` carries no validators and
  is re-fetched, and the assets it names are content-hashed, so a rebuilt bundle still reaches the
  window on its next load (the property CLAUDE.md relies on for `:8000`).
- **Two Hubs.** Each profile has its own folder, and origins also differ by port (`:8000`, `:8010`),
  so two windows' storage does not mix.
- **Two windows of one profile.** Running `agentweave --app` twice against one profile opens two
  windows on one folder. WebView2 lets a second process share a user data folder when the
  environment options match, and pywebview passes the same ones, so it is expected to open; if a
  backend refuses, the failure path below applies. Nothing automated drives a real WebView2, so the
  human guide checks it (task 3.3).

**Failure:** if the backend cannot open the profile (a locked directory, say), `webview.start`
raises. `_open_app_window_native` already catches every exception, reports it, and falls back to the
browser path (`cli.py:1028-1030`, and `app-lifecycle` *"Falls back when the backend is installed but
cannot create a window"*). Nothing new is needed there, and task 1.3 pins that it still holds.

## D2 — An unset appearance follows the system

```ts
function systemMode(): ModeId {
  try {
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}
// loadConfig(): mode: prefs.mode ?? systemMode()
```

- Read once at load, not subscribed. An operator who changes the system theme while the app is open
  sees it on the next launch. Following live changes is a further choice nobody has asked for.
- **Nothing is written on load.** Only `setMode` writes (`configStore.ts:144-147`), so the unset state
  stays unset and keeps following the system.
- `index.html`'s initial `data-mode="dark"` is left alone. On a light system the first paint still
  flashes dark before the store applies light, exactly as it does today for every launch; making the
  first paint match needs an inline script in `index.html` and is out of scope.

## D4 — Reset clears the profile's window folder, and says when it could not

`reset` already removes the profile's data directory, so D1's placement makes it remove the window
folder with no new deletion code. Two things change:

- The confirmation lists the window folder on its own line, so the operator sees that stored
  preferences and unsent drafts go too.
- **A window that is still open holds its folder.** WebView2 keeps files in its user data folder
  locked while the window runs, and `reset` stops only the Hub process, not a window the CLI process
  is showing. `rmtree(..., ignore_errors=True)` then leaves part of the directory, and today's
  `Deleted {data_dir}` line (`cli.py:1435`) would be false. After the `rmtree`, `reset` checks
  whether the directory still exists. If it does, it prints a warning naming it and telling the
  operator to close the app window and run reset again, and returns 1 instead of printing success.

`reset --profile x` touches only `x`'s folder, per the existing *"Reset targets exactly one
profile"* scenario; tasks 1.9 and 1.10 pin it for the window folder.

## D5 — The extra's floor is already too low (found by the 5.0 check)

pywebview 5.0 has `private_mode` and `storage_path` on `start()`, so this change needs no floor raise
for them. But 5.0, 5.1 and 5.2 have **no `icon` parameter** on `start()`; it first appears in 5.3
(wheels read 2026-09-24). `cli.py:1027` already passes `icon=`, so on 5.0-5.2 `start` raises
`TypeError` and the app silently opens in the browser instead. The defect predates this change, but
the floor is the line this change re-derives, so task 2.4 raises it to `pywebview>=5.3`.

## D3 — The options

| Option | What it would break | What it releases |
|---|---|---|
| **Both halves (this change)** | Nothing: private mode is not relied on anywhere (`grep -rn private_mode src hub` finds nothing on `09127ba`). | The theme, the open project, drafts and every panel preference survive a close; a first launch matches the system. |
| Persistence only | — | Everything except the first-launch theme. |
| System default only | — | The first-launch theme; every other preference is still lost. |
| Neither | — | — |

## Open questions

1. Should an unset appearance also follow the system **while the app is open**? Recommended: no, not
   now (D2).

## Round log

- R1 2026-09-24: written.
- R2 2026-09-24, copied from `spec-queue/tracks/B11.md` (R2, "Claims that stand", `:442-447`):
  *"F385: pywebview `start()` has `private_mode=True, storage_path=None` (measured by signature), and
  `configStore.ts:49` defaults to `'light'`."* No claim of this change disagreed with the code. R2
  did not check the 5.0 floor.
- R3 2026-09-24, copied from `spec-queue/tracks/B11.md` (R3, "Claims that stand", `:637-640`):
  *"F385: pywebview 6.2.1 sets `IsInPrivateModeEnabled` from `private_mode` whatever `storage_path`
  is (`platforms/edgechromium.py:81`, `winforms.py:743-750`), so both kwargs are needed, as change 2
  says."* No claim of this change disagreed. `openspec validate --strict` passed.
- Operator review 2026-09-24 (`spec-queue/tracks/reviews/B11-2026-09-24.md` section 2): APPROVE WITH
  FIXES, applied as listed at the top. **The 5.0 check**, repeated on the `pywebview==5.0` wheel:
  `start(..., private_mode: bool = True, storage_path: str | None = None, ...)`;
  `platforms/edgechromium.py:45` sets `IsInPrivateModeEnabled` from `private_mode`, and
  `platforms/winforms.py:522-529` uses `storage_path` as the user data folder when private mode is
  off or a path is given. Both kwargs exist at the floor. The same read found `start()` has no
  `icon` before 5.3 (D5). Citations re-verified on `09127ba`; `openspec validate
  the-app-window-keeps-the-operators-preferences --strict` passes.
