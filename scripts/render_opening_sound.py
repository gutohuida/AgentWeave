"""Render AgentWeave's launch sounds from the brand synth: src/agentweave/assets/opening*.wav.

agentweave-opens-on-the-thread. brand/sound/agentweave-sound.js is the one synth (the struck
glass, operator's pick 2026-10-23); this loads it into headless Chromium and renders `open` and
`openShort` with an OfflineAudioContext, so the CLI's files are the very sound the operator
approved in the browser. The first WAVs came from a separate Python copy that drifted out of tune.

It also writes src/agentweave/assets/opening-sound.json, pinning the synth's hash and each file's;
tests/test_splash.py fails when the synth changes and this has not been re-run.

    py -3.11 scripts/render_opening_sound.py
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SYNTH = ROOT / "brand" / "sound" / "agentweave-sound.js"
ASSETS = ROOT / "src" / "agentweave" / "assets"
FILES = {"opening.wav": "open", "opening-short.wav": "openShort"}

RENDER = """async (name) => {
  const bytes = await AgentWeaveSound.renderWav(name, { key: 'D', sampleRate: 44100 });
  let s = ''; for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(s);
}"""


def main() -> None:
    manifest = {
        "source": "brand/sound/agentweave-sound.js",
        "source_sha256": hashlib.sha256(SYNTH.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "key": "D",
        "sample_rate": 44100,
        "files": {},
    }
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("about:blank")
        page.add_script_tag(content=SYNTH.read_text(encoding="utf-8"))
        for filename, sound in FILES.items():
            data = base64.b64decode(page.evaluate(RENDER, sound))
            (ASSETS / filename).write_bytes(data)
            manifest["files"][filename] = hashlib.sha256(data).hexdigest()
            print(f"{filename}: {len(data) // 1024} KB")
        browser.close()
    (ASSETS / "opening-sound.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
