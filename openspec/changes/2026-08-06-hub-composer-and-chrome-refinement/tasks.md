# Tasks — composer and chrome refinement

**Dependency:** section 6 extends a requirement introduced by
`2026-08-04-hub-model-control-and-provisioning`. That change must be synced to the main specs before
this one is archived.

Reference material is at `https://github.com/pingdotgg/t3code` (MIT). The specific files read are
named in `proposal.md`; re-clone rather than guess if a detail is needed.

## 1. The control primitive

- [x] 1.1 Remove `hover:border-[var(--border)]` from `ghost` in `hub/ui/src/components/ui/button.tsx`.
      Express hover as background and text prominence only. Also merged `active:` into the same
      `bg-[var(--accent)]` fill rather than leaving it on the removed border colour.
- [x] 1.2 Keep `border border-transparent` in the base class. It exists so emphasis never shifts
      layout; removing it would reintroduce the pixel shift its comment documents.
- [x] 1.3 Leave `outline` and `destructive` alone — they draw a border at rest and are permitted to
      change it.
- [x] 1.4 **Audit every `variant="ghost"` call site** for a control that relied on the hover border
      to be legible against its background. Checked all 14 files using `variant="ghost"`
      (`AgentCreateDialog`, `AgentOutputPanel`, `ConversationControls`, `ChartersPage`, `JobCard`,
      `JobForm`, `ProjectHeader`, `ProjectTabs`, `Sidebar`, `DirectoryPicker`,
      `QuestionInterruptCard`, `RunnersPage`, `SpecPage`, `SpecWorkspace`) — every site is an icon or
      text button on an ordinary surface/card background, and `hover:bg-[var(--accent)]` (unchanged
      by this fix) was already present on all of them. None relied specifically on the border for
      legibility; no regressions found, none fixed.
- [x] 1.5 Unit test: a ghost control declares no hover border.
      `buttonVariants.test.ts` — "ghost declares no hover or active border utility".
- [x] 1.6 Unit test: a ghost control's resting and hover box dimensions are identical.
      `buttonVariants.test.ts` — "the base transparent border is the only border rule in play,
      so hover cannot shift box dimensions" (verifies `ghost`'s own class list contributes no
      `border*` token beyond the base's unconditional `border border-transparent`).

## 2. Composer control appearance

- [x] 2.1 Add one shared composer-control appearance, the counterpart of t3code's
      `composerControlClassName`: content height, muted text and icon, hover brightens text, no
      border or fill at rest. Implemented as two pieces so no radius/sizing class ever has to
      out-specificity another: a new `pill` `size` variant on the `Button` primitive
      (`h-8 gap-1 px-2.5 text-xs`, deliberately no `rounded-*`) plus an exported
      `composerControlClassName` (`rounded-full text-[var(--text-2)] hover:text-[var(--text)]`) in
      `ComposerModelControls.tsx`, used together (`variant="ghost" size="pill"
      className={composerControlClassName}`).
- [x] 2.2 Rebuild `ControlPill` (`ComposerModelControls.tsx`) on the `Button` primitive using that
      appearance. Remove the hardcoded `h-8 rounded border`.
- [x] 2.3 Route `ComposerConversationRouting` and `ComposerAgentSelector` through the same
      appearance so they cannot drift. `ComposerConversationRouting` already rendered through
      `ControlPill` itself; `ComposerAgentSelector` had its own hand-rolled trigger button, now
      rebuilt on `Button` with the same `composerControlClassName` import.
- [x] 2.4 Make the pill fully rounded at its own height. (`rounded-full` in the shared appearance,
      paired with the radius-free `pill` size — see 2.1.)
