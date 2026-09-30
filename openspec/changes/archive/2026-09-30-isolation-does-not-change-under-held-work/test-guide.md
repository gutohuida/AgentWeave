# Test guide — isolation does not change under held work

## Agent-verifiable

1. **All three doors refuse under held work** (`PATCH /agents/{name}`, `POST /agents/register`,
   `POST /session/sync`). 1.1-1.4, 1.11, 1.12 fail today.
2. **A refusal changes nothing** — on `/session/sync`, neither the session data nor the roster. 1.5, 1.11.
3. **The rule reads the config the Hub reads** (session entry over `Agent.config`): a change the
   session entry overrides is accepted. 1.9, 1.10 — they pass today and fail against a helper that
   looks at `Agent.config` alone.
4. **Idle agents, unrelated settings and roster seeding are unaffected.** 1.6, 1.7, 1.13, 1.14.
5. **F242's drive** (3.1): the 409 body, and a clean `git status` in the project root.

## Human-only

Nothing in the app sets isolation, by design, so there is nothing to click. Read the 409 sentence
recorded in 3.1 and ask: does it tell you which task to finish or reassign, and that nothing was
changed?
