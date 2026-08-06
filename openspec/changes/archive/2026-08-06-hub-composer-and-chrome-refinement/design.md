# Design — composer and chrome refinement

## Decision 1 — where "bare control" lives

`ControlPill` currently bypasses the `Button` primitive and re-implements a trigger badly. Two ways
to fix that.

**Rejected: restyle `ControlPill` in place.** It leaves the composer's controls as a private visual
dialect, and leaves `ghost`'s `hover:border` to keep drawing boxes everywhere else the operator
mentioned ("everything is kind of bordered until you hover" was not scoped to the composer).

**Chosen: fix the primitive, then build the pill on it.**

1. `ghost` stops colouring its border on hover. It keeps `border border-transparent` in the base —
   that rule exists so gaining emphasis never shifts layout by a pixel, and it is correct. What
   changes is that hover expresses itself as background and text colour only. This matches t3code's
   ghost exactly and is a one-line change with repo-wide effect.
2. A composer-control appearance is added as a shared thing every composer trigger uses — the
   AgentWeave counterpart of t3code's `composerControlClassName`. `ControlPill`,
   `ComposerConversationRouting`, and `ComposerAgentSelector` all render through it, so they cannot
   drift apart again.

Because step 1 is repo-wide, task 1.4 audits every `variant="ghost"` call site for a control that
was *relying* on the hover border to be legible.

## Decision 2 — "bound to the max size of the text inside"

Two separate sizing bugs share this complaint.

- **The trigger** is already content-width, but reads boxy because of `h-8` with `rounded` (4px) and
  a visible border. Removing the border and going fully rounded fixes it; no layout change needed.
- **The popover** hardcodes `min-w-[160px]`. That is the actual "not bound to the text" defect: a
  list of `Low / Medium / High` is stretched to 160px. It becomes content-width, with a *maximum*
  so a long model label truncates rather than pushing the popover off-screen. A minimum is dropped
  entirely.

"Fully rounded" means the pill's radius makes its ends semicircular at its own height, so it stays
a pill regardless of label length. It does not mean adding a new fixed radius token.

## Decision 3 — provider marks under the one-icon-system rule

`CLAUDE.md` is explicit: `Icon` wraps `lucide-react`; the Material Symbols webfont was removed
because it fetched from a CDN with `display=block` and held every icon invisible until the request
landed; **do not reintroduce a second icon system.**

Brand marks for OpenAI and Anthropic are not in lucide and never will be. The compliant path is the
one t3code uses: plain inline SVG components. They add no dependency, no webfont, no network
request — the exact failure mode the rule was written against. They live inside the existing `Icon`
module so there remains one import site for iconography.

Provider marks are **keyed off the catalog's provider identity**, and an unknown provider falls back
to a text label rather than a wrong mark. `2026-08-04-hub-model-control-and-provisioning` established
that no provider name is hardcoded in `ComposerModelControls`; a lookup keyed by catalog identity
with a graceful miss preserves that, whereas a hardcoded `if provider === 'codex'` would break it.
The existing source-contract test that scans that component for provider names must keep passing.

Brand marks are the providers' trademarks, not t3code's; MIT covers the surrounding code. Marks
should be taken from each provider's own brand assets where published.

## Decision 4 — the native folder dialog

t3code calls Electron's `showOpenDialog`. The Hub has no Electron process. The browser's
`showDirectoryPicker()` is not a substitute — it returns an opaque handle, deliberately never a
filesystem path, and the Hub needs a path.

What remains is that **the Hub's own Python process runs on the operator's machine in native mode**
and can open a host folder dialog itself. That is the only route to a real native picker here, and
it is available precisely because this is a local app.

Consequences that must be designed for, not discovered:

- **The dialog appears on the Hub host's desktop.** In native mode that is the same machine as the
  browser, so this is correct. It is *not* correct in Docker mode, which is why native mode gates it.
- **It blocks.** It must never run on the event loop. It runs off-loop with a timeout, and a
  timeout is a normal outcome, not a crash.
- **Cancel is a first-class result**, distinct from failure, and must not be reported as an error.
- **Concurrency.** A second request while a dialog is open must not open a second dialog.
- **It can be unavailable** — no desktop session, a headless host, a platform without a supported
  dialog. Availability is therefore something the frontend *asks about* before offering the button,
  rather than something it assumes and then apologises for.

The in-app browser is not deleted. It remains the path for Docker mode and for a host where the
dialog is unavailable, and typing a path directly stays available and unaffected, as
`2026-08-04-hub-model-control-and-provisioning` established.

The implementation is host-specific (Windows first, since that is the operator's platform). Platform
support is a capability the Hub reports, not a promise it makes. Nothing about the exposed shape
should assume a single platform.

## Decision 5 — the project path

The path is doing two jobs badly: identifying the project's location, and padding out the
agent-count line. It gets its own row, and becomes per-segment elements rather than a joined string,
so segments can be styled, truncated, and interacted with individually.

Elision stays — `elidePathSegments` and its tests are fine, and a deep path must not push the header
around. What changes is that its output is rendered as structure. The full path stays available on
hover, as today.

Whether a segment is clickable is left to implementation: a segment that navigates nowhere should
not look interactive. The requirement is that the path is structure, not that every segment is a
link.

## Decision 6 — the tab strip boundary

`hub-workspace-shell` already says a plane boundary "MUST NOT combine a strong fill contrast with a
strong dividing line." `ProjectTabs` does both. The line goes; the `var(--top)` plane stays and does
the separating. If, in review, the plane alone proves too weak at this boundary, the correction is
to strengthen the plane — not to put the line back.

## Verification constraints inherited

Three checks have been unverifiable across several changes and remain so unless tooling changes.
They are restated so they are not quietly dropped again:

- **Reduced motion** — `preview_set_appearance` emulates `prefers-color-scheme` only.
- **Numeric contrast ratios** — no automated checker available in-session.
- **Narrow-viewport (390×800) live check** — needs interactive resize.

Where these apply, `tasks.md` says so explicitly rather than leaving a bare unchecked box.

## Risks

- **`ghost`'s hover border is repo-wide.** A control somewhere may depend on it. Mitigated by the
  task 1.4 audit.
- **A blocking host dialog is a new class of thing for this codebase.** Mitigated by treating
  timeout, cancel, concurrent-request, and unavailable as designed outcomes with their own
  requirements.
- **Provider marks are brand assets.** Mitigated by sourcing from providers' own brand pages and
  keeping the fallback path real, so a missing mark degrades to a label rather than breaking.
