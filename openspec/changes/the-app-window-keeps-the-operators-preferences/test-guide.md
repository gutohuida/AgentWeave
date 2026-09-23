# Test guide — the app window keeps the operator's preferences

## Agent-verifiable

1. **The window asks for a kept profile.** Task 1.1 fails today and passes after: `start` receives
   `private_mode=False` and a `storage_path` under `~/.agentweave/hub/window`.
2. **The fallback still holds.** Task 1.3: a `start` that raises still falls back to the browser.
3. **An unset appearance follows the system.** Task 1.4 fails today (`light`) and passes after.
4. **A choice wins, and loading records none.** Tasks 1.6 and 1.7.

## Human-only

These need the real WebView2 window, which no test drives.

1. Choose dark, leave a draft unsent, close the window, reopen: dark, the same project, the draft
   there (task 3.1).
2. Remove `~/.agentweave/hub/window`, set the system to dark, open the app: it opens dark (3.2).
3. Look at `~/.agentweave/hub/window` after a launch: the profile is there, and nowhere under the
   repository.
