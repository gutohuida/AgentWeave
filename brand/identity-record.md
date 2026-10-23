# AgentWeave identity: the complete record

Written 2026-10-23 from the identity session of 2026-10-22 (handoff 0206), its four exploration
artifacts and the published kit. It records what was decided, why, and what was turned down, so
the next person changing the brand does not reopen settled questions. The brand book itself is
`brand/README.md`; this file is the history and the measurements behind it.

## 1. The brief, in the operator's words

Given on 2026-10-22, answering "who is it for, how should it feel, what sets it apart":

1. **Audience.** "People that want to create a factory with AI. Want AI woven into their processes.
   Companies that need more traceability on what's happening and why. This is not for vibe coders
   but a way to make AI work with developers and business people. A way that works and it's woven
   into the SDLC."
2. **Feel.** "Future, stability, visibility." Never: "murky, difficult, convoluted."
3. **Differentiator.** "Other tools don't have a good visibility and easy control over the agents.
   For you to reach an agentic workflow it's hard, convoluted and ugly. Or they pay too much
   attention to the agents and not the artifacts of the SDLC."
4. **Where the logo lives.** Unknown at the time; designed for favicon, app and taskbar icon, docs,
   GitHub and PyPI, README.
5. **Concept.** "Agents are woven throughout the entire development process. I want AgentWeave to
   be one place where you can weave your agents and processes together to develop." The name
   AgentWeave stays.

## 2. The origin story

In the operator's words: "The project evolved a bunch. First it was a way to connect multiple
agents working together from different companies so I could best utilize the strengths of each.
But then I noticed that I had no visibility on what was happening. Things just *poof* appeared out
of thin air with no control whatsoever, and I couldn't understand a thing. So AgentWeave evolved to
give you the entire control of your AI factory, with care for each of the artifacts generated, and
giving you the power to supervise and know what's happening. Transparency."

The told version (use this one in public copy):

> AgentWeave started as a way to get agents from different companies working together, each doing
> what it does best. Then the problem showed: work appeared out of thin air. No one could say who
> made it, or why. So AgentWeave grew into the place where you run your AI factory in the open:
> every artifact cared for, every step visible, every decision traceable. A red thread runs through
> all of it.

**The red thread.** In Goethe's *Elective Affinities* (1809), every rope of the British Royal Navy
has a red thread twisted through it, so even a small cut piece can be traced back to the Crown.
"Following the red thread" has meant traceability ever since. Madder was the classic red dye. In
AgentWeave the thread is the chain requirement → task → run → evidence → review → merge, where every
step names who took it.

## 3. How the mark was found

| Round | Artifact | What it showed | Outcome |
|---|---|---|---|
| R1 | https://claude.ai/artifact/QB8Yb689N3JrV9rw8BMBqA | Six directions, A–F | Operator liked **B (Interlaced W)** and **F (Woven A)**. |
| R2 | https://claude.ai/artifact/BKcmGbC5Vj7evBPcvV71Wz | Variants of B and F, after research into how logo designers work | **F3/F4 "lashed A" rejected**: "very similar" to an existing logo. **B4 (W app tile)** and **F2 (soft A)** liked. But the marks overall were "too complex, too much was happening and they were too straightforward". The operator asked for something simpler that **tells a story**. |
| R3 | https://claude.ai/artifact/PaxKnJeD3EkStPDx27jhCh | Five stories from weaving history: the flying shuttle, **the loop W** (human in the loop), the Jacquard punched card, the selvedge, the trace | Pick: **S2 "the loop"**, in **madder & verdigris**. |
| R4 | https://claude.ai/artifact/64fhekpHoZ9VmBatGoN3p5 | The red-thread narrative; two drawings of the loop; colour proposal for the app; app icon tiles; tagline and headline | Operator picked the **ink tile** app icon and accepted the recommendations on tagline, headline and the sidebar order. |
| Kit | https://claude.ai/artifact/TUUKwciug61DCayLS7XLHn | Design System artifact: brand book, tokens, logo assets, Logo / AppIcon / LoadingThread previews | Published 2026-10-22; mirrored into `brand/` on 2026-10-23. |

