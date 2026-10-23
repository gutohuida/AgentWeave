# Sound

AgentWeave's sound is **the struck glass** (S4b; operator's pick in sound round 2, 2026-10-23,
https://claude.ai/artifact/RfWBxnGPvLVfGohYbHnPbr, after round 1
https://claude.ai/artifact/1X8YWtSap3s77VA314QPMH).

One instrument: each note is two sine tones that begin slightly apart and settle into one clean
tone, struck by a small hard mallet. Murk becomes clear: "nothing appears out of thin air". A
failure is the one sound that never settles.

| Sound | When | Shape |
|---|---|---|
| `open` | The splash on a cold start | One note per corner of the W (D4 A4 D5 E5 A5), panned left to right with the thread, then a soft D-A-F♯ chord as the name appears |
| `openShort` | The splash on a warm start | D4, D5, A5 at the left end, the loop and the right end |
| `ask` | An agent asks, or wants a permission | Rises: A4 → E5 |
| `done` | Work finished | Steps down and resolves: E5 → D5 |
| `fail` | Stalled or failed | Low and falling, never settles: A3 → F3 |
| `ready` | The app is ready after a long start | A bright pair: D5 + A5 |

`agentweave-sound.js` is the single source, with no dependencies. The CLI's launch WAVs
(`src/agentweave/assets/opening*.wav`) are rendered from it by `scripts/render_opening_sound.py`
(OfflineAudioContext in headless Chromium), and `opening-sound.json` pins the synth's hash, so a
change to the synth without a re-render fails `tests/test_splash.py`. The app's notification
sounds play the same file live.

Rules: few sounds, used sparingly; notifications shorter than the opening; never every alert at
the same urgency; the operator can turn sound off (`AGENTWEAVE_SOUND=0` for the opening).
