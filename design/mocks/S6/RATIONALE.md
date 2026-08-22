# S6 rationale — questions and permission prompts

Four passes (P1 explore, P2 validate + mock, P3 iterate, P4 finish — this document). This screen
is really three surfaces sharing one visual family: `PermissionRequestCard` and `AgentQuestionCard`
(inline, above the composer, `.conversation-interject`/`.interject-*`), and the older
`QuestionsPanel`/`AnswerForm` full-list tab plus its `QuestionInterruptCard` overview banner. All
three are covered in both mocks. **S1 did not touch these** — confirmed at P1 by grepping S1's own
research/rationale for "interject" and these component names, zero hits — so this was genuinely new
ground.

## Research → six findings, three of them missing features

Full sourcing lives in `RESEARCH.md`: all five components read in full including their comments
(several — `nobodyWaiting`, the number-key-selects-but-does-not-submit behaviour, the
expiry-consequence sentence instead of a countdown — encode deliberate UX decisions already made
correctly, not styling gaps, and were left alone); two `WebSearch` passes (approval-dialog UX for
AI agents; chat quick-reply/keyboard-shortcut patterns) confirming the existing shortcut and
free-text-after-structured-choice conventions are sound, not novel risk; and three T3 Code
sourcemaps pulled directly (`ConfirmDialogHost.tsx`, `ComposerPendingApprovalPanel.tsx`,
`ComposerPendingApprovalActions.tsx`) — the modal `ConfirmDialogHost` pattern was read and
deliberately **not** adopted, since AgentWeave's inline-card choice (the conversation keeps flowing
around it; a modal would block it) is a considered difference, not a gap.

1. **`PermissionRequestCard`'s Allow/Deny hierarchy was accidental, not decided.** `Allow` used
   `<Button size="sm">` with no `variant` — defaulting to `ghost`, the quietest button in the
   vocabulary — for the single highest-consequence decision in the product, while `Deny` was
   `variant="outline"` and visually outranked it. Both mocks resolve this deliberately: `Allow` gets
   the filled/primary treatment, `Deny` stays outline — an affirmative default is legible without
   being a dark pattern, since nothing pre-selects or auto-times toward it.
2. **No request-kind label.** T3's `detailLabel` ("Command" / "File to read" / "File change") shown
   before the value; AgentWeave's `describe()` returns one bare string. Both mocks add a small
   category label, reusing existing semantic tokens (never inventing one) — this is the colour-coding
   opportunity IDENTITY.md calls in scope.
3. **No distinct detail sub-surface.** The command/path text sat as plain body copy with
   `wordBreak: break-all` and no visual separation from the surrounding card, no scroll for a long
   value. Both mocks give it a bordered, `--surface`-toned sub-block with its own scroll, mirroring
   T3's structural idea in AgentWeave's own tokens.
4. **No pending-count indicator on `PermissionRequestCard`**, unlike `AgentQuestionCard`'s existing
   `interject-count`. Both mocks add the same "N of M" treatment for parity.
5. **`AnswerForm`'s submit button is a raw inline-styled `background: var(--surface-3)`**, entirely
   outside the `Button` component — no raised/quiet states, no focus-ring treatment. Rebuilt on the
   real button vocabulary in both mocks.
6. **Motion is close to absent across all three surfaces**: option-row selection is an instant
   colour swap, `QuestionInterruptCard` appears/disappears with no transition, and a stale vs. live
   question read as equally prominent. `considered.html` applies U0a's motion vocabulary (entrance
   keyframe, hover elevation, amber near-timeout tint) — colour only, explicitly no ticking number,
   per the research finding to avoid countdown pressure.