Working rules learned along the way, for any future change to the mark:

- Keep a mark to **four parts or fewer**.
- Judge it **in monochrome first**; colour comes after the shape works.
- **Check 16 px by rendering it**, never by eye at large size (headless Edge screenshots work on
  this machine). The R3 drawing closed up at 16 px, which is why there are two drawings.
- Lead every option with **its story**: the operator chooses stories, not shapes.

## 4. The mark: the loop

One thread draws the W of Weave. At the centre it loops back over itself: the human in the loop,
the point where a person sees what the agents made before the work goes on. The thread passes
*under* itself at the crossing, cut by a real SVG mask, so the mark sits on any ground.

Both drawings sit on a 64-unit grid, round caps and joins, as two paths: path A (left stroke up into
the loop, masked where B crosses it) and path B (out of the loop, down and up the right stroke).

| Drawing | Use | Stroke | Mask gap | Path A | Path B |
|---|---|---|---|---|---|
| **Master** | 48 px and up | 5.5 | 9.5 | `M9 15 L21 50 L34 21 C38.6 12.5 37.6 6 32 6` | `M32 6 C26.4 6 25.4 12.5 30 21 L43 50 L55 15` |
| **Small** | 16–32 px (either at 33–47; prefer small in UI chrome) | 8 | 16 | `M7 18 L19 54 L33.5 25 C40 14 39.5 6 32 6` | `M32 6 C24.5 6 24 14 30.5 25 L45 54 L57 18` |

The small drawing has a heavier thread and an opened loop with a 4-unit gap, so the loop survives at
16 px.

**App icon and favicon (the ink tile).** A 64×64 tile, `rx 14` (22%), fill ink `#15171C`, the loop
scaled 0.66 about (32, 33) in madder dark `#CC4630`. App icon = master drawing; favicon = small
drawing. The tile is the same in both themes. The madder tile was offered and not chosen.

## 5. Colour

| Token | Light | Dark | Role |
|---|---|---|---|
| `madder` (`--brand-madder`) | `#B03A26` | `#CC4630` | The brand thread. Logo and brand surfaces only. |
| `verdigris` (`--ring`, `--rail-marker`) | `#1D6B6E` | `#5FB3B3` | The app's one accent hue: focus and selection only. |
| `ink-tile` | `#15171C` | `#15171C` | App icon and favicon ground. |
| `agent-2` | `#B8399A` | `#E066C0` | Magenta, was teal. |

Why each value:

- **Madder stays out of the app.** Anywhere but the logo it reads as an error (`--destructive`
  `#f4525f`/`#dc2f3c`) or as Claude (`--provider-claude` `#d97757`). Mark contrast 4.2:1 on the dark
  ground, 5.8:1 on light.
- **R3's dark madder `#F07F68` was rejected**: OKLab ΔE 5 from Claude's `#d97757`, so the logo
  would have read as Anthropic's.
- **Verdigris replaced indigo** (`#7c8cff` / `#5063d8`) as the single accent. Verdigris is the
  patina that protects copper: stability. 8.1:1 on the dark ground, 6.0:1 on light. The app stays
  monochrome; the accent never fills a control.
- **`agent-2` moved from teal (`#2fd4c8` / `#0f9c92`) to magenta**, because teal was ΔE 9 from
  verdigris and an agent would have looked like the selection colour.

## 6. Words

- **Tagline:** "Run your AI factory in the open." Beside the name wherever there is one line of room.
- **Hero headline:** "Nothing appears out of thin air." Only where the story follows it.
- **Sidebar head order:** loop, name, then the live-connection dot (the dot is the only on-screen
  report of the connection, so it stays).
- Voice rules are in `brand/README.md` § Voice: plain, active, no hype, no emoji, no "AI magic".

## 7. Motion

