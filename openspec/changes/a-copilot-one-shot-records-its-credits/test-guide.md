# Test guide — a Copilot one-shot records its credits

## Agent-verifiable

1. Group 1's tests fail and pass as `tasks.md` records. Run them against the real capture, never a
   hand-written stream, except where a test edits a captured line to make the case it names.
2. After drive 3.1, the trial database (`mode=ro`) holds a `checkpoint` and a `checkpoint_probe`
   row with `cli = 'copilot'` and non-NULL `ai_nano_aiu` / `premium_requests`. A Copilot worker row
   written before this change still reads NULL: nothing is backfilled.
3. `GET /accounting` is byte-identical before and after the drive's checkpoint for every field
   except the turns the drive itself ran. This change adds no read surface (design D5).
4. `test_runner_adapters_imports.py` passes: the adapter's new import of `copilot_usage` loads no
   `hub.db` or `hub.api`.

## Human-only

1. After `:8000` restarts on this change, run one Copilot checkpoint and decide whether a figure you
   can only read from the database is worth having before `worker-spend-counts-against-the-budget`
   shows it. (The figure cannot be recovered later for calls made before this change.)
2. Compare a recorded figure with what your GitHub Copilot billing or `/usage` shows for the same
   period, if you can. The Hub stores raw nano-AIU and displays it as AI credits divided by 1e9
   (`NANO_AIU_PER_AI_CREDIT`). That divisor is the SDK's documented convention only (the archived
   change's Q5), so a mismatch by a power of ten is the first thing to check. The Hub never converts
   credits to money.
