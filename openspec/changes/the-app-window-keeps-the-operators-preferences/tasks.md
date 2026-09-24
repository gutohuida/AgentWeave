## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2 (recorded in design.md's round log, copied from `spec-queue/tracks/B11.md` R2; the 5.0 half was done by the operator review, also recorded there): independently re-derive design's Context table: the window's `create_window`/`start` call, pywebview's `start` signature on the installed build **and on 5.0** (the extra's floor: confirm `private_mode` and `storage_path` exist there, or raise the floor), every `localStorage` writer in `hub/ui/src`, and whether anything in the app relies on storage being empty at launch (a first-run flow, `SetupModal`, `bootstrap()`'s auto-select at `configStore.ts:176`). Record in design's round log
- [x] 0.2 R3 (recorded in design.md's round log, copied from `spec-queue/tracks/B11.md` R3): a second independent re-derivation; `openspec validate the-app-window-keeps-the-operators-preferences --strict` passes
- [ ] 0.3 The operator records the F385 decision in `spec-queue/DECISIONS.md` (both halves, or one)

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 `tests/test_cli.py`, beside `test_pywebview_installed_opens_window_with_resolved_url`: with `HUB_DIR` patched to `tmp_path`, the fake `start` captures all kwargs; `_open_app_window_native(url)` passes `private_mode is False` and `Path(storage_path) == HUB_DIR / "data" / "window"`. Record that it FAILS today (neither kwarg is passed)
- [ ] 1.1a Same place: `_open_app_window_native(url, profile="a")` passes `Path(storage_path) == HUB_DIR / "profiles" / "a" / "window"`, and profiles `a` and `b` get different paths. Record that it FAILS today (no `profile` parameter)
- [ ] 1.1b `tests/test_hub_commands.py`: `_hub_native_start(..., app=True, profile="a")` on its "already running" branch (`cli.py:1068-1079`, health check patched to 200) calls `_open_app_window_native` with `profile="a"`; the same for `cmd_hub_start`'s Docker "already running" branch (`:1263-1274`). Record that both FAIL today
- [ ] 1.2 Control, PASSES before and after: `test_pywebview_installed_opens_window_with_resolved_url` (title, URL, icon)
- [ ] 1.3 Control, PASSES before and after: `test_webview_start_exception_falls_back`, with the fake `start` now accepting the new kwargs
- [ ] 1.4 `hub/ui/src/__tests__/configStore.test.ts`: with empty `localStorage` and `matchMedia('(prefers-color-scheme: dark)')` stubbed to match, a fresh store's `mode` is `dark`. Record that it FAILS today (`light`)
- [ ] 1.5 Same file: with the stub not matching, `mode` is `light` (control; passes today)
- [ ] 1.6 Same file: stored `{mode: 'light'}` with the stub matching dark gives `light` (control)
- [ ] 1.7 Same file: loading the store with empty storage writes nothing to `agentweave-prefs`. Control today; it pins D2's "nothing is written on load"
- [ ] 1.8 Same file: `window.matchMedia` throwing or absent gives `light`, no exception
- [ ] 1.9 `tests/test_hub_commands.py`, beside `test_reset_with_profile_deletes_only_that_profiles_directory` (`:649`): profiles `a` and `b` each have a `window/` folder with a file in it; `reset --profile a --yes` removes `a`'s window folder and leaves `b`'s. Control (passes today, because the folder sits inside the data directory); it pins D1's placement
- [ ] 1.10 Same file, beside `:671`: bare `reset --yes` removes `HUB_DIR/data/window` and leaves `HUB_DIR/profiles/a/window`. Control, as 1.9
- [ ] 1.11 Same file: with `shutil.rmtree` patched to leave the directory in place (as a locked window folder does), `reset --yes` returns 1, prints a warning naming the directory and telling the operator to close the app window, and does not print `Deleted` or `Hub data destroyed`. Record that it FAILS today (it prints both and returns 0)
- [ ] 1.12 Same file: `reset`'s confirmation lists the profile's window folder. Record that it FAILS today

## 2. The fix

- [ ] 2.1 `cli.py`: add `_hub_profile_window_dir(profile)` beside `_hub_profile_data_dir` (design D1); give `_open_app_window_native` a `profile` parameter and pass `private_mode=False, storage_path=str(_hub_profile_window_dir(profile))` to `webview.start`, with a comment naming F385 and this change; pass `profile` at all four call sites (`:1077`, `:1195`, `:1270`, `:1363`)
- [ ] 2.1a `cmd_reset`: list the window folder in the confirmation; after the `rmtree`, if the data directory still exists, warn (naming it, and to close the app window) and return 1 (design D4)
- [ ] 2.2 `configStore.ts`: add `systemMode()` per design D2 and use it in `loadConfig`
- [ ] 2.3 Rebuild the bundle (`make ui` or `scripts/refresh_ui_bundle.py`); commit `hub/ui/src` and `hub/hub/static/ui` together
- [ ] 2.4 `pyproject.toml:67`: raise the extra to `pywebview>=5.3`, the first release whose `start()` takes `icon` (design D5); no test can install 5.2 in CI, so record the wheel check inline
- [ ] 2.5 `pytest tests/test_cli.py tests/test_hub_commands.py -q`, `cd hub/ui && npx vitest run src/__tests__/configStore*.test.ts`, then the full vitest suite and `npm run lint`; record counts inline

## 3. Human-only

- [ ] 3.1 The operator opens the app, chooses dark, types an unsent draft, closes the window, and reopens: dark, the same project, the draft present
- [ ] 3.2 With `~/.agentweave/hub/data/window` removed and a dark system theme, the app opens dark
- [ ] 3.3 Two app windows at once: with one app window open, run `agentweave --app` again for the same profile; a second window opens (or the CLI reports the failure and opens the browser), and a preference changed in one is there in the other after it reloads. Then open a window for a second profile (`agentweave --profile t --port 8011 --app`, never against `:8000`'s profile): its preferences are its own
- [ ] 3.4 With an app window open, run `agentweave reset --profile t --yes` for that window's profile: reset warns that the folder is held and returns non-zero; close the window and rerun: the folder is gone
