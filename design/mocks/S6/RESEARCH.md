# S6 research — questions and permission prompts

P1 of the four-pass protocol. No mock built this pass; this is the research this screen's mocks
(P2) will draw from.

## What this "screen" actually is — five components, three surfaces

Confirmed by reading source and grepping call sites, not assumed:

| Component | File | Where it renders | Role |
|---|---|---|---|
| `QuestionsPanel` | `components/questions/QuestionsPanel.tsx` | Dedicated app tab (`App.tsx:373`, page id `questions`) | Full list: blocking / non-blocking / answered, each with free-text `AnswerForm` |
| `AnswerForm` | `components/questions/AnswerForm.tsx` | Inside `QuestionsPanel`, one per question | Free-text textarea + submit |
| `QuestionInterruptCard` | `components/questions/QuestionInterruptCard.tsx` | `OverviewPage.tsx:177`, banner | "An agent is waiting" summary linking to the Questions tab |
| `AgentQuestionCard` | `components/agents/AgentQuestionCard.tsx` | Inline in the conversation, above the composer | Structured options (single/multi-select) for the question the *open* run is asking |
| `PermissionRequestCard` | `components/agents/PermissionRequestCard.tsx` | Inline in the conversation, above the composer | Allow / Deny for a tool call the open run wants to make |

The last two are the same visual family already: both render into `.conversation-interject` /
`.interject-*` CSS classes (`index.css:541-624`) — a bordered `--surface-2` block, `--radius-content`,
inset top highlight. **S1 (conversation + composer) did not touch these** — grepped
`design/mocks/S1/*.md` for "interject" / component names, zero hits — so this is genuinely new
ground, not overlap.

Two of the five (`QuestionsPanel`/`AnswerForm`) are a **separate, older surface**: a full-list tab
that exists because a question can outlive the run that asked it (the operator answers later, from
a list, not from inside a live conversation). `AgentQuestionCard`/`PermissionRequestCard` are newer
and read as more considered — they carry explanatory comments about *why* they look as they do
(step/total vs. queue-depth, `nobodyWaiting`, keyboard shortcuts gated on focus). `QuestionsPanel`/
`AnswerForm` carry none — they are functionally complete but visually the plainest of the five.

## What's already good — do not undo

- `AgentQuestionCard`'s `nobodyWaiting` / batched-answer messaging is a deliberate, reasoned choice
  (see its own comments, lines 67-70, 150-166) — a UX decision already made correctly, not a
  styling gap.
- The `interject-choice` hover/selected states (`index.css:559-584`) already use `--row-hover`,
  `--row-selected`, `--border-hi` — exactly the tokens IDENTITY.md says are "barely used" elsewhere.
  This surface is ahead of the rest of the product here.
- Number-key shortcuts on `AgentQuestionCard` select an option but do not submit — the composer's
  send button confirms. This already matches the "avoid shortcuts that trigger irreversible
  actions" finding below, without having read it.

## External research

**Search: "permission approval dialog UI pattern AI agent allow deny high stakes decision design
2026"**

- Approval requests that carry the agent's accumulated context (what's been done, what this step
  does, what's next) get faster, more accurate decisions than terse approve/deny. Binary
  approve-all-or-abort-all feels wrong for multi-step tasks.
- A three-stage evaluation (DENY rules → ALLOW rules → HUMAN gate) is the general shape; actions
  are classified by reversibility × impact.
- Reviewers need: the exact action, changed state, authority, evidence, uncertainty, alternatives,
  and limits on reversal. Approval UIs should **avoid preselected approval, avoid countdown
  pressure, and avoid keyboard shortcuts on irreversible actions.** Reauthentication close to
  decision time for high-risk actions.
