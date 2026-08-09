# Tasks — a dismissal cannot cost the whole conversation

## 1. Where "near the window" lives

- [x] 1.1 `FINAL_WARNING_PERCENT` in `checkpoint_policy.py`, with the reasoning stated where the
      existing `DEFAULT_THRESHOLD_VALUE = 80` comment already reasons about the same 95%
      compaction point. Below Claude Code's compaction, above any sensible ordinary threshold
- [x] 1.2 `needs_final_warning(policy, *, percent)` — true only when a percentage is known and it
      has reached the mark. Takes no `context_tokens`: this is deliberately not answerable in
      token mode, and accepting the argument would invite a caller to think it is

## 2. The behaviour

- [x] 2.1 The `dismissed` branch in `consider` promotes to `final` and broadcasts, instead of
      returning
- [x] 2.2 A conversation already `final` is not re-broadcast, exactly as `due` is not re-marked
- [x] 2.3 A conversation in `due` is left alone — its banner is already on screen
- [x] 2.4 Token mode with no resolvable window stays silent, and says so through `_declined`
- [x] 2.5 `automatic` is untouched: it never reaches the warning branch at all

## 3. The surface

- [x] 3.1 Taking a checkpoint clears `final` as it already clears `due`
- [x] 3.2 The dismissal endpoint refuses to move `final` back to `dismissed` — the state exists
      precisely because dismissal was already spent
- [x] 3.3 The banner renders with the checkpoint action and **no** dismiss action
- [x] 3.4 The local `warningDismissed` flag must not suppress it. That flag exists to hide the
      *first* warning between the click and the refetch; a final warning is a different fact
      about a conversation the operator has already dismissed once, so the flag is true by
      definition every time it matters

## 4. Verification

- [x] 4.1 `pytest hub/tests/`, `npx vitest run`, `npx tsc --noEmit`, `ruff check`
- [x] 4.2 `npm run build` + copy to `hub/hub/static/ui`, confirmed with `diff -rq`
- [x] 4.3 Live: dismiss a warning, drive the conversation past the final mark, confirm the
      non-dismissible warning appears and that no checkpoint was generated to produce it

> **Live-verified, and it found a defect the unit tests did not.**
>
> Driven through the real `consider` against the running Hub's own database
> (`proj-84d218db`, mode `offered`, threshold **tokens/150000**), with `conv-c311b78f` seeded to
> `dismissed`:
>
> | reading | state | worker invocations | checkpoints |
> |---|---|---|---|
> | 85% | `dismissed` | 23 | 0 |
> | 96% | `final` | 23 | 0 |
> | 98% again | `final` | 23 | 0 |
>
> **The first run of this produced `dismissed` at 96%.** The backstop was evaluated after
> `should_checkpoint`, which in token mode reads `context_tokens` alone — so a reading carrying a
> percentage and no token count declined as "below the tokens threshold of 150000" and the final
> warning was unreachable. It is now answered ahead of the threshold checks, because "near the
> window" is a claim about the window filling up rather than about the operator's configured
> number. Covered by `test_the_backstop_does_not_depend_on_the_configured_threshold`.
>
> Every unit test passed against the broken ordering, because they all configured percent mode and
> supplied a percentage. The live environment was in token mode.
>
> **Not verified:** the banner has not been driven in a browser. The absent dismiss action, the
> tone and the `warningDismissed` interaction are covered by vitest only.
