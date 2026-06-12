# PR 1: Fix SPA API Key Leak

> **Severity:** CRITICAL
> **Closes:** C1
> **Time:** ~30-40 minutes
> **Risk:** Low (only removes a code path, doesn't add new logic)
> **Strategy:** Test-first — write the failing test, confirm it fails, then apply the fix, confirm it passes.

---

## The bug

`hub/hub/main.py:66-99` — the `serve_spa` handler reads the first non-revoked API key from the database and embeds it in `<script>window.__AW_CONFIG__={...}</script>` inside the served HTML.

**Any unauthenticated `GET /` returns the live key in the response body.**

```bash
curl http://hub:8000/anything
# <!DOCTYPE html>
# <html>
# <head>
# <script>window.__AW_CONFIG__={"apiKey":"aw_live_a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6","projectId":"proj-default"};</script>
# ...
```

A network attacker can exfiltrate the key with a single `curl`. From there they have full Hub access: read all messages, tasks, agent output, project instructions, etc.

---

## Why it exists (and what the fix must preserve)

The SPA needs the API key to talk to the Hub. The current code embeds it in HTML so the React app can read `window.__AW_CONFIG__.apiKey` on first load. This is convenient for "open Hub URL → auto-connects" UX, but it's a security disaster.

**The fix:** have the SPA call `/api/v1/setup/token` on first load. This endpoint already exists (`hub/hub/api/v1/setup.py:46-71`) and is already restricted to localhost + Docker bridge IPs (`_is_local_address` check). A remote attacker hitting the SPA will see a 403 and fall back to manual SetupModal entry.

This is a defense-in-depth fix:
- The Hub already had `/api/v1/setup/token` for the CLI bootstrap use case.
- We're repurposing it for the SPA bootstrap.
- Remote users get the same UX they had before (manual entry), not auto-connect.
- Local users (the typical case) get the same UX as before (auto-connect).

---

## File changes

### 1. `hub/hub/main.py` — stop injecting the key

**Before** (lines 66-99):

```python
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str):
    if full_path.startswith("api/") or full_path == "health":
        raise HTTPException(404)

    # Inject runtime config so the dashboard connects automatically.
    # The Hub is serving the dashboard, so it already knows its own key.
    html = (UI_DIST / "index.html").read_text()

    # Fetch the live API key from DB — it may be auto-generated and
    # not present in settings.aw_bootstrap_api_key (env file)
    from sqlalchemy import select as _select

    from .db.engine import async_session_factory as _sf
    from .db.models import ApiKey as _ApiKey

    api_key_value = settings.aw_bootstrap_api_key
    project_id_value = settings.aw_bootstrap_project_id
    try:
        async with _sf() as _db:
            _res = await _db.execute(
                _select(_ApiKey).where(_ApiKey.revoked == False).limit(1)  # noqa: E712
            )
            _row = _res.scalar_one_or_none()
            if _row:
                api_key_value = _row.id
                project_id_value = _row.project_id
    except Exception:
        pass  # fall back to settings values

    config = json.dumps({"apiKey": api_key_value, "projectId": project_id_value})
    script = f"<script>window.__AW_CONFIG__={config};</script>"
    html = html.replace("</head>", f"{script}</head>")
    return HTMLResponse(html)
```

**After:**

```python
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str):
    if full_path.startswith("api/") or full_path == "health":
        raise HTTPException(404)
    if not (UI_DIST / "index.html").exists():
        raise HTTPException(404, "UI not built")
    return HTMLResponse((UI_DIST / "index.html").read_text())
```

Removes:
- The 5-line import block
- The DB query
- The `json.dumps(...)` of the config
- The `script` injection
- The 5-line `try/except: pass` block

Also remove the now-unused `import json` at the top of the file.

### 2. `hub/ui/src/api/setup.ts` — NEW file

```typescript
export interface SetupConfig {
  apiKey: string
  projectId: string
}

export async function fetchSetupToken(): Promise<SetupConfig | null> {
  try {
    const resp = await fetch('/api/v1/setup/token', { credentials: 'same-origin' })
    if (!resp.ok) return null  // 403 from non-localhost, 503 if no key configured
    const data = await resp.json()
    return { apiKey: data.api_key, projectId: data.project_id ?? 'proj-default' }
  } catch {
    return null  // network error, CORS, etc.
  }
}
```

### 3. `hub/ui/src/store/configStore.ts` — replace `window.__AW_CONFIG__` with bootstrap call

**Before** (lines 24-34):

```typescript
  // 2. Server-injected config takes precedence for connection settings
  const injected = (window as unknown as Record<string, unknown>).__AW_CONFIG__ as Partial<StoredConfig> | undefined
  if (injected?.apiKey) {
    return {
      apiKey:    injected.apiKey,
      hubUrl:    window.location.origin,
      projectId: injected.projectId ?? 'proj-default',
      theme:     stored.theme ?? 'cosmic',      // Use stored theme preference
      mode:      stored.mode  ?? 'light',       // Use stored mode preference
    }
  }
```

**After:**

Remove the `window.__AW_CONFIG__` block. Replace with a state field that the App.tsx populates via an async bootstrap.

Add to `StoredConfig`:
- `bootstrapState: 'pending' | 'ready' | 'failed'` (default 'pending')

Add to `ConfigState`:
- `bootstrap: () => Promise<void>` — async, calls `fetchSetupToken()`, if it returns a value and there's no apiKey in localStorage, call `setConfig(...)`. Sets `bootstrapState` to 'ready' or 'failed'.

Add to `loadConfig()`:
- Return `{ ..., bootstrapState: 'pending' }` instead of merging from `window.__AW_CONFIG__`.

(See the actual edit below in the implementation phase. The exact text will be written by the agent applying the fix.)

### 4. `hub/ui/src/App.tsx` — call `bootstrap()` on mount

Add a `useEffect` at the top of the App component:

```typescript
useEffect(() => {
  useConfigStore.getState().bootstrap()
}, [])
```

If `bootstrapState === 'pending'`, render a brief "Connecting…" indicator instead of the main UI. This is a UX tradeoff: a few hundred ms of loading on first load in exchange for the security fix.

---

## The test (write this FIRST, before the fix)

**File:** `hub/tests/test_setup.py`

Add these tests:

```python
@pytest.mark.asyncio
async def test_spa_does_not_leak_api_key_in_html(app):
    """Regression test: GET / must not contain the API key in the response body.

    The Hub serves the React dashboard at /. Previously, the SPA fallback
    injected the live API key into a <script> tag in the HTML so the
    dashboard could auto-connect. This leaked the key to any unauthenticated
    request, including remote attackers (curl http://hub:8000/anything).
    The key must now be fetched by the SPA from /api/v1/setup/token,
    which is restricted to localhost + Docker bridge IPs.
    """
    # Need a built UI dist for the SPA fallback to exist. Skip if not built.
    from pathlib import Path
    ui_dist = Path(__file__).parent.parent / "hub" / "static" / "ui"
    if not (ui_dist / "index.html").exists():
        pytest.skip("UI not built (no hub/static/ui/index.html)")

    resp = await app.get("/")
    assert resp.status_code == 200
    body = resp.text
    # The actual key (from conftest) must not appear in the HTML
    assert "aw_live_testkey_abcdefgh" not in body, (
        "API key leaked into SPA HTML response. "
        "The serve_spa handler must not inject __AW_CONFIG__."
    )
    # Also check no aw_live_ prefix at all (defense in depth)
    assert "aw_live_" not in body
    # The SPA fallback is still wired (returns HTML, not JSON)
    assert "<html" in body.lower()


@pytest.mark.asyncio
async def test_setup_token_still_works_for_localhost(app):
    """After the fix, /api/v1/setup/token must still be the bootstrap path."""
    resp = await app.get("/api/v1/setup/token")
    assert resp.status_code == 200
    data = resp.json()
    assert "api_key" in data
    assert data["api_key"].startswith("aw_live_")
```

**Test the test:** Before applying the fix, run `pytest tests/test_setup.py::test_spa_does_not_leak_api_key_in_html -v` and confirm it FAILS with the `aw_live_` assertion. This proves the test catches the bug.

---

## Verification

After applying the fix:

```bash
cd hub
pytest tests/test_setup.py -v
# Should show: 5 passed (3 existing + 2 new)

pytest tests/ -v
# Should show: all tests still pass
```

Manual verification:

```bash
# 1. Start the Hub (locally, so setup/token works)
docker compose up -d

# 2. Verify the leak is fixed
curl -s http://localhost:8000/ | grep -c "aw_live_"
# Expected: 0

# 3. Verify the SPA can still bootstrap from localhost
curl -s http://localhost:8000/api/v1/setup/token
# Expected: {"api_key":"aw_live_..."}

# 4. Verify the SPA still loads
curl -s http://localhost:8000/ | head -5
# Expected: <!DOCTYPE html>...
```

---

## Risk assessment

- **Backward compatibility:** Users with `apiKey` already in `localStorage` are unaffected (existing path 3 in `loadConfig`).
- **Remote access scenario:** A user accessing the Hub from a remote machine must enter the key once via SetupModal. The key is then stored in `sessionStorage` (full fix in PR 9) and the user is connected. This is the right UX — same as if `/api/v1/setup/token` returned 403 to that remote user.
- **What is NOT changing in PR 1:** CORS, auth, the `_is_local_address` heuristic, the existing `localStorage` write path. Those are in later PRs.
- **Performance:** One extra HTTP request on first page load. Negligible.
- **UX:** A brief "Connecting…" indicator for ~100-300ms while the bootstrap call completes. Acceptable.

---

## File change summary

| File | Action | LOC |
|---|---|---|
| `hub/hub/main.py` | Edit (lines 66-99 + remove `import json`) | −35 |
| `hub/ui/src/api/setup.ts` | New | +12 |
| `hub/ui/src/store/configStore.ts` | Edit (replace `__AW_CONFIG__` block with bootstrap state) | ±0 (replacement) |
| `hub/ui/src/App.tsx` | Edit (add useEffect for bootstrap) | +8 |
| `hub/tests/test_setup.py` | Edit (add 2 tests) | +30 |

**Net: +15 LOC, –35 LOC, 2 new tests, 1 deleted 5-line `try/except: pass` block, 1 deleted 24-line SPA key-injection code path, 1 unused `import json` removed.**

---

## Commit message

```
fix(hub): stop leaking live API key in SPA HTML response

The /  catch-all route in main.py embedded the first non-revoked API
key into a <script> tag in every HTML response. curl http://hub:8000/
returned a working key to any unauthenticated request.

Move bootstrap config to /api/v1/setup/token (already localhost-only).
The SPA now calls that endpoint on first load instead of receiving the
key in HTML. Remote users fall back to manual SetupModal entry.

Add regression test: GET / must not contain 'aw_live_' anywhere.
Existing /api/v1/setup/token test still passes.

Closes C1 from docs/audit-2026-q2/findings.md.
```

---

## How to execute this PR

1. **Confirm you're on the right branch:** `git checkout -b audit/2026-q2-hardening` (or check it out if it exists).
2. **Bump version:** `hub/pyproject.toml` 0.31.1 → 0.32.0-audit.1
3. **Write the failing tests** in `hub/tests/test_setup.py`. Run `pytest tests/test_setup.py::test_spa_does_not_leak_api_key_in_html -v` and confirm it FAILS.
4. **Apply the server fix** in `hub/hub/main.py`.
5. **Apply the client fix** in the 3 UI files.
6. **Run the tests:** `pytest tests/ -v` and `cd hub && pytest tests/ -v`. Both must be green.
7. **Manual smoke test:** `docker compose up -d` then `curl -s http://localhost:8000/ | grep -c aw_live_` (must be 0).
8. **Commit** with the message above.
9. **Push** the branch.
10. **Open a PR** to merge `audit/2026-q2-hardening` into itself (i.e., for the audit branch's history), or save it for the final merge to `master`.

---

## What's next

After PR 1 ships, move to **PR 2 — Transport data-loss bugs** (3-4 days, the biggest single PR). See `pr-roadmap.md` for the full sequence.
