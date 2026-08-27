# 2026-08-27 — fix and drive

Branch `autonomous/2026-08-27-fix-and-drive`, cut from `bbe00a7`. Stop at 2026-08-28T08:00+01:00.

Purpose, in the operator's words on arming: *"fix whatever you can fix and run a e2e-loop to find
errors and fix them."* Finding defects is the goal, not a side effect.

---

## Iteration 1 — BASELINE: every finding gets a status, and the open severity-A list

**2026-08-27T22:07+01:00 · commit `f8e0cf0` · queue item `BASELINE` → done**

### Reconciliation on arrival

STATE claimed the branch had to be cut. It was already cut and pushed — `9cf10dd`
("chore(autonomous): branch cut from bbe00a7, run armed for 08:00"), tree clean, local and
`origin/autonomous/2026-08-27-fix-and-drive` at the same sha. Nothing to reconcile beyond that;
`next_action`'s first clause was already satisfied, so this iteration did its second clause.

### What was done

`scripts/drive/FINDINGS.md` had 72 findings and no status field. Each `## F<n>` now carries a
`**Status:**` line immediately under its header, and a new `## Open severity-A baseline,
2026-08-27` section sits at the top of the file.

### Method, and the trap in it

The obvious method — `git log --all --grep="F<n>"` — is wrong here, and I only found out by
reading the commits it returned. F1, F2, F3, F4 and F6 are also finding numbers in a **different**
series: the operator-UX findings in `.claude/autonomous/2026-08-16-operator-ux-findings.md`, worked
through as `Q4-spec-ux-fixes` phases and referenced again by the `N6` review commits. An
unrestricted grep attributes `027506c "Q4-spec-ux-fixes: IMPLEMENT phase 1 (F2)"` to this file's
F2, which is about a UTC clock wearing a local label. It is not the same F2.

The fix: for each finding, find the commit that *first wrote its section* —

```
git log --all --reverse -S "## F<n> " -- scripts/drive/FINDINGS.md
```

— and only consider mentions at or after that commit's timestamp. That removes every false
attribution above, because the other series predates this file's sections. 3,211 commits scanned;
the per-finding mention lists are in `.claude/autonomous/scratch/mentions.txt` and the birth
commits in `births.json`.

Eleven findings could not be settled from commit subjects alone and were decided by reading their
own prose plus the fixing commit's body: F14, F15, F20, F26, F35, F37, F47, F61, F62, F66, and F3.
Two of those changed the answer I would otherwise have written:

- **F14** looked fixed — `7fcd172` names it. Its body says what actually shipped: a *derived*
  `awaiting_answer_reason` that reports the wait without moving the task's status. The task-state
  half is untouched, which is exactly why STATE lists F14's fix shape as an open operator decision
  blocking F60's parked half. Recorded as **partially fixed**, not fixed.
- **F35** looked fixed — `29ab883` shipped a refusal naming the field, its shape and an example.
  `78459e4` then **reverted** it on the operator's call, preferring the declared schema, and
  removed the machinery rather than leaving unreachable safeguard code behind ("a safeguard nobody
  can reach is worse than none, because it is counted"). Recorded as closed by decision, not by
  repair.

F60's guard was traced to its actual origin rather than assumed: `git log -S` on the docstring puts
`_asker_is_gone` in `033ec4c` (2026-08-10), sixteen days **before** F60 was filed. So the guard
STATE says is "already shipped" is not a response to the finding at all — it predates it.

### The baseline

Severity A still open — three, and only one wholly open:

| Finding | State |
|---|---|
| **F12** | open, no commit anywhere references it. Queued as `F12-SPEC`/`F12-IMPL`. |
| **F52** | partially fixed `68459ea`; the rest does not reproduce, central inference disproved by `0cda570`, last axis eliminated live by `57eb92b`. Out of scope. |
| **F60** | partially fixed `033ec4c` (which predates it); remaining half parked for F14, an operator decision. |

`F9 (A-)` is not a defect. The other seventeen A's are fixed with a named commit:
F1 F5 F10 F23 F27 F41 F43 F45 F49 F51 F54 F56 F57 F58 F70 F71 F72.

Open below A: F3 F15 F20 F21 F42 F47 F61 F62 F65 F66 F68, plus F53's second half and F14's
task-state half.

### Verification

Not a code change, so there is no test to watch fail. What was checked instead:

- **72 status lines for 72 headers**, asserted in the script that wrote them (it also asserts no
  finding number in the status table is unused).
- **Every sha cited resolves to a commit.** All 52 shas appearing in the new status lines and the
  baseline table were run through `git cat-file -t`; all 52 answer `commit`. Seventeen other
  7-hex-looking strings elsewhere in the file do *not* resolve — they are commits in throwaway test
  repositories and one `api_equivalent_usd_micros` value — and none of them are in the lines this
  iteration added.
- The one claim that would be embarrassing to get wrong — that the `Q4-spec-ux-fixes` F-numbers are
  a different series — was confirmed by reading `da31ca6`'s body, which describes "all six operator
  UX findings" and names F2's root cause as `SpecFrame.tsx`'s theme override. Not this file's F2.

### Honest limit on what this measures

Every "fixed" here means *a commit that says it fixed it exists and its body describes the right
defect*. It does **not** mean the fix was re-driven live tonight. This repository's dominant
failure mode is a change that passes its tests and cannot fire in production (F41 is literally a
finding about that, and F38's fix was dead for a week), so the baseline is a bookkeeping floor, not
a proof of correctness. The section says so in the file.

**Next:** `E2E-1` — the operator's headline ask. Full-surface `e2e-loop` sweep against a fresh
throwaway project outside this repository, fixing what it finds, every fix carrying a test watched
to fail.
