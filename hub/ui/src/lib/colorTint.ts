/**
 * A translucent tint of a design token, derived via color-mix rather than authored as a raw
 * rgba() literal — the tint can never drift from the token it tints, and it recolours
 * automatically when the token does (e.g. across the light/dark ramp).
 */
export function tint(token: string, percent = 10): string {
  return `color-mix(in srgb, ${token} ${percent}%, transparent)`
}
