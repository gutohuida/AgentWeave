/**
 * What a workspace file *is*, derived from its name — the icon the tree and tab strip show, and
 * the language the viewer highlights it as.
 *
 * One module rather than two lookups, because the two answers come from the same evidence and
 * would otherwise drift: a file the tree calls Docker and the viewer highlights as plain text is
 * the kind of small inconsistency nobody reports but everybody notices.
 *
 * Whole-filename rules are checked before extensions, because the files an operator most wants to
 * recognise at a glance are often extensionless (`Dockerfile`, `Makefile`, `.gitignore`) — the
 * same reason the file endpoint detects binary content by NUL byte rather than by extension
 * (design D7).
 *
 * Lucide carries no brand marks, so there is no literal Docker whale or Python logo available.
 * `file_container` for Docker and shape-based glyphs elsewhere are the closest honest mapping
 * inside the one icon system CLAUDE.md allows.
 */

export interface FileKind {
  /** A name in `Icon`'s map. */
  icon: string
  /** The glyph's colour, as a palette token — never a literal hex. Every value here is already
   *  tuned per `[data-mode]`, so the tree follows light/dark for free. Colour carries most of the
   *  recognition at 12px: `FileCode2` and `FileType2` are near-identical shapes at that size, and
   *  it is the green-vs-blue that actually tells `app.py` from `panel.ts` at a glance. */
  colour: string
  /** A highlight.js language id, or null to render as plain text. */
  language: string | null
}

const DEFAULT_KIND: FileKind = { icon: 'description', colour: 'var(--text-3)', language: null }

/** Matched against the lowercased whole filename, before any extension rule. */
const BY_FILENAME: Record<string, FileKind> = {
  dockerfile: { icon: 'file_container', colour: 'var(--blue)', language: 'dockerfile' },
  'docker-compose.yml': { icon: 'file_container', colour: 'var(--blue)', language: 'yaml' },
  'docker-compose.yaml': { icon: 'file_container', colour: 'var(--blue)', language: 'yaml' },
  '.dockerignore': { icon: 'file_container', colour: 'var(--blue)', language: null },
  makefile: { icon: 'file_config', colour: 'var(--amber)', language: 'makefile' },
  'cmakelists.txt': { icon: 'file_config', colour: 'var(--amber)', language: null },
  '.gitignore': { icon: 'file_vcs', colour: 'var(--amber)', language: null },
  '.gitattributes': { icon: 'file_vcs', colour: 'var(--amber)', language: null },
  '.gitmodules': { icon: 'file_vcs', colour: 'var(--amber)', language: null },
  '.env': { icon: 'file_lock', colour: 'var(--text-3)', language: 'ini' },
  '.env.example': { icon: 'file_lock', colour: 'var(--text-3)', language: 'ini' },
  'package.json': { icon: 'file_package', colour: 'var(--red)', language: 'json' },
  'package-lock.json': { icon: 'file_lock', colour: 'var(--text-3)', language: 'json' },
  'pyproject.toml': { icon: 'file_package', colour: 'var(--red)', language: 'ini' },
  'requirements.txt': { icon: 'file_package', colour: 'var(--red)', language: null },
  'cargo.toml': { icon: 'file_package', colour: 'var(--red)', language: 'ini' },
  'go.mod': { icon: 'file_package', colour: 'var(--red)', language: null },
  'go.sum': { icon: 'file_lock', colour: 'var(--text-3)', language: null },
  'yarn.lock': { icon: 'file_lock', colour: 'var(--text-3)', language: null },
  'pnpm-lock.yaml': { icon: 'file_lock', colour: 'var(--text-3)', language: 'yaml' },
  'license': { icon: 'description', colour: 'var(--text-3)', language: null },
  'readme.md': { icon: 'file_markdown', colour: 'var(--purple)', language: 'markdown' },
}

