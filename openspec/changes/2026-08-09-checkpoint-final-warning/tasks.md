# Tasks — a dismissal cannot cost the whole conversation

## 1. Where "near the window" lives

- [ ] 1.1 `FINAL_WARNING_PERCENT` in `checkpoint_policy.py`, with the reasoning stated where the
      existing `DEFAULT_THRESHOLD_VALUE = 80` comment already reasons about the same 95%
      compaction point. Below Claude Code's compaction, above any sensible ordinary threshold
- [ ] 1.2 `needs_final_warning(policy, *, percent)` — true only when a percentage is known and it
      has reached the mark. Takes no `context_tokens`: this is deliberately not answerable in
      token mode, and accepting the argument would invite a caller to think it is

## 2. The behaviour

- [ ] 2.1 The `dismissed` branch in `consider` promotes to `final` and broadcasts, instead of
      returning
- [ ] 2.2 A conversation already `final` is not re-broadcast, exactly as `due` is not re-marked
- [ ] 2.3 A conversation in `due` is left alone — its banner is already on screen
- [ ] 2.4 Token mode with no resolvable window stays silent, and says so through `_declined`
- [ ] 2.5 `automatic` is untouched: it never reaches the warning branch at all

## 3. The surface

- [ ] 3.1 Taking a checkpoint clears `final` as it already clears `due`
- [ ] 3.2 The dismissal endpoint refuses to move `final` back to `dismissed` — the state exists
      precisely because dismissal was already spent
- [ ] 3.3 The banner renders with the checkpoint action and **no** dismiss action
- [ ] 3.4 The local `warningDismissed` flag must not suppress it. That flag exists to hide the
      *first* warning between the click and the refetch; a final warning is a different fact
      about a conversation the operator has already dismissed once, so the flag is true by
      definition every time it matters

## 4. Verification

- [ ] 4.1 `pytest hub/tests/`, `npx vitest run`, `npx tsc --noEmit`, `ruff check`
- [ ] 4.2 `npm run build` + copy to `hub/hub/static/ui`, confirmed with `diff -rq`
- [ ] 4.3 Live: dismiss a warning, drive the conversation past the final mark, confirm the
      non-dismissible warning appears and that no checkpoint was generated to produce it
