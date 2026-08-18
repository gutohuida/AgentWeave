#!/usr/bin/env python3
"""Generate the provisional AgentWeave mark and write it everywhere it is used.

Run with `py -3.11 scripts/generate_icon.py`. Requires Pillow (already a dev
dependency of this repo). Not wired into any build step -- the mark is
provisional and regenerating it is a deliberate, occasional action, not part
of every `npm run build`.

Outputs:
  src/agentweave/assets/icon.ico   -- multi-size .ico for the pywebview window
  hub/ui/public/favicon.ico        -- same file, for the web favicon
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent

# Matches hub/ui/src/index.css's dark-theme tokens: --bg, --blue, --purple.
BG = (10, 10, 11, 255)
STRAND_BLUE = (124, 140, 255, 255)
STRAND_PURPLE = (168, 85, 247, 255)

ICO_SIZES = [16, 32, 48, 64, 128, 256]
CANVAS = 256


def _lerp(p0: tuple[float, float], p1: tuple[float, float], t: float) -> tuple[float, float]:
    return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)


def build_mark(size: int = CANVAS) -> Image.Image:
    """A rounded badge with two diagonal ribbons crossing in a woven
    over/under -- the blue ribbon passes over unbroken, the purple ribbon
    breaks at the crossing to read as passing under it."""
    scale = size / CANVAS
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    radius = 56 * scale
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=BG)

    margin = 40 * scale
    ribbon_w = 46 * scale
    center = (size / 2, size / 2)

    top_left = (margin, margin)
    bottom_right = (size - margin, size - margin)
    bottom_left = (margin, size - margin)
    top_right = (size - margin, margin)

    # Blue ribbon: unbroken, top-left to bottom-right -- drawn first, "under"
    # everything except where the purple ribbon explicitly breaks for it.
    draw.line([top_left, bottom_right], fill=STRAND_BLUE, width=round(ribbon_w), joint="curve")
    for end in (top_left, bottom_right):
        draw.ellipse(
            [
                end[0] - ribbon_w / 2,
                end[1] - ribbon_w / 2,
                end[0] + ribbon_w / 2,
                end[1] + ribbon_w / 2,
            ],
            fill=STRAND_BLUE,
        )

    # Purple ribbon: bottom-left to top-right, split into two segments that
    # stop short of the centre so the blue ribbon reads as passing over it.
    gap_t = (ribbon_w * 0.9) / (math.dist(bottom_left, top_right) / 2)
    seg1_end = _lerp(bottom_left, center, 1 - gap_t)
    seg2_start = _lerp(center, top_right, gap_t)
    for p0, p1 in ((bottom_left, seg1_end), (seg2_start, top_right)):
        draw.line([p0, p1], fill=STRAND_PURPLE, width=round(ribbon_w), joint="curve")
    for end in (bottom_left, top_right):
        draw.ellipse(
            [
                end[0] - ribbon_w / 2,
                end[1] - ribbon_w / 2,
                end[0] + ribbon_w / 2,
                end[1] + ribbon_w / 2,
            ],
            fill=STRAND_PURPLE,
        )
    for seg_end in (seg1_end, seg2_start):
        draw.ellipse(
            [
                seg_end[0] - ribbon_w / 2,
                seg_end[1] - ribbon_w / 2,
                seg_end[0] + ribbon_w / 2,
                seg_end[1] + ribbon_w / 2,
            ],
            fill=STRAND_PURPLE,
        )

    # Re-clip to the rounded badge -- the ribbons' round end caps can poke
    # a pixel or two past the corner radius.
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    badge.paste(img, (0, 0), mask)
    return badge


def write_ico(path: Path) -> None:
    base = build_mark(CANVAS)
    path.parent.mkdir(parents=True, exist_ok=True)
    base.save(path, format="ICO", sizes=[(s, s) for s in ICO_SIZES])


def write_preview(path: Path, size: int = CANVAS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    build_mark(size).save(path, format="PNG")


if __name__ == "__main__":
    cli_ico = REPO_ROOT / "src" / "agentweave" / "assets" / "icon.ico"
    favicon_ico = REPO_ROOT / "hub" / "ui" / "public" / "favicon.ico"
    preview_png = REPO_ROOT / ".claude" / "autonomous" / "scratch" / "icon_preview.png"

    write_ico(cli_ico)
    write_ico(favicon_ico)
    write_preview(preview_png)

    print(f"wrote {cli_ico}")
    print(f"wrote {favicon_ico}")
    print(f"wrote {preview_png}")