- [Agentic UX: Frontend Design Patterns for AI Agents in 2026](https://zylos.ai/research/2026-05-28-agentic-ux-frontend-design-patterns-ai-agents/)
- [AI Agent Permissions, Approvals, and Fallbacks](https://www.featbit.co/blogs/ai-agent-tool-permissions-approval-fallback)
- [AI Agent Approval UX: What Reviewers Must See](https://edilec.com/blog/ai-11018/approval-screens-high-risk-agent-actions/)
- [Designing For Agentic AI: Practical UX Patterns For Control, Consent, And Accountability — Smashing Magazine](https://www.smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/)

**Search: "chat interface quick reply structured options UI pattern keyboard shortcuts numbered
choices design"**

- Structured choices (buttons/chips) work best to *open* a turn; free text once the conversation
  has direction — matches `AgentQuestionCard`'s own "pick one, or write your own answer below."
- Chat keyboard shortcuts for message-level actions are an established pattern, reinforcing that
  `AgentQuestionCard`'s number-key selection is sound, not novel risk.
- [Chatbot UI Design Patterns and Best Practices 2026](https://fuselabcreative.com/chatbot-interface-design-guide/)
- [Chat UI Design: How to Build Effective Chat Interfaces in 2026 — UXPin](https://www.uxpin.com/studio/blog/chat-user-interface-design/)

## T3 Code — direct analogues, read from sourcemaps

Grepped `index-*.js.map`'s `sources` for permission/approval/confirm/question and pulled the
matching `sourcesContent`. Three files map directly onto this screen's two conversation-interject
components:

**`ConfirmDialogHost.tsx`** — a generic modal (`AlertDialog`) confirm pattern, title/description
parsed from a message string, Cancel / Confirm footer. Architecturally different from AgentWeave's
choice (inline card, not a modal) — that difference is deliberate on AgentWeave's side (the
conversation keeps flowing around the card; a modal would block it) and is **not** something this
pass should import. Read for completeness, not adopted.

**`ComposerPendingApprovalPanel.tsx`** — the closest direct analogue to `PermissionRequestCard`.
Notable structural differences from AgentWeave's version:
- An uppercase, letter-spaced eyebrow ("PENDING APPROVAL") — AgentWeave's `interject-eyebrow` is
  already this pattern (11px, 600 weight, 0.02em tracking), just not uppercase. Confirms the
  existing choice rather than changing it.
- **Categorizes the request into a kind** (`command` / `file-read` / `file-change`) and shows a
  `detailLabel` ("Command" / "File to read" / "File change") *before* the value, not just the raw
  value. AgentWeave's `describe()` returns one bare string with no category — a reader has to infer
  from context what kind of thing they're approving.
- The detail itself renders in a **distinct sub-block**: bordered, `bg-background/70`, `<pre>` with
  `max-h-40 overflow-auto` and monospace. AgentWeave's `describe()` output is a plain paragraph with
  `wordBreak: 'break-all'` sitting directly in the card — no visual separation between "here is what
  I'm asking" and the surrounding chrome, and a long command has nowhere to scroll (it just breaks
  ugly across lines).
- Shows `1/{pendingCount}` when more than one approval is queued. AgentWeave's `AgentQuestionCard`
  already has this (`interject-count`, "step/total"); `PermissionRequestCard` does not — multiple
  simultaneous permission requests today render as a bare stacked list with no count anywhere.

**`ComposerPendingApprovalActions.tsx`** — **four** actions, not two: Cancel turn / Decline /
*Always allow this session* / Approve once. AgentWeave's `PermissionRequestCard` has only Allow /
Deny. "Always allow this session" is a genuine missing **feature**, not a styling gap — flagged per
the pre-authorization to mock what research turns up and note it, not implement it.

## Gaps found in the current AgentWeave components

**`PermissionRequestCard`** (the highest-stakes surface here — this is the "operator stops trusting
the product exactly when it looks cheapest" case from the queue item):
- `Allow` uses `<Button size="sm">` with no `variant`, which defaults to `ghost` (transparent,
  borderless at rest) — the *affirmative* action on the single highest-consequence decision in the
  product renders as the quietest button in the button vocabulary. `Deny` is `variant="outline"`
  (bordered), so visually Deny outranks Allow. Whether that hierarchy is *intentional* restraint
  (do not nudge toward the riskier action) or an oversight is exactly the kind of judgment call P2
  needs to make deliberately rather than by accident — worth a variant that states it either way,
  rather than leaving it silently ambiguous.
- No request-kind badge/label (T3 finding above).
- No distinct "detail" sub-surface for the command/path — currently indistinguishable from body
  text except monospace + word-break.
- No count indicator for multiple simultaneous requests (T3 + `AgentQuestionCard` precedent).
- The expiry-consequence sentence ("will be refused if nobody answers") is good — stating the
  asymmetric, safe-side default in words rather than a countdown matches the research finding to
  avoid countdown pressure. Keep this; do not add a ticking timer.

**`AgentQuestionCard`**: already the most refined of the five. The remaining gap is almost entirely
motion/elevation, not structure — option rows have hover/selected colour but no transition on
selection beyond the instant background swap, and the "no longer waiting" state dims nothing
visually (text-only), so a stale question and a live one are equally prominent at a glance.

**`QuestionsPanel`** / **`AnswerForm`**: the plainest pair. `AnswerForm`'s submit button is
`background: var(--surface-3)` inline styles — outside the `Button` component entirely, so it gets
none of the vocabulary (raised/quiet states, focus ring treatment) the rest of the product now has.
The blocking-question red banner (lines 24-31) is the one place on this screen with real visual
weight; individual question rows inside it are otherwise identical to non-blocking rows apart from
one label colour. No elapsed-vs-timeout warning, no link back to which conversation/agent context
the question came from beyond the agent name, no motion on the `<details>` disclosure.

**`QuestionInterruptCard`**: reasonably considered already (amber tint, compact variant, dismiss).
Gap is mostly motion — appears/disappears with no transition, and compact vs. full are structurally
near-identical rather than a real density adaptation.

## Missing features to mock and flag (not implement)

1. **"Always allow this session" / scoped permission grant** — T3's fourth action. Mocking this
   needs no new visual language, just a third button in the existing vocabulary.
2. **Pending-count indicator on `PermissionRequestCard`** — parity fix, reuses `interject-count`.
3. **Request-kind categorization** for permission requests (command / file-read / file-write /
   other) — enables a colour-coding opportunity IDENTITY.md explicitly calls in scope ("Colour
   *coding* — using the existing semantic and agent scales more systematically"), using existing
   semantic tokens rather than new hues.

## What P2 will build

`design/mocks/S6/<variant>.html`, two or three degrees of refinement per IDENTITY.md, covering all
three surfaces with realistic content: the `PermissionRequestCard` command-approval case (richest,
highest stakes), the `AgentQuestionCard` multi-select case, and the `QuestionsPanel` blocking-list
case. Both themes, all interaction states, per the standard protocol.
