# Test guide — the app window keeps the operator's preferences

## Agent-verifiable

1. **The window asks for a kept profile, one per Hub profile.** Tasks 1.1, 1.1a and 1.1b fail today
   and pass after: `start` receives `private_mode=False` and a `storage_path` of
   `<profile data dir>/window`, and every caller passes its `--profile` through.
2. **The fallback still holds.** Task 1.3: a `start` that raises still falls back to the browser.
3. **An unset appearance follows the system.** Task 1.4 fails today (`light`) and passes after.
4. **A choice wins, and loading records none.** Tasks 1.6 and 1.7.
5. **Reset clears one profile's window folder, and says when it cannot.** Tasks 1.9 and 1.10
   (controls) and 1.11, 1.12 (fail today).

## Human-only

These need the real WebView2 window, which no test drives.

1. Choose dark, leave a draft unsent, close the window, reopen: dark, the same project, the draft
   there (task 3.1).
2. Remove `~/.agentweave/hub/data/window`, set the system to dark, open the app: it opens dark (3.2).
3. Look at `~/.agentweave/hub/data/window` after a launch: the profile is there, and nowhere under
   the repository.
4. **Two app windows at once** (3.3): with one window open, run `agentweave --app` again for the same
   profile. A second window opens (or the CLI names the failure and opens the browser), and a
   preference changed in one shows in the other after it reloads. Then open a window for a throwaway
   named profile on another port (never `:8000`'s): its preferences are its own.
5. With a window open, reset its profile: reset warns that the folder is held and fails; close the
   window and reset again: the folder is gone (3.4).
