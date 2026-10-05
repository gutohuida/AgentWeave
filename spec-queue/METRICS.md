# Spec-process metrics: the tiered, drive-first trial

Started 2026-10-04, when the operator reset the process (`CLAUDE.md`, *Spec weight follows risk*).
The operator reviews it around **2026-10-18**: keep, loosen or tighten the tiers.

**One row per closed change or Tier-0 fix**, appended at archive or close time by whichever session
or window closed it. Times are wall-clock estimates from commit timestamps, rounded to 5 minutes.

**Caught** lists each real defect found before merge, tagged by the stage that found it:
`review`, `opus`, `test`, `drive`, or `post-merge`. "None" is a valid answer. A wording fix is
not a defect.

| Date | Change / finding | Tier | Spec | Build | Drive | Caught (stage: what) |
|---|---|---|---|---|---|---|
| 2026-10-04 | a-secret-split-across-two-events-is-still-scrubbed (F488), baseline before the reset | 2 (old 3-round) | 2h10 | 1h10 | 0h07 | R2: unscrubbed session.error log line · R3: edge whitespace defeats join · opus: test placement; F490 filed (out of scope) |
| 2026-10-05 | F493 the suites leak a run's credentials into its Hub | 0 | 0 | 0h10 | 0h10 | test: the CLI suite leaked too (4 `POST /session/sync`, 10 failures under a run env), not in the finding · drive: 5 fake rows before, 0 after, on `:8010` |
| 2026-10-05 | F490 agent tool writes skip the secret scrub | 0 (operator-directed; secrets) | 0 | 0h10 | 0h10 | test: own scan helper bug only · drive: none (stub-provider Copilot run, key in no column); before-drive refused by the session classifier |
| 2026-10-05 | F491 review context asks for the whole suite | 0 | 0 | 0h05 | 0h05 | None (drive: one 122 s run, approved; re-observed F492 in its tool inputs) |
