"""Render AgentWeave's opening sound: src/agentweave/assets/opening.wav and opening-short.wav.

agentweave-opens-on-the-thread. One plucked-thread instrument (Karplus-Strong), the settings the
operator kept in the thread lab (https://claude.ai/artifact/GniK2BGBQJzh2ouG3boTpN): key D,
brightness 0.45, ring 0.55, room 0.18. The notes land when the splash's thread passes each corner
of the W, panned left to right with it, then a soft D-A-F# chord as the name appears.

The timings mirror src/agentweave/assets/splash.html: the head runs easeOutCubic(t / 1.3) along
path A then path B; a warm open plays the intro 1.8x faster. Seeded, so a rerun writes the same
bytes. Stdlib only:

    py -3.11 scripts/make_opening_sound.py
"""

from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "src" / "agentweave" / "assets"
RATE = 22050
ROOT_D4 = 293.66
BRIGHT, RING, ROOM = 0.45, 0.55, 0.18
DRAW, NAME_AT, WARM_SPEED = 1.3, 1.3, 1.8

# The master drawing: path A (left end -> loop top), path B (loop top -> right end).
A = [
    ("L", (9, 15), (21, 50)),
    ("L", (21, 50), (34, 21)),
    ("C", (34, 21), (38.6, 12.5), (37.6, 6), (32, 6)),
]
B = [
    ("C", (32, 6), (26.4, 6), (25.4, 12.5), (30, 21)),
    ("L", (30, 21), (43, 50)),
    ("L", (43, 50), (55, 15)),
]
CORNER_X = [9, 21, 32, 43, 55]


def _length(seg) -> float:
    if seg[0] == "L":
        (x0, y0), (x1, y1) = seg[1], seg[2]
        return math.hypot(x1 - x0, y1 - y0)
    p0, p1, p2, p3 = seg[1:]
    total, prev = 0.0, p0
    for i in range(1, 401):
        t = i / 400
        u = 1 - t
        pt = tuple(
            u**3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t**3 * d
            for a, b, c, d in zip(p0, p1, p2, p3)
        )
        total += math.hypot(pt[0] - prev[0], pt[1] - prev[1])
        prev = pt
    return total


def corner_fractions() -> list[float]:
    la, lb = sum(map(_length, A)), sum(map(_length, B))
    total = la + lb
    return [0.0, _length(A[0]) / total, la / total, (total - _length(B[-1])) / total, 1.0]


def time_at(fraction: float, speed: float) -> float:
    """When easeOutCubic(t / DRAW) reaches `fraction`, at `speed`. The ease approaches the right
    end so slowly that the eye sees the thread arrive at about 97%; the last note goes there,
    clear of the chord."""
    fraction = min(fraction, 0.97)
    return DRAW * (1 - (1 - fraction) ** (1 / 3)) / speed


def pluck(freq: float, seconds: float = 2.6, muted: bool = False) -> list[float]:
    sustain = 0.990 + RING * 0.0085
    bright = BRIGHT
    if muted:
        sustain, bright = min(sustain, 0.982), BRIGHT * 0.35
    n = max(2, round(RATE / freq))
    ring, prev, lp = [], 0.0, 0.12 + 0.88 * bright
    for _ in range(n):
        prev += lp * (random.uniform(-1, 1) - prev)
        ring.append(prev)
    mean = sum(ring) / n
    ring = [r - mean for r in ring]
    q = 0.42 * bright
    out, idx = [], 0
    for _ in range(int(RATE * seconds)):
        cur, nxt = ring[idx], ring[(idx + 1) % n]
        out.append(cur)
        ring[idx] = sustain * ((1 - q) * 0.5 * (cur + nxt) + q * cur)
        idx = (idx + 1) % n
    peak = max(abs(v) for v in out) or 1.0
    fade_in, fade_out = int(RATE * 0.002), int(RATE * 0.4)
    for i in range(len(out)):
        g = 0.9 / peak
        if i < fade_in:
            g *= i / fade_in
        if i > len(out) - fade_out:
            g *= (len(out) - i) / fade_out
        out[i] *= g
    # a gentle one-pole low-pass, the lab's filter (cut-off rises with brightness)
    cutoff = 1600 + bright * 7000
    alpha = 1 - math.exp(-2 * math.pi * cutoff / RATE)
    y = 0.0
    for i, v in enumerate(out):
        y += alpha * (v - y)
        out[i] = y
    return out


def render(
    notes: list[tuple[float, int, float, float]], tail: float = 2.8
) -> tuple[list[float], list[float]]:
    """notes: (start seconds, semitones above D4, gain, pan -1..1) -> stereo."""
    length = int(RATE * (max(n[0] for n in notes) + tail))
    left, right = [0.0] * length, [0.0] * length
    for start, semi, gain, pan in notes:
        tone = pluck(ROOT_D4 * 2 ** (semi / 12))
        gl, gr = gain * math.cos((pan + 1) * math.pi / 4), gain * math.sin((pan + 1) * math.pi / 4)
        at = int(start * RATE)
        for i, v in enumerate(tone):
            if at + i >= length:
                break
            left[at + i] += v * gl
            right[at + i] += v * gr
    return reverb(left), reverb(right, offset=7)


def reverb(dry: list[float], offset: int = 0) -> list[float]:
    """A small room: four feedback combs into one all-pass (Schroeder), mixed at ROOM."""
    combs = [(1116 + offset) // 2, (1188 + offset) // 2, (1277 + offset) // 2, (1356 + offset) // 2]
    wet = [0.0] * len(dry)
    for delay in combs:
        buf, fb = [0.0] * delay, 0.78
        for i, v in enumerate(dry):
            out = buf[i % delay]
            buf[i % delay] = v + out * fb
            wet[i] += out / len(combs)
    delay, g, buf = 278, 0.5, [0.0] * 278
    for i, v in enumerate(wet):
        b = buf[i % delay]
        buf[i % delay] = v + b * g
        wet[i] = b - g * v
    return [d + ROOM * w for d, w in zip(dry, wet)]


def write(path: Path, left: list[float], right: list[float]) -> None:
    peak = max(max(abs(v) for v in left), max(abs(v) for v in right)) or 1.0
    scale = 0.5 / peak  # -6 dBFS: the system volume does the rest
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        frames = bytearray()
        for lv, rv in zip(left, right):
            frames += struct.pack("<hh", int(lv * scale * 32767), int(rv * scale * 32767))
        out.writeframes(bytes(frames))


def main() -> None:
    corners = corner_fractions()
    pan = [((x - 32) / 32) * 0.7 for x in CORNER_X]

    random.seed(7)
    semis = [0, 7, 12, 14, 19]
    cold = [
        (time_at(f, 1), s, 0.75 if i == 2 else 0.6, pan[i])
        for i, (f, s) in enumerate(zip(corners, semis))
    ]
    cold += [(NAME_AT + i * 0.045, s, 0.38, (i - 1) * 0.35) for i, s in enumerate([0, 7, 16])]
    write(ASSETS / "opening.wav", *render(cold))

    random.seed(11)
    warm = [
        (time_at(corners[i], WARM_SPEED), s, 0.55, pan[i]) for i, s in zip([0, 2, 4], [0, 12, 19])
    ]
    write(ASSETS / "opening-short.wav", *render(warm, tail=2.2))

    for name in ("opening.wav", "opening-short.wav"):
        print(f"{name}: {(ASSETS / name).stat().st_size // 1024} KB")
    print("note times (cold):", [round(n[0], 3) for n in cold])


if __name__ == "__main__":
    main()