- [x] 2.5 Remove `min-w-[160px]` from the popover. Give it a maximum width with truncation and no
      minimum. Now `max-w-64`; `ControlOption`'s label already truncates (`min-w-0 flex-1
      truncate`, unrelated to the removed fixed minimum).
- [x] 2.6 Unit test: no composer control declares a resting or hover border.
      `composerModelControls.test.tsx` — "composerControlClassName declares no border and no fixed
      width".
- [x] 2.7 Unit test: the popover declares no minimum width. Same file — "ControlPill.tsx declares no
      fixed minimum-width on its popover" (matches `min-w-[`, not the unrelated `min-w-0` flex
      escape hatch elsewhere in the file).
- [ ] 2.8 Unit test: a short-label control is narrower than a long-label one (content sizing is real,
      not incidental). **Not covered by an automated test** — jsdom does not perform real layout, so
      an actual pixel-width comparison isn't possible under vitest; covered instead by 2.6's
      assertion that no fixed-width class exists, and by the live check in §10.
- [x] 2.9 Unit test: each composer control still exposes a focus indicator.
      `composerModelControls.test.tsx` — "the model pill trigger renders as a real button exposing a
      focus indicator"; `buttonVariants.test.ts` also confirms `focus-visible:ring-2` is present for
      every variant/size combination including `ghost`/`pill`.

## 3. Composer surface focus

- [x] 3.1 Remove the `.conversation-composer-surface:focus-within` rule from `hub/ui/src/index.css`.
- [x] 3.2 Confirm the resting surface still reads as a distinct surface without it; if it does not,
      adjust the resting treatment rather than restoring a focus reaction. The resting rule already
      carries `border: 1px solid var(--border-hi)` (the elevated end of the border scale, not the
      ordinary `--border`) plus its own drop shadow — kept as-is; no strengthening needed. Full
      confirmation is the live check in §10.
- [x] 3.3 Unit test: the stylesheet declares no focus-within border, shadow, or ring on the composer
      surface. `hubVisualLanguage.test.ts` — "the composer surface does not react to focus".
- [x] 3.4 Unit test: controls inside the composer still show focus indicators. Same test — confirms
      `Composer.tsx` still renders through the `Button` primitive, whose base class carries an
      unconditional `focus-visible:ring-2` (verified generally in `buttonVariants.test.ts`).

## 4. Provider marks

- [x] 4.1 Add provider marks as inline SVG within the existing `Icon` module
      (`hub/ui/src/components/common/Icon.tsx`). No new dependency, no webfont, no network request.
      Source each mark from that provider's own published brand assets. Sourced Anthropic's and
      OpenAI's actual mark paths from t3code's own `Icons.tsx`
      (`apps/web/src/components/Icons.tsx`, `ClaudeAI`/`OpenAI` exports, MIT) via `gh api` against
      the upstream repo, not approximated — those are each provider's own published mark, the same
      one t3code itself renders. OpenAI's mark uses `currentColor` (it's a monochrome mark by
      design); Anthropic's fixed brand colour is a new mode-independent `--provider-claude` token in
      `index.css` (kept out of the .tsx file — `hubVisualLanguage.test.ts` bans raw hex in
      `src/components/**/*.tsx`).
- [x] 4.2 Resolve marks by the catalog's provider identity, with a text-label fallback for an
      unknown provider. New `ProviderMark({ provider, label, size, className })` — unknown provider
      renders `providerInitials(label)` (t3code's own initials algorithm, ported) in a small badge,
      never a broken or wrong icon.
- [x] 4.3 Show the mark beside the current value and beside each option in the composer's model
      control. `ControlPill`/`ControlOption` gained an optional `icon` prop; `ModelPill` computes one
      `ProviderMark` (every model in one Model pill belongs to the same already-resolved provider)
      and passes it to both the trigger and every option — `EnumControlPill` (Effort etc.) and
      `ComposerConversationRouting` ("To") pass no icon, unaffected.
- [x] 4.4 Show the mark beside each provider in `AgentCreateDialog.tsx`, keeping the provider name
      always present. A native `<option>` cannot host an SVG in any browser, so "beside each
      provider" required replacing the bare `<select>` with a real listbox (new `ProviderPicker`,
      same button+popover shape as `ComposerAgentSelector`) — this was the literal bare-`<select>`
      the proposal named as the "more consequential" case of this problem. The Model and Charter
      fields are untouched, still native `<select>`s (out of task 4's scope; 4b is the composer's own
      model-picker rebuild, a different component). Updated 2 existing tests that drove the old
      `<select>` via `fireEvent.change` to open-then-click, matching `ComposerAgentSelector`'s own
      established test pattern in this codebase.
- [x] 4.5 Confirm the existing source-contract test — that `ComposerModelControls.tsx` hardcodes no
      provider name — still passes. Confirmed: `ModelPill` passes `provider.provider`/`provider.label`
      (catalog-supplied), never a literal; the actual "claude"/"codex" keys live in `Icon.tsx`, a
      different file the contract test doesn't scan.
- [x] 4.6 Unit test: an unknown provider renders a text label and no mark.
      `providerMark.test.tsx` — "renders an unknown provider as text initials, and no mark".
- [x] 4.7 Unit test: a launchable provider with no mark is still selectable.
      `agentCreationUi.test.tsx` — "a launchable provider with no brand mark is still selectable"
      (added a third mocked catalog provider, `future-cli`, with no entry in `PROVIDER_MARKS`).

## 4b. Model picker — search, grouping, favourites

Reference: t3code `ModelPickerContent.tsx`, `ModelPickerSidebar.tsx`, `modelPickerSearch.ts`.

**Scope decision, not covered by design.md (operator confirmed via `AskUserQuestion` before starting
this section):** the composer's model pill is scoped to one already-resolved provider (the target
agent's bound runner) — `model-catalog`'s own spec is explicit that "the choices are the ones the
catalog declares for the *relevant* provider" and control values never cross providers. Cross-
provider switching through this control would mean rebinding the agent's runner, a bigger, separately
specced action. Built single-provider, with the search/grouping/favourites mechanism generic enough
that a labelled provider-group header works today (exactly one group) and is ready if a future
catalog ever offers more than one group in one picker.

- [x] 4b.1 Add search over the model list, matching label, identifier, and provider name.
      Substring/fuzzy, not leading-prefix only. New `hub/ui/src/components/agents/ModelPicker.tsx`,
      case-insensitive `.includes()` against all three.
- [x] 4b.2 Group entries by provider, with each entry attributable to its provider at a glance and a
      provider's entries reachable as a group. One labelled section (`ProviderMark` + provider label)
      per the single resolved provider — see scope decision above.
- [x] 4b.3 Ensure filtering never surfaces a model that is not otherwise selectable — filter the
      offered set, never widen it. Filter operates on `provider.models` only, never adds to it.
- [x] 4b.4 Empty-result state that says nothing matched and can be cleared back to the full list.
- [x] 4b.5 Favourites: mark/unmark from the picker, marked models presented first.
- [x] 4b.6 Persist favourites across conversations and reloads. **Decision: operator-local**
      (`window.localStorage`, key `aw.composer.favouriteModels`) — the same mechanism
      `configStore.ts` already uses for mode/selected-project, not a new Hub-stored table. They are
      this browser's preference, not project state; keyed `${provider}:${modelId}` to avoid any
      cross-provider id collision.
- [x] 4b.7 Guarantee favourites change ordering only: no agent's default or resolved model moves.
      The favourite toggle never calls `onChangeModel`; only the sort comparator reads `favourites`.
- [x] 4b.8 Full keyboard operation: open, type to narrow, move, select, dismiss. Dismiss selects
      nothing. Arrow-key roving highlight + Enter-to-select, intercepted on the popover's own
      `onKeyDown` (search input keeps real DOM focus throughout — a lighter pattern than full
      ARIA-combobox `aria-activedescendant`, consistent with this codebase's existing listbox
      components, none of which implement that either).
- [x] 4b.9 Unit tests: non-prefix match found; provider-name search; grouping; no extra models via
      search; empty state; favourite ordering; favourite persistence; favourites do not change
      resolution; each keyboard action; dismiss leaves model unchanged. All in `modelPicker.test.tsx`
      (12 tests).
- [x] 4b.10 Keep the picker's width content-derived per section 2 — search must not reintroduce a
      fixed width. Popover is `max-w-72` (a cap, not a minimum); enforced by a source-contract test
      that specifically excludes `max-w-` while catching a bare fixed-width `w-N` token.

## 5. Project header

- [x] 5.1 Replace `pathSegments.join(' › ')` in `ProjectHeader.tsx` with per-segment elements.
- [x] 5.2 Move the path onto its own line, off the agent-count line.
- [x] 5.3 Keep `elidePathSegments` and its tests; keep the full path available on hover (`title` moved
      from the inline `<span>` onto the path's own `<p>`).
- [x] 5.4 Decide whether segments navigate. **Decided: no.** Rendered as plain, non-interactive
      `<span>` elements (no button/link semantics, no hover/focus state) — there is no per-segment
      navigation destination in the Hub today, and design.md Decision 5 is explicit that a segment
      with nowhere to go should not look interactive. Structure without false affordance.
- [x] 5.5 Unit test: a multi-segment path renders as multiple elements, not one text node.
      `projectHeaderPath.test.tsx` — "renders a multi-segment path as multiple elements".
- [x] 5.6 Unit test: the agent count and the path are not in the same line element. Same file —
      "keeps the agent count and the path out of the same line element".
- [x] 5.7 Unit test: a deep path still elides in the middle and keeps its ends. Same file — "elides a
      deep path in the middle and keeps its head and tail, with the full path on hover".

## 6. Tab strip boundary

- [x] 6.1 Remove `borderBottom` from the nav in `ProjectTabs.tsx`. Keep `background: var(--top)`.
- [ ] 6.2 Check the boundary in both themes. If the plane alone is too weak, strengthen the plane —
      do not restore the rule. **Deferred to §10's live check** (not yet performed).
- [x] 6.3 Unit test: the view switcher declares no bottom border. `hubVisualLanguage.test.ts` — "the
      tab strip carries only a plane change at its boundary, not a dividing line".

## 7. Native folder dialog — Hub side

- [x] 7.1 Add a Hub module that opens the host's folder dialog and returns a path, cancellation, a
      timeout, or a failure as distinct outcomes. Windows first. New `hub/hub/native_dialog.py`.
      `tkinter.filedialog.askdirectory` (Windows' own native common dialog, via Tk's platform
      binding) — standard library, no new dependency, matching every other choice in this codebase.
      Runs as a short-lived subprocess (`python -c <script>`), not a thread hosting a blocking Tk
      mainloop: a subprocess can be killed cleanly on timeout, a thread cannot.
- [x] 7.2 Run it off the event loop with a timeout. The Hub must serve other requests while a dialog
      is open — assert this, do not assume it. `asyncio.create_subprocess_exec` +
      `asyncio.wait_for(proc.communicate(), timeout=...)`, fully async — never blocks the loop.
      Asserted live by 7.7 below, not just by inspection.
- [x] 7.3 Guard against concurrent requests: a second request while one is open opens no second
      dialog. Module-level `asyncio.Lock`; a second call while held raises `DialogBusyError`
      *before* any subprocess spawns (not queued behind the first).
- [x] 7.4 Report availability: unavailable in a container, unavailable without a desktop session,
      unavailable on an unsupported platform. Platform check (`sys.platform == "win32"`) plus an
      interactive-window-station check via `ctypes` (stdlib) — the same technique .NET's own
      `Environment.UserInteractive` uses. Both a Linux container (fails the platform check) and a
      Windows service/Session-0 process (fails the window-station check) fall out of these two
      checks without container-specific detection logic.
- [x] 7.5 Endpoint for availability and for opening, authenticated like every other Hub endpoint and
      operator-scoped (no project ID — it precedes a project existing, same as `fs/list`).
      `GET/POST /api/v1/fs/native-dialog/{availability,open}`, `get_operator` dependency, matching
      `fs_browse.py`'s own pattern exactly.
- [x] 7.6 Unit tests: each of path / cancel / timeout / failure / unavailable / concurrent.
      `test_native_dialog.py`, `TestOpenFolderDialogUnit` (6 tests) + `TestCheckAvailability` (3).
- [x] 7.7 Unit test: the Hub answers another request while a dialog is open. Same file,
      `test_hub_answers_another_request_while_a_dialog_is_open` — a controllable `asyncio.Event`
      holds the mocked dialog call open while a concurrent `GET /health` is asserted to complete
      first, then the dialog call is released and confirmed to complete after. Full suite: 761
      passed, 9 skipped (747 baseline + 14 new).

## 8. Native folder dialog — UI side

- [x] 8.1 Offer the native dialog in `ProjectManagerModal.tsx` only where the Hub reports it
      available. New `hub/ui/src/api/nativeDialog.ts` (`useNativeDialogAvailability`,
      `useOpenNativeDialog`, same instance-scoped shape as `fsBrowse.ts` — added to
      `projectScopedApiContract.test.tsx`'s existing instance-level exemption set alongside it, same
      rationale). When available, "Browse…" opens the native dialog directly; when not, it opens the
      in-app `DirectoryPicker` exactly as before — unchanged for every operator this isn't offered to.
- [x] 8.2 Cancel leaves the typed path untouched and shows no error. `outcome: "cancelled"` is a
      distinct no-op branch — no `setPath`, no notice.
- [x] 8.3 Timeout and failure are reported in their own terms, with browsing and typing still
      available. A `role="status"` notice names which one occurred (and the failure's own detail
      text); the text input and both browse paths remain fully interactive throughout.
- [x] 8.4 Keep the in-app browser reachable as the fallback. A "Browse within the Hub instead" toggle
      is shown alongside the native option — same `DirectoryPicker`/`pickerOpen` state as the
      native-unavailable case, not a second, parallel implementation.
- [x] 8.5 Unit tests for available / unavailable / cancel / timeout / failure.
      `projectManagerDirectoryPicker.test.tsx`, new describe block (6 tests): offered-only-when-
      available, chosen path fills the field, cancel is silent, timeout/failure each report their
      own text, in-app browser stays reachable. Full frontend suite: 451 passed (445 baseline + 6
      new), `tsc --noEmit` clean.

## 9. Directory browser improvements (the fallback path)

- [ ] 9.1 Present the available filesystem roots.
- [ ] 9.2 Show the current location as navigable structure with direct return to an ancestor.
- [ ] 9.3 Give choosing the current directory its own visible control. Remove the undisclosed
      double-click-to-choose behaviour.
- [ ] 9.4 Keyboard operation: move between entries, enter, go to parent, choose.
- [ ] 9.5 Unit tests for roots, ancestor navigation, the explicit choose control, and each keyboard
      action.

## 10. Verification

- [ ] 10.1 `npm test -- --run` in `hub/ui` — full pass, count recorded.
- [ ] 10.2 `npx tsc --noEmit` in `hub/ui` — clean.
- [ ] 10.3 `pytest hub/tests -q` — full pass, count recorded.
- [ ] 10.4 `npm run build` and refresh `hub/hub/static/ui`; `pytest hub/tests/test_ui_staleness.py -q`
      passes.
- [ ] 10.5 **Live:** composer controls show no box at rest or on hover; pills are rounded and fit
      their labels; the popover fits its longest item.
- [ ] 10.6 **Live:** clicking into the composer produces no ring or border change.
- [ ] 10.7 **Live:** provider marks render in the composer and in agent creation, in both themes.
- [ ] 10.8 **Live:** the project path renders as segments on its own line; a deep path elides.
- [ ] 10.9 **Live:** no rule under the view switcher, in both themes.
- [ ] 10.10 **Live:** the native folder dialog opens, returns a real path, and registers a project
      with it. Also exercise cancel.
- [ ] 10.11 **Live:** keyboard-only traversal of the composer control row.
- [ ] 10.11b **Live:** open the model picker, search by provider name and by partial model name,
      favourite a model, reload, and confirm it is still presented first.
- [ ] 10.12 Narrow viewport (390×800) — **carried forward as unverifiable** without interactive
      resize control. State this rather than leaving it blank.
- [ ] 10.13 Numeric contrast ratios — **carried forward as unverifiable**; no checker available.
- [ ] 10.14 Reduced motion — **carried forward as unverifiable** since
      `2026-08-04-hub-contextual-navigation`; `preview_set_appearance` emulates only
      `prefers-color-scheme`.
- [ ] 10.15 `openspec validate 2026-08-06-hub-composer-and-chrome-refinement --strict` — clean.
