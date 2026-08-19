import {
  siC,
  siCplusplus,
  siCss,
  siDocker,
  siGit,
  siGnubash,
  siGo,
  siHtml5,
  siJavascript,
  siJson,
  siKotlin,
  siLua,
  siMarkdown,
  siNpm,
  siPhp,
  siPython,
  siRuby,
  siRust,
  siSqlite,
  siSwift,
  siToml,
  siTypescript,
  siXml,
  siYaml,
  type SimpleIcon,
} from 'simple-icons'

/**
 * Brand marks for file types, from `simple-icons`.
 *
 * **Why a second icon package exists at all.** CLAUDE.md's rule is "do not reintroduce a second
 * icon system", written after the Material Symbols *webfont* loaded `display=block` from a CDN and
 * held every icon invisible until the network answered. That failure mode is absent here: these
 * are bundled path strings, no font, no network, no FOIT. The rule's reasoning does not reach this
 * case, and the operator decided the exception explicitly on 2026-08-19 — recorded in CLAUDE.md so
 * it reads as a decision rather than a violation someone later "fixes".
 *
 * lucide cannot serve this: it deliberately carries no brand marks, and neither do Heroicons,
 * Phosphor or Tabler. A Docker file that looks like Docker is not available from a UI icon set at
 * any version.
 *
 * **Where a mark does not exist, there is no fallback brand — the lucide shape stands.** PowerShell,
 * Java and C# have all been removed from simple-icons over trademark objections, so `.ps1`, `.java`
 * and `.cs` keep their generic glyph rather than borrowing a near-enough logo, which would be both
 * wrong and a trademark problem of our own making.
 *
 * The paths are CC0; the trademarks remain their owners'. They are used here to identify a file's
 * type, which is the same nominative use every editor makes of them.
 */
export const BRAND_MARKS: Record<string, SimpleIcon> = {
  c: siC,
  cplusplus: siCplusplus,
  css: siCss,
  docker: siDocker,
  git: siGit,
  gnubash: siGnubash,
  go: siGo,
  html5: siHtml5,
  javascript: siJavascript,
  json: siJson,
  kotlin: siKotlin,
  lua: siLua,
  markdown: siMarkdown,
  npm: siNpm,
  php: siPhp,
  python: siPython,
  ruby: siRuby,
  rust: siRust,
  sqlite: siSqlite,
  swift: siSwift,
  toml: siToml,
  typescript: siTypescript,
  xml: siXml,
  yaml: siYaml,
}

/** `Icon`'s `name` prefix that routes to a brand mark rather than the lucide map. */
export const BRAND_PREFIX = 'brand:'

export function brandIconName(key: string): string {
  return `${BRAND_PREFIX}${key}`
}

/** WCAG relative luminance. */
function luminance(hex: string): number {
  const channel = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  const [r, g, b] = [0, 2, 4].map((i) => channel(parseInt(hex.slice(i, i + 2), 16) / 255))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: number, b: number): number {
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
}

/* Roughly the app's two page backgrounds. Not read from CSS because this has to be answerable
 * without a DOM — `fileColourFor` is a pure function used in tests and before first paint. */
const LIGHT_BG = luminance('fafafa')
const DARK_BG = luminance('0a0a0a')

/** Below this against *either* background, the brand's own colour is not legible enough to use. */
const MIN_CONTRAST = 2.0

/**
 * A brand's own colour, when it is legible in **both** themes — Docker blue is Docker blue in
 * light and dark, and that fixedness is the point of showing a real mark.
 *
 * Returns null when it is not, so the caller falls back to a theme-aware palette token. Measured
 * rather than assumed, because several official brand colours are unusable against one of our two
 * backgrounds: Markdown, JSON and Rust are pure `#000000` (contrast 1.06 on dark — invisible, and
 * this shipped that way for one build before a dark-mode screenshot caught it), Lua is navy, and
 * JavaScript's yellow scores 1.30 on light. The *shape* still carries the identity in those cases;
 * only the colour is substituted, which is the right half to give up.
 *
 * Computed rather than hardcoded so it stays correct if simple-icons revises a hex, or if a brand
 * is added here later.
 */
export function brandHex(name: string): string | null {
  const mark = BRAND_MARKS[name.startsWith(BRAND_PREFIX) ? name.slice(BRAND_PREFIX.length) : name]
  if (!mark) return null
  const l = luminance(mark.hex)
  if (contrast(l, LIGHT_BG) < MIN_CONTRAST || contrast(l, DARK_BG) < MIN_CONTRAST) return null
  return `#${mark.hex}`
}

export const BRAND_MARK_KEYS: readonly string[] = Object.keys(BRAND_MARKS)
