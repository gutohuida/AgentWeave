/// <reference types="vite/client" />
import { describe, expect, it } from 'vitest'
// @ts-expect-error Vitest runs in Node; the browser bundle never includes this contract test.
import { readFileSync } from 'node:fs'

// The contrast bar 1.0 holds itself to, enforced rather than recorded.
//
// `2026-08-04-hub-charcoal-visual-refresh` task 8.9 measured the ramp and found --text-3 below
// AA 4.5 on every surface in both modes, on text that is not decorative — timestamps, the
// session-continuity line, composer placeholders, status labels. Task 8.11 put the remediation
// to the operator as a design decision, because meeting 4.5 would have pushed --text-3 to within
// one step of --text-2 and collapsed the three-level neutral ramp into two. The ramp is what the
// charcoal refresh was for.
//
// The operator chose **3.0** — the WCAG bar for large text and non-text UI — held on every
// surface, keeping three distinct levels. That decision is a number, so it is asserted as one:
// a future palette edit that drops back below it fails here instead of shipping.
//
// Deliberately computed from index.css rather than pinned to literals. Pinning hexes would say
// "these are the colours"; this says "whatever the colours are, they clear the bar", which is
// the thing actually decided.

const cssSource = readFileSync('src/index.css', 'utf8')

const AA_NORMAL = 4.5
const NON_TEXT = 3.0

function relativeLuminance(hex: string): number {
  const h = hex.replace('#', '')
  const channels = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

/** The declared value of a token within one mode block, hex only. */
function token(block: string, name: string): string {
  const match = block.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})\\s*;`))
  if (!match) throw new Error(`${name} is not declared as a hex literal in this mode block`)
  return match[1]
}

const MODES = {
  dark: cssSource.slice(cssSource.indexOf('[data-mode="dark"]'), cssSource.indexOf('[data-mode="light"]')),
  light: cssSource.slice(cssSource.indexOf('[data-mode="light"]')),
} as const

// Every plane text is ever set on. --surface-3 is the worst case in both modes: it is the
// closest ground plane to the text ramp, so it is where a passing token fails first.
const SURFACES = ['--bg', '--surface', '--surface-2', '--surface-3'] as const

describe('the neutral ramp holds the contrast bar the operator chose (8.11)', () => {
  for (const mode of ['dark', 'light'] as const) {
    const block = MODES[mode]

    it(`${mode}: every text level clears 3.0 on every surface`, () => {
      for (const level of ['--text', '--text-2', '--text-3'] as const) {
        const fg = token(block, level)
        for (const surface of SURFACES) {
          const ratio = contrast(fg, token(block, surface))
          expect(
            ratio,
            `${mode} ${level} (${fg}) on ${surface} is ${ratio.toFixed(2)}, below the 3.0 bar`,
          ).toBeGreaterThanOrEqual(NON_TEXT)
        }
      }
    })

    it(`${mode}: the two primary text levels also clear AA 4.5`, () => {
      // 3.0 was accepted for the third level only. The levels carrying primary and secondary
      // copy were already comfortably AA and are held there, so the exemption stays narrow.
      for (const level of ['--text', '--text-2'] as const) {
        const fg = token(block, level)
        for (const surface of SURFACES) {
          const ratio = contrast(fg, token(block, surface))
          expect(
            ratio,
            `${mode} ${level} (${fg}) on ${surface} is ${ratio.toFixed(2)}, below AA ${AA_NORMAL}`,
          ).toBeGreaterThanOrEqual(AA_NORMAL)
        }
      }
    })

    it(`${mode}: status hues clear 3.0 on every surface`, () => {
      // Light --green and --amber were the two that failed 8.9 alongside --text-3.
      for (const hue of ['--green', '--amber', '--red', '--blue', '--purple'] as const) {
        const fg = token(block, hue)
        for (const surface of SURFACES) {
          const ratio = contrast(fg, token(block, surface))
          expect(
            ratio,
            `${mode} ${hue} (${fg}) on ${surface} is ${ratio.toFixed(2)}, below the 3.0 bar`,
          ).toBeGreaterThanOrEqual(NON_TEXT)
        }
      }
    })

    it(`${mode}: the ramp still has three distinguishable levels`, () => {
      // The whole reason 4.5 was rejected. Asserted as a relationship, not a value: the levels
      // must stay ordered, and each step must be a step someone can actually see. The AA
      // alternative sat at 1.03 (dark) and 1.20 (light) — that is the collapse being guarded.
      const [t1, t2, t3] = (['--text', '--text-2', '--text-3'] as const).map((l) => token(block, l))
      const step = contrast(t2, t3)
      expect(step, `${mode} --text-2 (${t2}) and --text-3 (${t3}) are within ${step.toFixed(3)}`)
        .toBeGreaterThan(1.25)
      expect(contrast(t1, t2)).toBeGreaterThan(1.25)

      // And ordered: each level recedes further from the text colour than the one above it.
      const bg = token(block, '--bg')
      expect(contrast(t1, bg)).toBeGreaterThan(contrast(t2, bg))
      expect(contrast(t2, bg)).toBeGreaterThan(contrast(t3, bg))
    })
  }
})