Two ideas from T3 were mocked as **missing features and flagged, not implemented**, per the
pre-authorization to mock what research turns up: **"Always allow this session"** (a third,
scoped-grant action alongside Allow/Deny — mocked as `.btn-scope`, a ghost button, deliberately the
quietest of the three so it doesn't compete with the Allow/Deny decision itself) and the
**pending-count indicator** above (already built, not merely proposed, since it reused an existing
pattern rather than inventing one).

## What was rejected, and under which clause

Nothing from `RESEARCH.md`'s findings was discarded — P2 validated all six against
`IDENTITY.md`'s rejection test line by line and all six passed cleanly: no new hue (clause 1 — the
kind-label and near-timeout tint both reuse existing semantic tokens), `--blue`/`--ring` untouched
outside focus/selection (clause 2), no new radius (clauses 3/4), no new icon source (clause 5 — the
scoped-grant button is text-only), and the one adopted T3 pattern (`ConfirmDialogHost`'s modal
shape) was explicitly **not** taken, on architectural grounds stated above rather than a rejection
test clause. Honestly recording nothing was rejected under the test itself, rather than inventing a
rejection to appear more rigorous.

## P3 — adversarial iterate found no mock defect, one real pre-existing bug

P2's own build pass already screenshotted all four combinations (variant × theme) at rest and read
every image — thorough, but resting-state only. P3 went further: real keyboard `Tab`-driven
`:focus-visible` on Deny, real mouse `:hover` on `.q-row`/`.btn-scope`, real `mousedown`-held
`:active` on Allow, and a 420px narrow-viewport reflow check — all across both files and both
themes. Nothing needed fixing. One initial false alarm (Deny's focus ring appearing absent in
`considered.html`) was chased down and resolved as a test-timing artifact — `getComputedStyle` was
sampled mid-`box-shadow`-transition at t≈0, since the ring transitions over `--dur-fast` (150ms);
adding a settle wait before reading confirmed the ring renders correctly, and the same false
negative reproduced identically on `restrained.html` once its own wait was removed, proving it was
never a mock defect. `restrained.html`'s `.q-row` correctly has no hover rule at all — a deliberate
smallest-fix omission per its own stated intent, not an oversight in one file only.

**One genuine, verified pre-existing defect in the real product, recorded but not fixed** (out of
this mocks-only queue item's scope): `hub/ui/src/components/agents/PermissionRequestCard.tsx:103`
sets `fontFamily: 'var(--font-mono)'` inline, but `--font-mono` is never declared anywhere as a CSS
custom property — the app's actual monospace styling comes from a `.font-mono` *class*
(`index.css:229-230`), not a variable of that name. The inline style resolves to nothing in the
browser today, so the command-detail text in the real, running component likely does not render in
monospace despite the component's evident intent. Both S6 mocks independently wrote the same
variable name but with a CSS `var()` fallback (`var(--font-mono, ui-monospace, monospace)`), so they
render correctly by accident of the fallback syntax — meaning a morning reader comparing a mock
screenshot to the real running app may notice the mock's command text in monospace and the real
one not, an unflagged visual delta this pass didn't introduce but is worth naming here. A real fix
later is small: either declare `--font-mono` as a token, or change the inline style to
`className="font-mono"`.

## Verification summary across all four passes

- P2: `py -3.11` + Playwright loading each file via `file://` (no server — static documents), both
  variants × both themes, full-page screenshots at 960×1400, read and checked against the rejection
  test. Zero broken images, three pre-existing `@fontsource` 404 console errors (already documented
  elsewhere in this queue, not new).
- P3: real interaction battery — `Tab`-driven focus-visible, real hover, real mousedown-held active,
  420px narrow-viewport reflow — across both files and both themes. No mock defect found; one
  test-timing false alarm resolved; one genuine pre-existing real-component bug found and recorded
  above.
- P4 (this pass): re-read both files in full against clause 5 with distance from having written
  them — still reads as the same product refined, not a redesign. No further mock change was made:
  P3 found nothing in the mocks themselves to fix, only the `--font-mono` finding recorded above,
  which belongs in this document, not a mock edit.
- All verification screenshots were deleted after reading, per this queue's established
  no-committed-screenshots precedent (`.gitignore`'s blanket `*.png` rule) — `git status --short`
  confirmed only the intended `.html`/`.md` files remained before each commit.

**S6 is now fully done — all four passes (P1–P4) complete and verified.**