/** Matched against the lowercased extension, without the dot. */
const BY_EXTENSION: Record<string, FileKind> = {
  // Web / TypeScript
  ts: { icon: 'file_type', colour: 'var(--blue)', language: 'typescript' },
  tsx: { icon: 'file_type', colour: 'var(--blue)', language: 'typescript' },
  mts: { icon: 'file_type', colour: 'var(--blue)', language: 'typescript' },
  cts: { icon: 'file_type', colour: 'var(--blue)', language: 'typescript' },
  js: { icon: 'file_code', colour: 'var(--green)', language: 'javascript' },
  jsx: { icon: 'file_code', colour: 'var(--green)', language: 'javascript' },
  mjs: { icon: 'file_code', colour: 'var(--green)', language: 'javascript' },
  cjs: { icon: 'file_code', colour: 'var(--green)', language: 'javascript' },
  // Languages
  py: { icon: 'file_code', colour: 'var(--green)', language: 'python' },
  pyi: { icon: 'file_code', colour: 'var(--green)', language: 'python' },
  rs: { icon: 'file_code', colour: 'var(--green)', language: 'rust' },
  go: { icon: 'file_code', colour: 'var(--green)', language: 'go' },
  rb: { icon: 'file_code', colour: 'var(--green)', language: 'ruby' },
  java: { icon: 'file_code', colour: 'var(--green)', language: 'java' },
  kt: { icon: 'file_code', colour: 'var(--green)', language: 'kotlin' },
  swift: { icon: 'file_code', colour: 'var(--green)', language: 'swift' },
  c: { icon: 'file_code', colour: 'var(--green)', language: 'c' },
  h: { icon: 'file_code', colour: 'var(--green)', language: 'c' },
  cpp: { icon: 'file_code', colour: 'var(--green)', language: 'cpp' },
  cc: { icon: 'file_code', colour: 'var(--green)', language: 'cpp' },
  hpp: { icon: 'file_code', colour: 'var(--green)', language: 'cpp' },
  cs: { icon: 'file_code', colour: 'var(--green)', language: 'csharp' },
  php: { icon: 'file_code', colour: 'var(--green)', language: 'php' },
  lua: { icon: 'file_code', colour: 'var(--green)', language: 'lua' },
  // Shells
  sh: { icon: 'terminal', colour: 'var(--green)', language: 'bash' },
  bash: { icon: 'terminal', colour: 'var(--green)', language: 'bash' },
  zsh: { icon: 'terminal', colour: 'var(--green)', language: 'bash' },
  fish: { icon: 'terminal', colour: 'var(--green)', language: 'bash' },
  ps1: { icon: 'terminal', colour: 'var(--green)', language: 'powershell' },
  psm1: { icon: 'terminal', colour: 'var(--green)', language: 'powershell' },
  bat: { icon: 'terminal', colour: 'var(--green)', language: 'dos' },
  cmd: { icon: 'terminal', colour: 'var(--green)', language: 'dos' },
  // Data / config
  json: { icon: 'file_json', colour: 'var(--amber)', language: 'json' },
  jsonc: { icon: 'file_json', colour: 'var(--amber)', language: 'json' },
  yml: { icon: 'file_config', colour: 'var(--amber)', language: 'yaml' },
  yaml: { icon: 'file_config', colour: 'var(--amber)', language: 'yaml' },
  toml: { icon: 'file_config', colour: 'var(--amber)', language: 'ini' },
  ini: { icon: 'file_config', colour: 'var(--amber)', language: 'ini' },
  cfg: { icon: 'file_config', colour: 'var(--amber)', language: 'ini' },
  conf: { icon: 'file_config', colour: 'var(--amber)', language: 'ini' },
  properties: { icon: 'file_config', colour: 'var(--amber)', language: 'ini' },
  xml: { icon: 'file_braces', colour: 'var(--purple)', language: 'xml' },
  csv: { icon: 'file_sheet', colour: 'var(--green)', language: null },
  tsv: { icon: 'file_sheet', colour: 'var(--green)', language: null },
  sql: { icon: 'file_database', colour: 'var(--blue)', language: 'sql' },
  db: { icon: 'file_database', colour: 'var(--blue)', language: null },
  sqlite: { icon: 'file_database', colour: 'var(--blue)', language: null },
  // Markup / styles
  md: { icon: 'file_markdown', colour: 'var(--purple)', language: 'markdown' },
  markdown: { icon: 'file_markdown', colour: 'var(--purple)', language: 'markdown' },
  mdx: { icon: 'file_markdown', colour: 'var(--purple)', language: 'markdown' },
  rst: { icon: 'file_markdown', colour: 'var(--purple)', language: null },
  html: { icon: 'file_braces', colour: 'var(--purple)', language: 'xml' },
  htm: { icon: 'file_braces', colour: 'var(--purple)', language: 'xml' },
  css: { icon: 'file_style', colour: 'var(--purple)', language: 'css' },
  scss: { icon: 'file_style', colour: 'var(--purple)', language: 'css' },
  less: { icon: 'file_style', colour: 'var(--purple)', language: 'css' },
  // Images and other binaries the viewer will refuse anyway — the icon still tells the truth in
  // the tree, which is where it matters.
  png: { icon: 'file_image', colour: 'var(--purple)', language: null },
  jpg: { icon: 'file_image', colour: 'var(--purple)', language: null },
  jpeg: { icon: 'file_image', colour: 'var(--purple)', language: null },
  gif: { icon: 'file_image', colour: 'var(--purple)', language: null },
  svg: { icon: 'file_image', colour: 'var(--purple)', language: 'xml' },
  webp: { icon: 'file_image', colour: 'var(--purple)', language: null },
  ico: { icon: 'file_image', colour: 'var(--purple)', language: null },
  // Prose
  txt: { icon: 'description', colour: 'var(--text-3)', language: null },
  log: { icon: 'description', colour: 'var(--text-3)', language: null },
}

/** The name, lowercased, with any directory stripped. */
function basename(path: string): string {
  const slash = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'))
  return (slash === -1 ? path : path.slice(slash + 1)).toLowerCase()
}

export function fileKindFor(path: string): FileKind {
  const name = basename(path)
  const byName = BY_FILENAME[name]
  if (byName) return byName

  // `Dockerfile.dev`, `dockerfile.prod` — the same file by intent, so recognise the stem too.
  if (name.startsWith('dockerfile')) return BY_FILENAME.dockerfile
  if (name.startsWith('.env.')) return BY_FILENAME['.env']

  const dot = name.lastIndexOf('.')
  if (dot <= 0) return DEFAULT_KIND
  return BY_EXTENSION[name.slice(dot + 1)] ?? DEFAULT_KIND
}

export function fileIconFor(path: string): string {
  return fileKindFor(path).icon
}

export function fileColourFor(path: string): string {
  return fileKindFor(path).colour
}

export function fileLanguageFor(path: string): string | null {
  return fileKindFor(path).language
}

/** Markdown gets rendered rather than highlighted — see `FilePreview`. */
export function isMarkdownPath(path: string): boolean {
  return fileKindFor(path).language === 'markdown'
}
