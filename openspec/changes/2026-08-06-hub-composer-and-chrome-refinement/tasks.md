# Tasks — composer and chrome refinement

**Dependency:** section 6 extends a requirement introduced by
`2026-08-04-hub-model-control-and-provisioning`. That change must be synced to the main specs before
this one is archived.

Reference material is at `https://github.com/pingdotgg/t3code` (MIT). The specific files read are
named in `proposal.md`; re-clone rather than guess if a detail is needed.

## 1. The control primitive

- [ ] 1.1 Remove `hover:border-[var(--border)]` from `ghost` in `hub/ui/src/components/ui/button.tsx`.
      Express hover as background and text prominence only.
- [ ] 1.2 Keep `border border-transparent` in the base class. It exists so emphasis never shifts
      layout; removing it would reintroduce the pixel shift its comment documents.
- [ ] 1.3 Leave `outline` and `destructive` alone — they draw a border at rest and are permitted to
      change it.
- [ ] 1.4 **Audit every `variant="ghost"` call site** for a control that relied on the hover border
      to be legible against its background. List what was checked; fix any that regress.
- [ ] 1.5 Unit test: a ghost control declares no hover border.
- [ ] 1.6 Unit test: a ghost control's resting and hover box dimensions are identical.

## 2. Composer control appearance

- [ ] 2.1 Add one shared composer-control appearance, the counterpart of t3code's
      `composerControlClassName`: content height, muted text and icon, hover brightens text, no
      border or fill at rest.
- [ ] 2.2 Rebuild `ControlPill` (`ComposerModelControls.tsx`) on the `Button` primitive using that
      appearance. Remove the hardcoded `h-8 rounded border`.
- [ ] 2.3 Route `ComposerConversationRouting` and `ComposerAgentSelector` through the same
      appearance so they cannot drift.
- [ ] 2.4 Make the pill fully rounded at its own height.
- [ ] 2.5 Remove `min-w-[160px]` from the popover. Give it a maximum width with truncation and no
      minimum.
- [ ] 2.6 Unit test: no composer control declares a resting or hover border.
- [ ] 2.7 Unit test: the popover declares no minimum width.
- [ ] 2.8 Unit test: a short-label control is narrower than a long-label one (content sizing is real,
      not incidental).
- [ ] 2.9 Unit test: each composer control still exposes a focus indicator.

## 3. Composer surface focus

- [ ] 3.1 Remove the `.conversation-composer-surface:focus-within` rule from `hub/ui/src/index.css`.
- [ ] 3.2 Confirm the resting surface still reads as a distinct surface without it; if it does not,
      adjust the resting treatment rather than restoring a focus reaction.
- [ ] 3.3 Unit test: the stylesheet declares no focus-within border, shadow, or ring on the composer
      surface.
- [ ] 3.4 Unit test: controls inside the composer still show focus indicators.

## 4. Provider marks

- [ ] 4.1 Add provider marks as inline SVG within the existing `Icon` module
      (`hub/ui/src/components/common/Icon.tsx`). No new dependency, no webfont, no network request.
      Source each mark from that provider's own published brand assets.
- [ ] 4.2 Resolve marks by the catalog's provider identity, with a text-label fallback for an
      unknown provider.
- [ ] 4.3 Show the mark beside the current value and beside each option in the composer's model
      control.
- [ ] 4.4 Show the mark beside each provider in `AgentCreateDialog.tsx`, keeping the provider name
      always present.
- [ ] 4.5 Confirm the existing source-contract test — that `ComposerModelControls.tsx` hardcodes no
      provider name — still passes. Do not weaken it to accommodate the lookup.
- [ ] 4.6 Unit test: an unknown provider renders a text label and no mark.
- [ ] 4.7 Unit test: a launchable provider with no mark is still selectable.

## 4b. Model picker — search, grouping, favourites

