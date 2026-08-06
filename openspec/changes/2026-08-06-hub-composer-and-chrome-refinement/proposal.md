# Composer controls stop looking like buttons, and the project path stops being a string

**Approved:** 2026-08-06, operator

## Why

`2026-08-04-hub-charcoal-visual-refresh` recoloured the Hub and restructured the composer. Operator
review of the result found that the *shapes* are still wrong, and that two things it claimed to fix
were not fixed. Feedback, verbatim where it was specific:

> The folder path in the top still looks ugly. It's still is a string and I don't like the line that
> separates the top navigation and the entire top part. The buttons on the chat box are too square
> and too much like buttons. I don't like it, it breaks the style. Everything is kind of [bordered]
> until you hover. […] The boxes to chose the model etc are too squared. I would like them more
> rounded off and bound to the max size of the text inside them so they look slicker and well fit.
> Also to chose provider and model could we do something like T3 with the icons from each provider?
> Also the conversation box highlights when we're writing or selected. Didn't like that effect. The
> project folder browser is very bad.

Each of these traces to a specific, identifiable place in the code.

**The path is literally still a string.** `ProjectHeader.tsx` computes segments and then does
`pathSegments.join(' › ')`, dropping the result into a 10px paragraph after `2 agents · `. The prior
change described this as a "segmented path", but a joined string inside a `<p>` is a string. It
renders as `2 agents · C:\ › … › testbed › two-codex-agents › workspace` — unscannable, unclickable,
and competing with the project name it sits under.

**The dividing line is real and it is doubled.** `ProjectTabs.tsx` sets
`borderBottom: '1px solid var(--border-region)'` *and* a distinct `background: var(--top)`. The
shell's own spec already forbids exactly this: *"Their boundary SHALL remain subtle and MUST NOT
combine a strong fill contrast with a strong dividing line."* The tab strip does both.

**Every quiet control gains a border box on hover.** `button.tsx` puts
`border border-transparent` in the base class — deliberately, so hover cannot shift layout — and the
`ghost` variant then does `hover:border-[var(--border)]`. The intent was "floats in nothing until
touched"; the result is that touching anything draws a box around it. This is what "everything is
kind of [bordered] until you hover" describes.

**The composer's own pills are the squarest thing on screen.** `ControlPill` in
`ComposerModelControls.tsx` does not use the `Button` primitive at all. It hardcodes
`h-8 rounded border` — Tailwind's bare `rounded` is 4px, against the design system's 6-10px
`--radius-*` scale — with a **permanently visible** border. Its popover hardcodes `min-w-[160px]`,
so a list of short labels is padded out to a fixed width regardless of its content. That is the
"not bound to the max size of the text inside them" complaint precisely.

**The composer surface flashes on focus.** `index.css` gives
`.conversation-composer-surface:focus-within` a primary-tinted border plus a 3px primary ring. It
fires on every click into the textarea.

**The model picker has no provider identity.** Model and provider are chosen from text-only lists.
The agent-creation dialog has the same problem in a more consequential place: provider is the first
decision an operator makes about an agent, and it is presented as a bare `<select>`.

**The directory picker is a 288px-tall dropdown.** `DirectoryPicker.tsx` offers no drive list, no
breadcrumb, no keyboard navigation, no type-ahead, and requires a *double-click* to choose a folder
while a single click navigates into it — an undiscoverable distinction with no affordance.

## Reference

The operator named **t3code** (`https://github.com/pingdotgg/t3code`, MIT) as the target. It was
cloned and read. The relevant patterns:

- `apps/web/src/components/chat/ComposerControl.tsx` — composer controls are
  `h-7 gap-1.5 px-2.5 text-muted-foreground/70 hover:text-foreground/80`. **No border, no
  background, no fill.** A control is muted text plus an icon plus a chevron; hover brightens the
  *text*. Nothing is ever drawn around it.
- `apps/web/src/components/ui/button.tsx` — their `ghost` variant is
  `border-transparent text-foreground [:hover]:bg-accent`. It never colours the border on hover.
  This is the single line that separates their feel from ours.
- `apps/web/src/components/chat/ModelPickerContent.tsx`, `ModelPickerSidebar.tsx`, and
  `modelPickerSearch.ts` — the picker is a provider-grouped list with a favourites rail and
  tokenised fuzzy search that indexes the provider's display name as well as the model's, so typing
  a provider's name finds its models.
- `apps/web/src/components/chat/ProviderInstanceIcon.tsx` and `Icons.tsx` — provider marks are plain
  inline SVG components with the brand's fill baked in, keyed by provider, with a text-initials
  fallback for an unknown provider. No icon library, no webfont, no network fetch.
- `apps/desktop/src/electron/ElectronDialog.ts` — folder choice is `showOpenDialog` with
  `properties: ["openDirectory", "createDirectory"]`, returning a real path, with cancel as a
  first-class outcome.

The last of these does not port directly: the Hub is a FastAPI server with a browser UI, not an
Electron app. See design.md.

## What changes

- **Composer controls become bare.** No resting border, no hover border, no box. Muted text and
  icon; hover brightens the text.
- **Selection pills are fully rounded and sized to their content**, trigger and popover alike. No
  fixed minimum width.
- **The composer surface stops highlighting on focus.** Caret and placeholder already say where
  typing goes.
- **Provider identity is shown as the provider's own mark**, in the composer's model control and in
  the agent-creation dialog, with a labelled fallback for a provider that has no mark.
- **The model list becomes a real picker** — searchable by model or provider name, grouped by
  provider, with operator-marked favourites first, fully keyboard-operable. Today it is a flat
  popover, which is tolerable at six models and is not what the catalog is growing into.
- **The project path becomes real navigable structure**, not concatenated text, and stops sharing a
  line with the agent count.
- **The tab strip's dividing line goes away**, leaving the plane change to do the work the shell
  spec already requires of it.
- **Choosing a project directory opens the operating system's own folder dialog** when the Hub runs
  natively on the operator's machine.

## Impact

- **Affected specs:** `agent-composer`, `hub-workspace-shell`, `local-project-workspace`,
  `operator-agent-creation`
- **Affected code:** `hub/ui/src/components/ui/button.tsx`,
  `components/agents/ComposerModelControls.tsx`, `ComposerConversationRouting.tsx`,
  `ComposerAgentSelector.tsx`, `components/layout/ProjectHeader.tsx`, `ProjectTabs.tsx`,
  `components/projects/DirectoryPicker.tsx`, `ProjectManagerModal.tsx`,
  `components/agents/AgentCreateDialog.tsx`, `components/common/Icon.tsx`, `src/index.css`;
  new Hub-side native folder dialog module
- **Constraint carried forward:** `Icon` wraps `lucide-react` and there is exactly one icon system.
  Provider marks are added as inline SVG within that component, not as a second library.

## Out of scope

- The charcoal palette itself. Colour is not what the feedback is about; shape and weight are.
- Docker-mode directory browsing, which keeps today's in-app browser as its only option.
