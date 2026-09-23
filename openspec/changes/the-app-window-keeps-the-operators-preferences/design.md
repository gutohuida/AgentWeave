# Design — the app window keeps the operator's preferences

**Built on the recommended answer to B11's F385 question** (ROUNDS.md D13, *"pywebview private
mode"*): **persist the window's profile, and let an unset appearance follow the system.** If the
operator answers only the first half, drop D2 and its requirement; if only the second, drop D1 and
its requirement. The halves are independent (F385's own text says so).

## Context — measured on `ce086b6`

| Fact | Where |
|---|---|
| Window opened with no profile arguments | `src/agentweave/cli.py:1025-1027` |
| `start(... private_mode=True, storage_path=None ...)` is pywebview's default | `inspect.signature(webview.start)` on pywebview 6.2.1, this machine |
| The extra allows any pywebview from 5.0 | `pyproject.toml:67` `app = ["pywebview>=5.0"]` |
| The CLI already names the Hub's home | `cli.py:242` `HUB_DIR = Path.home() / ".agentweave" / "hub"` |
| Unset mode resolves to light | `hub/ui/src/store/configStore.ts:49` |
| The credential lives in `sessionStorage`, not `localStorage` | `configStore.ts:37-40` (`SESSION_STORAGE_KEY`) |
| The page's first paint is `data-mode="dark"` before the store applies a mode | `hub/ui/index.html:2`; applied at `App.tsx:150` |
| `index.html` is served with no validators, so a persistent HTTP cache cannot hold a stale page | `hub/hub/main.py:573-579` returns `HTMLResponse(... read_text())`, no `ETag` or `Last-Modified`; hashed `/assets` are immutable by name |
| The CLI tests stub `webview` for every test by default | `tests/conftest.py:35-42` |
| The native-window test captures `start`'s kwargs | `tests/test_cli.py:305-308` |

## D1 — A profile on disk, under the product's own home

```python
webview.start(
    icon=_app_icon_path(),
    private_mode=False,
    storage_path=str(HUB_DIR / "window"),
)
```

- **Why an explicit `storage_path`.** With `private_mode=False` alone, the backend picks a location
  of its own. The product should be able to name where its state is, both for the operator and for
  the reset button `R4` asks for.
- **What persists that did not.** Everything the Proposal lists. The most valuable is not the theme:
  it is the unsent composer draft, which `agent-conversation-workspace` *"Unsent composer text
  survives navigation and reload"* already protects within a session and which a window close
  destroys today.
- **What does not persist.** `sessionStorage` is per window session under either setting, so the
  session credential still does not outlive the window.
- **Stale pages.** A persistent profile keeps an HTTP cache. `index.html` carries no validators and
  is re-fetched, and the assets it names are content-hashed, so a rebuilt bundle still reaches the
  window on its next load (the property CLAUDE.md relies on for `:8000`).
- **Two Hubs.** Origins differ by port (`:8000`, `:8010`), so the profiles' storage does not mix.

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

## D3 — The options

| Option | What it would break | What it releases |
|---|---|---|
| **Both halves (this change)** | Nothing: private mode is not relied on anywhere (`grep -rn private_mode src hub` finds nothing). | The theme, the open project, drafts and every panel preference survive a close; a first launch matches the system. |
| Persistence only | — | Everything except the first-launch theme. |
| System default only | — | The first-launch theme; every other preference is still lost. |
| Neither | — | — |

## Open questions

1. Should an unset appearance also follow the system **while the app is open**? Recommended: no, not
   now (D2).

## Round log

- R1 2026-09-24: written.
