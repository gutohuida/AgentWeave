# Proposal — the app window keeps the operator's preferences

**Round 1, 2026-09-24** (bundle B11, `spec-queue/tracks/B11.md`). Finding: **F385 (C)**, filed by
the operator from their own use (operator review 2026-09-24 applied: `spec-queue/tracks/reviews/B11-2026-09-24.md` section 2): *"whenever I close the hub and open again the theme changes from
dark to light."* Re-verified on `ce086b6`. **Nothing here is implemented yet.**

## Why

Two halves, both still as filed.

1. **The window forgets everything the app stores.** `src/agentweave/cli.py:1025-1027` opens the
   window with `webview.create_window("AgentWeave", url, text_select=True)` and
   `webview.start(icon=_app_icon_path())`. pywebview 6.2.1 (installed; the extra pins `>=5.0`,
   `pyproject.toml:67`) declares `start(..., private_mode: bool = True, storage_path: str | None =
   None, ...)`, measured with `inspect.signature`. A private profile is discarded when the window
   closes, so every `localStorage` write the app makes is gone at the next launch. That is more than
   the theme. `grep -rn "localStorage.setItem" hub/ui/src` finds: the appearance and the open
   project (`store/configStore.ts:107,119`), the sidebar's width, collapse, expanded agents and rail
   view (`App.tsx:131,139`, `layout/Sidebar.tsx:192,200,208`), the model favourites
   (`agents/ModelPicker.tsx:29`), the spec tree and presentation (`spec/FileTree.tsx:36`,
   `spec/SpecTree.tsx:61`, `spec/specPreferences.ts:129`), the panel tabs (`store/panelTabsStore.ts`),
   and **unsent composer drafts** (`lib/composerDrafts.ts:27`).
2. **An unset appearance is light, whatever the system says.** `store/configStore.ts:49` reads
   `mode: prefs.mode ?? 'light'`. Nothing in `hub/ui/src` consults `prefers-color-scheme`. So an
   operator who never chose and one whose choice was lost both get light.

## What Changes

- **The window keeps a profile on disk, one per Hub profile** (design D1): `webview.start(...,
  private_mode=False, storage_path=str(_hub_profile_window_dir(profile)))`, a `window/` folder inside
  the profile's own data directory (`~/.agentweave/hub/data/window` for the default,
  `~/.agentweave/hub/profiles/<name>/window` for a named one; `cli.py:641-650`). The `--profile`
  the CLI already holds is passed through to `_open_app_window_native`. The folder is somewhere the
  product owns and can name, which the operator's `R4` reset button will need.
- **Reset clears it** (design D4): `agentweave reset [--profile x]` already removes that profile's
  data directory, so it removes the window folder with it. It now lists the folder, and when an open
  window holds the folder it warns and fails instead of reporting success.
- **The extra's floor rises to `pywebview>=5.3`** (design D5): the first release whose `start()`
  takes the `icon` the CLI already passes.
- **An appearance nobody chose follows the system's** (design D2): `prefs.mode ?? systemMode()`,
  where `systemMode()` reads `matchMedia('(prefers-color-scheme: dark)')`. Choosing a mode still
  writes it, and a written choice still wins. The unset state is not written on load, so it keeps
  following the system at every launch.

The session credential stays in `sessionStorage` (`configStore.ts:37-40`), so a persistent profile
does not persist it. No Hub change, no migration, no API shape.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `app-lifecycle`: a new requirement, *The app window keeps what the app stored between launches*,
  which also keeps that state per profile and has reset clear it. It adds to, and does not
  contradict, *A named profile selects a separate, deliberate instance* (reset still targets exactly
  one profile's data; the window state is part of it).
- `hub-workspace-shell`: a new requirement, *An appearance the operator never chose follows the
  system's*.

## Impact

- `src/agentweave/cli.py` (`_open_app_window_native`, its four callers, `cmd_reset`, a new
  `_hub_profile_window_dir`), `pyproject.toml`'s `app` extra, `tests/test_cli.py` and
  `tests/test_hub_commands.py`.
- `hub/ui/src/store/configStore.ts` and its tests. **A UI bundle**, so it reaches `:8000`'s live app
  on the operator's next reload once committed (CLAUDE.md). It needs no backend change, so it has no
  restart-ordering hazard.
- The CLI half reaches the operator when they next install or run the CLI from this checkout.