Reference: t3code `ModelPickerContent.tsx`, `ModelPickerSidebar.tsx`, `modelPickerSearch.ts`.

- [ ] 4b.1 Add search over the model list, matching label, identifier, and provider name.
      Substring/fuzzy, not leading-prefix only.
- [ ] 4b.2 Group entries by provider, with each entry attributable to its provider at a glance and a
      provider's entries reachable as a group.
- [ ] 4b.3 Ensure filtering never surfaces a model that is not otherwise selectable — filter the
      offered set, never widen it.
- [ ] 4b.4 Empty-result state that says nothing matched and can be cleared back to the full list.
- [ ] 4b.5 Favourites: mark/unmark from the picker, marked models presented first.
- [ ] 4b.6 Persist favourites across conversations and reloads. Decide and record where they live
      (operator-local vs Hub-stored) — they are the operator's preference, not project data.
- [ ] 4b.7 Guarantee favourites change ordering only: no agent's default or resolved model moves.
- [ ] 4b.8 Full keyboard operation: open, type to narrow, move, select, dismiss. Dismiss selects
      nothing.
- [ ] 4b.9 Unit tests: non-prefix match found; provider-name search; grouping; no extra models via
      search; empty state; favourite ordering; favourite persistence; favourites do not change
      resolution; each keyboard action; dismiss leaves model unchanged.
- [ ] 4b.10 Keep the picker's width content-derived per section 2 — search must not reintroduce a
      fixed width.

## 5. Project header

- [ ] 5.1 Replace `pathSegments.join(' › ')` in `ProjectHeader.tsx` with per-segment elements.
- [ ] 5.2 Move the path onto its own line, off the agent-count line.
- [ ] 5.3 Keep `elidePathSegments` and its tests; keep the full path available on hover.
- [ ] 5.4 Decide whether segments navigate. If they do not, ensure they are not styled as
      interactive. Record the decision.
- [ ] 5.5 Unit test: a multi-segment path renders as multiple elements, not one text node.
- [ ] 5.6 Unit test: the agent count and the path are not in the same line element.
- [ ] 5.7 Unit test: a deep path still elides in the middle and keeps its ends.

## 6. Tab strip boundary

- [ ] 6.1 Remove `borderBottom` from the nav in `ProjectTabs.tsx`. Keep `background: var(--top)`.
- [ ] 6.2 Check the boundary in both themes. If the plane alone is too weak, strengthen the plane —
      do not restore the rule.
- [ ] 6.3 Unit test: the view switcher declares no bottom border.

## 7. Native folder dialog — Hub side

- [ ] 7.1 Add a Hub module that opens the host's folder dialog and returns a path, cancellation, a
      timeout, or a failure as distinct outcomes. Windows first.
- [ ] 7.2 Run it off the event loop with a timeout. The Hub must serve other requests while a dialog
      is open — assert this, do not assume it.
- [ ] 7.3 Guard against concurrent requests: a second request while one is open opens no second
      dialog.
- [ ] 7.4 Report availability: unavailable in a container, unavailable without a desktop session,
      unavailable on an unsupported platform.
- [ ] 7.5 Endpoint for availability and for opening, authenticated like every other Hub endpoint and
      operator-scoped (no project ID — it precedes a project existing, same as `fs/list`).
- [ ] 7.6 Unit tests: each of path / cancel / timeout / failure / unavailable / concurrent.
- [ ] 7.7 Unit test: the Hub answers another request while a dialog is open.

## 8. Native folder dialog — UI side

- [ ] 8.1 Offer the native dialog in `ProjectManagerModal.tsx` only where the Hub reports it
      available.
- [ ] 8.2 Cancel leaves the typed path untouched and shows no error.
- [ ] 8.3 Timeout and failure are reported in their own terms, with browsing and typing still
      available.
- [ ] 8.4 Keep the in-app browser reachable as the fallback.
- [ ] 8.5 Unit tests for available / unavailable / cancel / timeout / failure.

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
