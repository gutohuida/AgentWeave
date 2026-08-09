# Tasks — warn before spending

## 1. The state

- [x] 1.1 `Conversation.checkpoint_warning` — one nullable column holding `due` or `dismissed`,
      NULL meaning "not warned". **Not two booleans**: `warned` and `dismissed` together make
      "dismissed but never warned" representable, and every reader would have to decide what that
      meant
- [x] 1.2 Migration `0050`, guarded like `0038`-`0049`

## 2. The behaviour

- [x] 2.1 `offered` marks the conversation due and broadcasts it; it no longer generates
- [x] 2.2 A conversation already `due` is not re-marked, and one `dismissed` is left alone
- [x] 2.3 `automatic` is untouched — it generates and hands over, because that is what it means
- [x] 2.4 Dismissal endpoint, and a successor starts NULL so it is warnable again

## 3. The surface

- [x] 3.1 The warning appears in the conversation with **Checkpoint now** and **Dismiss**
- [x] 3.2 Distinguishable from the existing ready-checkpoint offer — one asks whether to spend,
      the other asks whether to hand over, and they can be true at once
- [x] 3.3 Live-refreshed, or the warning appears only on reload

## 4. Verification

- [x] 4.1 `pytest hub/tests/`, `npx vitest run`, `npx tsc --noEmit`, `ruff check`
- [x] 4.2 `npm run build` + copy to `hub/hub/static/ui`, confirmed with `diff -rq`
- [x] 4.3 Live: cross a threshold under `offered`, confirm a warning and **no** worker invocation

> **Live-verified.** With the project on `offered` and a threshold well below the conversation's
> usage, a real opus-2 turn left `conv-c311b78f` marked `due` and produced **no worker
> invocation** — the newest was thirteen minutes earlier, from before the change. Warned, spent
> nothing.
>
> **Two older tests inverted rather than deleted.**
> `test_under_offered_a_checkpoint_is_made_but_nothing_is_cut_over` asserted the behaviour this
> change removes; it now reads `..._nothing_is_made_and_nothing_is_cut_over` and records why. The
> repeat-suppression test moved to `automatic`, since only that mode still generates.
