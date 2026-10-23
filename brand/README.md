# AgentWeave brand kit

The visual identity of AgentWeave, kept in the repository. It mirrors the identity kit built on
2026-10-22 as a Design System artifact (https://claude.ai/artifact/TUUKwciug61DCayLS7XLHn). **This
folder is now the source of truth**: when the two disagree, change this folder first, then
republish the artifact.

| Path | What |
|---|---|
| `README.md` | This file: the brand book (story, voice, logo, colour, type, motion, icons). |
| `identity-record.md` | The full record: the brief in the operator's words, every exploration round and why options were rejected, the mark's exact geometry, the colour measurements, where each piece shipped in the code, and what is still open. |
| `tokens.json` | Brand and app tokens (colour per theme, type, radius), in the Design System artifact's list format. The app's own values live in `hub/ui/src/index.css`. |
| `logos/` | Every logo file: SVG (real mask cut-outs) and PNG rasters. See `logos/README.md`. |
| `sound/` | The sound identity: the struck-glass synth (`agentweave-sound.js`) that the launch WAVs are rendered from and the app plays, and its guide. |
| `components/<Name>/` | Guidelines (`README.md`) and a standalone preview (`preview.html`, opens in a browser) for Logo, AppIcon, LoadingThread and the kit's Cover. |

Copies already in use elsewhere: `docs/assets/agentweave-*.svg` (docs site),
`hub/ui/src/assets/brand/favicon.svg` and `hub/ui/src/components/common/BrandLoop.tsx` (the app),
`hub/ui/public/favicon.ico` and `src/agentweave/assets/icon.ico` (browser and window icons).

---

AgentWeave runs your AI factory in the open. Agents from different companies work together inside your software process, and every artifact they produce, every step and every decision stays visible and traceable. The identity says one thing: **nothing appears out of thin air.**

## The story

Tell it in this order, in these words or close to them:

> AgentWeave started as a way to get agents from different companies working together, each doing what it does best. Then the problem showed: work appeared out of thin air. No one could say who made it, or why. So AgentWeave grew into the place where you run your AI factory in the open: every artifact cared for, every step visible, every decision traceable. A red thread runs through all of it.

The red thread is real history. In Goethe's *Elective Affinities* (1809), every rope of the British Royal Navy has a red thread twisted through it, so even a small cut piece can be traced back to the Crown. "Following the red thread" has meant traceability ever since. Madder was the classic red dye.

## Voice

- **Tagline:** "Run your AI factory in the open." Use it beside the name everywhere there is room for one line (PyPI summary, GitHub About, docs subtitle).
- **Hero headline:** "Nothing appears out of thin air." Use it only where the story follows (README top, docs landing).
- Feel: **future, stability, visibility.** Never murky, difficult or convoluted. When a sentence gets clever, make it plain.
- Write for teams building with AI, developers and business people together. Not for vibe coders: no hype, no magic, no "just".
- In the app, the words are the operator's: no event names, raw ids, cron strings or file instructions on screen. Ids go in a tooltip or a copy action.
- Active voice; a control says exactly what happens ("Recreate the tasks"), and its result says it happened.
- No emoji. No sparkles or "AI magic" imagery.

## Logo: the loop

One thread draws the W of Weave. At the centre it loops back over itself: the human in the loop, the point where a person sees what the agents made before the work goes on.

- Use `agentweave-loop.svg` (master drawing) at 48px and up, and `agentweave-loop-small.svg` (heavier thread, opened loop) from 16px to 32px. Between 33 and 47px either works; prefer small in UI chrome.
- Thread colour: `madder` on light and dark grounds (use the `-on-dark` file on dark). Single-ink contexts: `agentweave-loop-ink.svg` on light, `agentweave-loop-white.svg` on dark or on photos. No other colours.
- The gaps are real cut-outs, so the mark sits on any ground.
- Clear space: keep a quarter of the mark's width empty on every side. Minimum size: 16px, small drawing.
- Lockup: loop, then "AgentWeave" in `wordmark` (or `display` weight on brand surfaces), gap of half the loop's width, name vertically centred on the loop.
- In the app's sidebar head the order is loop, name, then the live-connection dot. The dot stays: it is the only report of the connection on screen.
- Don't: recolour the thread (no verdigris, no gradients), outline it, rotate it, close the gap at the crossing, detach the loop, add a sparkle, or set it on a madder ground.

## App icon and favicon

The ink tile: `ink-tile` ground, `madder` (dark value) thread, corner `radius-icon`. `agentweave-app-icon.svg` uses the master drawing (app and taskbar icons, 48px and up); `agentweave-favicon.svg` uses the small drawing (browser tabs). PNGs are provided at 16, 32, 48, 180 (Apple touch) and 512.

## Colour

- The app stays **monochrome**: `primary` fills buttons, `text`/`text-2`/`text-3` carry hierarchy, surfaces lift with `surface`, `surface-2`, `surface-3`. The accent hue never fills a control.
- `verdigris` is the one accent, reached only through `ring` (focus, selection) and `rail-marker`. Verdigris is the patina that protects copper: stability.
- `madder` is the brand: the logo's thread and brand surfaces outside the app. Inside the app it appears in the logo only, because anywhere else it reads as an error (`destructive`) or as Claude (`provider-claude`).
- Status colours keep their meaning and always come with a word or icon: `destructive` errors, `green` success and live, `amber` needs you or waiting, `blue` info.
- Agents take `agent-1` … `agent-8` by registration order. `agent-2` is magenta so no agent looks like the accent.
- `provider-claude` is Anthropic's colour, for Claude's mark only.
- `text-3` holds 3:1, not 4.5:1, by design: use it for meta and large text, never for body copy.

## Type

- `sans` is DM Sans (self-hosted in the app as DM Sans Variable); `mono` is JetBrains Mono. Its rounded, even strokes match the loop's thread.
- App text uses `body`, `title`, `small`, `label` and `code`. Brand surfaces add `display` and `tagline`; neither appears in the app.
- Set headings with balanced wrapping; keep running text near 65 characters wide.

## Shape and motion

- Radii: `radius-lg` (10px) is the base, with `radius-sm`, `radius-md`, `radius-xl` derived from it; `radius-content` (24px) for self-contained results.
- Motion is quiet and short: 150, 250 and 500ms on cubic-bezier(0.16, 1, 0.3, 1). The brand motion is the thread: the loading thread "weaves through" (draws in, then its tail follows out, every 1.8s) and is every loading state in the app; the opening splash is the "shuttle pass", a glint running ahead of the thread as it draws. Under reduced motion both stand still. Sound: the struck glass, one synth in `sound/` (see `sound/README.md`); notifications: `identity-record.md` §7.

## Iconography

- UI icons are lucide, through the app's `Icon` component. Provider and file-type marks come from simple-icons through the same component (`brand:<key>`), only where a mark is published, in the brand's colour only when it clears contrast on both grounds.
- No icon font, no emoji, no third icon source without the operator deciding it.