**The loading thread: "weave through"** (operator's pick, 2026-10-23, in the thread lab
https://claude.ai/artifact/GniK2BGBQJzh2ouG3boTpN). The thread draws in from the left end through
the loop to the right end, then its tail follows it out the far end, continuously, on a **1.8 s**
cycle with no fade:

- path A's stretch grows over 0–25% of the cycle, path B's over 25–50%; the tail runs through A over
  50–75% and through B over 75–100%; each quarter eases in and out, so the thread pauses briefly at
  the loop, where the human is;
- both paths use `pathLength="1"`; a visible window [s, e] is `stroke-dasharray: e-s 2;
  stroke-dashoffset: -s`, and the mask's crossing cut follows path B, so the gap opens only when B
  reaches the crossing;
- under `prefers-reduced-motion` it stands still, fully drawn.

Sizes: 64 px (master drawing) for a panel, 24 px inline beside its label, 16 px inside a button in
the text colour. It is every loading state in the app, held back for 300 ms so quick loads show
nothing. It replaced the kit's first motion ("draw, hold, fade, every 1.6 s"), which read as
restarting on long waits.

**The opening splash: "shuttle pass"** (operator's pick, 2026-10-23). The window opens at once and
a bright glint runs ahead of the madder thread as it draws the W, like a shuttle crossing the loom;
then the name and tagline appear. A cold open lasts at least about 2 s and keeps weaving until the
Hub is ready; a warm open (Hub already running) plays a short 1.2 s version.

**Sound** (decided 2026-10-23, two rounds): **the struck glass**. Round 1 offered five stories (taut
thread, shuttle crossing, punched card, in the open, call and answer); the operator kept the taut
thread and in the open; round 2 varied both and added hybrids; the pick was S4b, struck glass.
Each note is two tones that begin slightly apart and settle into one, struck by a small mallet: murk
becoming clear. The first shipped opening (a plucked string rendered by a separate Python copy of
the synth) drifted up to ~24 cents out of tune with a metallic reverb, so the synth now lives once,
in `brand/sound/agentweave-sound.js`, and the launch WAVs are rendered from it. Sounds and shapes:
`brand/sound/README.md`.

**Notifications** (decided 2026-10-23): every project on the Hub notifies, labelled with its name.
Window in front: a toast and a quiet sound. Window in the background: the sound, a count in the
title and a flashing taskbar button. One sound at most every few seconds; a burst is one sound and
one grouped toast. Sounds by default for "needs you" and "stalled or failed"; "done" is off by
default.

## 8. Where it shipped

Commit `4b3eb07` (Tier 0, visuals only), merged to master as `e23cbc6` on 2026-10-22:

- `hub/ui/src/index.css`: `--ring` verdigris, `--agent-2` magenta, new `--brand-madder`.
- `hub/ui/src/components/common/BrandLoop.tsx`: the in-app mark (small drawing, `useId` mask; mask
  fills are `white`/`black` because the hubVisualLanguage test refuses hex).
- `hub/ui/src/components/layout/Sidebar.tsx`: loop, name, dot.
- `hub/ui/index.html` + `hub/ui/src/assets/brand/favicon.svg`: SVG favicon served through Vite's
  `/assets/` (the Hub's SPA fallback answers `/favicon.ico` with `index.html`).
- `hub/ui/public/favicon.ico`, `src/agentweave/assets/icon.ico`: regenerated icons.
- `mkdocs.yml`, `docs/stylesheets/brand.css`, `docs/assets/agentweave-*.svg`: docs theme.
- `README.md`: logo, tagline, origin story.

## 9. Open

As of 2026-10-23:

- `pyproject.toml`, `hub/pyproject.toml` and `mkdocs.yml` `site_description` still say
  "Multi-agent AI collaboration framework…"; the tagline was offered as the replacement and not
  yet answered.
- No Apple touch icon in the app (the PNG exists here in `logos/`).
- Built 2026-10-23: the loading thread in the app (`the-thread-is-how-agentweave-shows-it-is-loading`)
  and the opening splash with its sound (`agentweave-opens-on-the-thread`: the window opens at once
  on `src/agentweave/assets/splash.html`, the CLI plays `opening.wav` / `opening-short.wav`, rendered from
  `brand/sound/agentweave-sound.js` by `scripts/render_opening_sound.py`; `AGENTWEAVE_SOUND=0` silences it). Next: sounded notifications,
  then a test of real Windows notifications.
