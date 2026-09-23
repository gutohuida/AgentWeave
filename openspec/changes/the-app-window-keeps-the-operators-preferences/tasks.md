## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [ ] 0.1 R2: independently re-derive design's Context table: the window's `create_window`/`start` call, pywebview's `start` signature on the installed build **and on 5.0** (the extra's floor: confirm `private_mode` and `storage_path` exist there, or raise the floor), every `localStorage` writer in `hub/ui/src`, and whether anything in the app relies on storage being empty at launch (a first-run flow, `SetupModal`, `bootstrap()`'s auto-select at `configStore.ts:176`). Record in design's round log
- [ ] 0.2 R3: a second independent re-derivation; `openspec validate the-app-window-keeps-the-operators-preferences --strict` passes
- [ ] 0.3 The operator records the F385 decision in `spec-queue/DECISIONS.md` (both halves, or one)

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 `tests/test_cli.py`, beside `test_pywebview_installed_opens_window_with_resolved_url`: the fake `start` captures all kwargs; assert `private_mode is False` and `Path(storage_path) == HUB_DIR / "window"`. Record that it FAILS today (neither kwarg is passed)
- [ ] 1.2 Control, PASSES before and after: `test_pywebview_installed_opens_window_with_resolved_url` (title, URL, icon)
- [ ] 1.3 Control, PASSES before and after: `test_webview_start_exception_falls_back`, with the fake `start` now accepting the new kwargs
- [ ] 1.4 `hub/ui/src/__tests__/configStore.test.ts`: with empty `localStorage` and `matchMedia('(prefers-color-scheme: dark)')` stubbed to match, a fresh store's `mode` is `dark`. Record that it FAILS today (`light`)
- [ ] 1.5 Same file: with the stub not matching, `mode` is `light` (control; passes today)
- [ ] 1.6 Same file: stored `{mode: 'light'}` with the stub matching dark gives `light` (control)
- [ ] 1.7 Same file: loading the store with empty storage writes nothing to `agentweave-prefs`. Control today; it pins D2's "nothing is written on load"
- [ ] 1.8 Same file: `window.matchMedia` throwing or absent gives `light`, no exception

## 2. The fix

- [ ] 2.1 `cli.py` `_open_app_window_native`: pass `private_mode=False, storage_path=str(HUB_DIR / "window")` to `webview.start`, with a comment naming F385 and this change
- [ ] 2.2 `configStore.ts`: add `systemMode()` per design D2 and use it in `loadConfig`
- [ ] 2.3 Rebuild the bundle (`make ui` or `scripts/refresh_ui_bundle.py`); commit `hub/ui/src` and `hub/hub/static/ui` together
- [ ] 2.4 `pytest tests/test_cli.py -q`, `cd hub/ui && npx vitest run src/__tests__/configStore*.test.ts`, then the full vitest suite and `npm run lint`; record counts inline

## 3. Human-only

- [ ] 3.1 The operator opens the app, chooses dark, types an unsent draft, closes the window, and reopens: dark, the same project, the draft present
- [ ] 3.2 With `~/.agentweave/hub/window` removed and a dark system theme, the app opens dark
