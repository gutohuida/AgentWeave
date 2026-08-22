# S8-jobs research — scheduled jobs (`JobsPage`, `JobCard`, `JobForm`)

First sub-screen of queue item S8 (`jobs`, then `agents`, then `logs`, then the command palette —
each its own four-pass unit per the queue item's own text and `pre_authorised`). This pass reads the
current code end to end before touching anything, per `screen_pass_protocol`.

## What was read

- **`JobsPage.tsx`** (full). Header + "New Job" button, an `archiveError` alert banner, three filter
  pills (`all`/`active`/`paused`, `row-item` class — the same interaction primitive `Sidebar` and the
  cron-preset chips in `JobForm` use), a plain vertical card list (`grid gap-3 max-w-3xl` — one
  column, not an actual grid), and a stats footer (`Total` / `Active` / `Paused` counts plus "Jobs
  fire based on server time"). Loading state is a spinner + text, not a skeleton — same gap
  `IDENTITY.md` already names as generic across the app.
- **`JobCard.tsx`** (full, including comments). Two comments encode deliberate decisions worth
  preserving: `RunHistory` must not say "No runs yet" while `historyLoading` is still true, because a
  job with real failed firings previously read as one that had never fired (a correctness bug
  masquerading as a styling default — do not reintroduce it in a mock's simplified loading path);
  and the run-history row's error-summary span is ordered *before* the timestamp specifically because
  ordering it last let it consume the row's `flex-1` free space and shunted the timestamp back
  against the trigger word, producing `"scheduled1 minute ago"` with no space — invisible until a
  card's own history loaded, since the jobs-list response never carries a run to render. Structure:
  header (name + `Local` badge + `@agent` + cron **shown only as a monospace code chip, not a
  translated sentence**), a badges row (enabled/paused, session mode, run count), next/last run as
  plain small text, an action row (`Run`/`Pause`or`Resume`/`Archive` with a two-step confirm), and an
  expand toggle revealing message text, a 5-run history list, an optional `LoopBlock` (rendered only
  when `job.loop` is present — a plain job's card must not change shape at all, human-only check
  8.1), and an IDs footer. `LoopBlock` is its own component specifically so the `useTasks` fetch it
  needs only runs for a job that actually has a loop.
- **`JobForm.tsx`** (full). A centred modal (`fixed inset-0` + scrim), five plain fields (name,
  agent select, message textarea, cron text input + five preset chips, session-mode radio pair), and
  a collapsed-by-default "Make this a loop" section. A comment explains why `loopEnabled` is tracked
  as its own boolean rather than inferred from `purpose` being non-empty: a controlled textarea
  always renders `purpose=""`, and the server's rule is `purpose is not None` — so an always-present
  empty string must not, by that fact alone, opt every job into being a loop. The cron field is raw
  text entry with no live validation and no preview of what it actually means or when it will
  next fire before submission — the operator commits blind. Native `<input type="radio">` /
  `<input type="checkbox">` are unstyled, unlike the custom control vocabulary `_system/controls.html`
  (U0b) already built for toggles/selects.
- **`hub/ui/src/index.css`** — confirmed available tokens: `--row-hover/-active/-selected`,
  `--lift-hi`/`--press-lo`, `--dur-fast/base/slow`, `--ease`, `--radius*`, the semantic colours
  (`--green`/`--amber`/`--red`/`--blue`), and `tint()` from `lib/colorTint.ts` (already used for the
  archive-error banner background).
- **`design/mocks/_system/foundations.html` and `controls.html`** (U0a/U0b, both already built this
  run) — the elevation scale, interaction-state vocabulary, and button/badge/toggle taxonomy this
  mock must draw from rather than invent again. Jobs is the first screen after U0a/U0b, so it is the
  first real test of whether that vocabulary composes onto a genuinely different surface (a
  scheduling list) rather than only the ones it was designed against.

## External research

- **Cron UI baseline** (Inventive HQ cron builder, CrontabRobot, cron-expression-descriptor):
  the near-universal pattern is separate minute/hour/day/month/weekday fields *plus* a
  plain-English translation shown live below the expression, and a preview of the next several fire
  times in the viewer's local zone, so the operator confirms intent before committing rather than
  parsing `0 9 * * 1-5` by eye.
  ([Inventive HQ](https://inventivehq.com/tools/developer/cron-builder),
  [cron-expression-descriptor](https://bradymholt.github.io/cron-expression-descriptor/),
  [DEV Community guide](https://dev.to/_d7eb1c1703182e3ce1782/cron-expression-builder-guide-create-scheduled-tasks-like-a-pro-13p9))
- **Modern self-hosted cron dashboards** (Cronboard, Cronmaster, Cronicle): next-run time is treated
  as first-class information shown inline in the list, not something the operator has to compute
  from the cron string; run history renders as a compact glanceable trend rather than requiring an
  expand-to-see interaction for every job.
  ([Cronboard/UBOS](https://ubos.tech/news/cronboard-modern-terminal%E2%80%91based-cron-job-monitoring-dashboard/),
  [Cronmaster/Noted](https://noted.lol/cronmaster/),
  [Cronicle WebUI docs](https://github.com/jhuckaby/Cronicle/blob/master/docs/WebUI.md))
- **GitHub Actions workflow runs**: status badges recolour per outcome and are the primary scan
  target of the list, not a caption; a run's real-time graph and per-step status are available a
  click away, and the *list* view is deliberately terse — confirms AgentWeave's own two-level
  (collapsed card / expanded detail) structure is the right shape, it is just under-styled at the
  collapsed level.
  ([GitHub Docs: viewing workflow run history](https://docs.github.com/en/actions/managing-workflow-runs/viewing-workflow-run-history),
  [GitHub Docs: monitor workflows](https://docs.github.com/en/actions/how-tos/monitor-workflows))

## Findings — what's missing, not just unstyled

1. **The cron string is never translated to English anywhere the operator sees it before or after
   creating a job.** The form's five preset buttons carry a label (`"Daily at 9am"`) but typing or
   editing the field freehand shows only the raw string, and the card shows only the raw string too.
   A missing-feature gap per every source above, not a colour problem. In scope to mock (a small,
   dependency-free cron-to-English formatter covering the finite preset-like shapes this product's
   jobs actually use); noted for `RATIONALE.md` as a feature call, not implemented here.
2. **No next-run preview before submit.** The operator commits a schedule without seeing when it
   will actually fire first. Same category as finding 1 — mock it, don't implement it.
3. **Collapsed card carries no run-history signal at all.** The only place "is this job healthy"
   shows is inside the 5-run list, which requires an expand + (for a job with no cached `job.history`)
   a network fetch. A compact trend (e.g. last-5-runs as small status dots) on the *collapsed* card
   would answer "is this job okay" at list-scan speed — the GitHub Actions pattern above. This is a
   genuine information gap, not decoration; the dots reuse the exact status→colour mapping
   `RunHistory` already computes, so it does not invent new semantics.
4. **Texture/motion gaps, same character as every other screen so far**: no hover lift on cards
   (`--lift-hi` exists, unused here), the filter pills and cron-preset chips share the `row-item`
   class but the active-state contrast is minimal, action buttons don't distinguish primary
   (`Run`) from routine (`Pause`/`Resume`) from destructive (`Archive`, already correctly red) by
   weight, the expand chevron has no rotation transition, `LoopBlock`'s queue-count badges are all
   `variant="secondary"` regardless of status word (`pending`/`in_progress`/`blocked`/... all read
   identically), and the loading state is the same generic spinner named as a product-wide gap in
   `IDENTITY.md` rather than a skeleton shaped like a job card.
5. **`JobForm`'s native radio/checkbox controls are unstyled**, inconsistent with the segmented and
   toggle patterns `_system/controls.html` already built. The loop section's disclosure is a bare
   chevron + text with no container, motion, or visual separation once open beyond a top border.
6. **Source distinction (`Local` badge) is easy to miss** — a single small secondary badge next to
   the name, same visual weight as every other badge, though a locally-defined job (no server
   record) behaves differently enough (see `hub/hub/jobs` local-source handling) that an operator
   should be able to tell at a glance which jobs live where.

## What must not change (`IDENTITY.md` clause 5, clause 7)

- No new hues for run-status colours — `--green`/`--amber`/`--red`/`--text-3` already cover
  completed/failed-or-skipped/stopped/pending exactly as `RunHistory` maps them today; a run-trend
  dot strip reuses this mapping verbatim.
- No pill-shaped cards or a second corner radius — cards stay `var(--radius)`/`var(--radius-lg)`
  family, matching every other screen's cards.
- No pie/donut/gauge chart for run health — a row of small status dots is the density-preserving,
  identity-consistent equivalent (clause 6: at least as much information per screen).
- The cron-to-English formatter and next-run preview, if mocked, must look like inline text using
  existing type scale — not a new "insight card" pattern foreign to the rest of the product.
