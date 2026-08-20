# Exploration — How long an open document should follow you (2026-08-20)

**Status:** Stub. One of eight explore pages opened 2026-08-20 covering the open backlog. **Partially
fixed already** — this page exists to settle whether the remaining half should be built.

**Origin:** item 7 of the operator's twelve:

> *"Leaving a conversation detaches the open spec."*

---

## What was already shipped, and deliberately scoped narrow

Commit `524ccc2` fixed **one** round trip: open a spec, go to agent settings, press Back — the spec
is still attached.

- `hub/ui/src/lib/navigation.ts` — `agentSettingsBackDestination` takes an optional `document`.
- `hub/ui/src/App.tsx:169` — a `lastConversationDocument` ref, declared above the bootstrap
  early-returns (they are conditional; a hook below them is a rules-of-hooks violation).
- `hub/ui/src/App.tsx:243-247` — `openDocument` falls back to the remembered value **only** on
  `agent-settings`.

**A wider fix was written first and reverted.** Remembering the document across every
non-conversation destination broke an existing test —
`App-mount.test.tsx`'s *"does not resurrect a document when arriving from a project tab"* — whose
recorded rationale is:

> *"the memory is of what is on screen, not a preference that outlives leaving the surface."*

The narrow fix's reasoning: settings is a **detour** about the conversation you are in, left by a
Back button. A project tab is a **departure**.

## The open question this page exists for

**Was the operator complaining about agent settings, or about project tabs and the Spec screen
too?** This was asked at the end of the last session and never answered.

It matters because widening the fix means **overturning a test and its stated rationale** — which is
a decision about what the product believes, not a bug fix. Doing that silently would be wrong; doing
it on the operator's say-so is fine.

## Open questions

1. **Which navigations did the operator actually try?** The answer may be that the narrow fix already
   covers the real complaint.
2. **Is "detour versus departure" the right distinction at all?** It is a clean line, but it is one I
   drew, not one the operator stated. There may be a simpler rule: the document stays until you open
   a different one, full stop.
3. **If widened, what replaces the overturned test?** The rationale it encodes is not obviously
   wrong; a replacement should say what the new belief is, not just delete the old assertion.
4. **Does the Spec screen count as leaving?** Arguably the least like a departure of all of them —
   you are going to look at specs.
5. **Should this survive a reload, not just a navigation?** Currently a ref, so no. That is a
   different and larger claim about persistence.

## Known gap in coverage

Handoff 0063 records it plainly: an App-level test for the settings round trip **was written and
removed**. Inside the fully mounted `App`, clicking `agent-menu-proj-test-claude` did not resolve a
`menuitem` named "Agent settings" (`rowMenus.test.tsx` gets it by rendering `Sidebar` directly with
its own mocks). The behaviour is covered by two `navigation.ts` unit tests instead — so **the
App-level wiring that decides *when* to pass the remembered document is not directly covered.**

Whatever this page concludes, that gap should be closed, because it is exactly the wiring any
widening would change.

## Size

Small in code either way. The work is one answer from the operator plus, if widened, an honest
rewrite of the test that currently says the opposite.
