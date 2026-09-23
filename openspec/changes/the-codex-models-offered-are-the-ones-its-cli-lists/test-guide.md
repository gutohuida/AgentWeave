# Test guide — the Codex models offered are the ones its CLI lists

## Agent-verifiable

1. Tasks 1.1–1.3 behave as recorded: tests 1, 6 and 7 fail before group 2, and 8 fails with the
   conftest guard removed.
2. Drive 3.1 lists exactly the `visibility: "list"` slugs of `~/.codex/models_cache.json`, in
   `priority` order. Compare against
   `py -3.11 -c "import json,os;d=json.load(open(os.path.expanduser('~/.codex/models_cache.json'),encoding='utf-8'));print(sorted([m for m in d['models'] if m['visibility']=='list'],key=lambda m:m['priority']))"`.
3. Rename the cache aside, re-read `GET /model-catalog`, and see `built_in` with a reason naming the
   path. Rename it back and see `cli_cache` again, with no Hub restart. **Trial Hub only.**
4. `py -3.11 scripts/check_model_catalog.py` still runs and exits as before.

## Not verifiable here

A Codex *turn* on a cache-listed model. Codex is undrivable on this machine (2026-08-29). This
change does not claim that a spawn succeeds, only that the Hub offers what the CLI lists.

## Human-only

1. New runner with Codex selected: does the one-line source note make sense without context?
   Would you know what to do if it said *Built-in list*?
2. Add agent with Codex selected: is the preselected model one your installed Codex lists?
