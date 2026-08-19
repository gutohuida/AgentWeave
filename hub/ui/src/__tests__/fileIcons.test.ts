import { describe, it, expect } from 'vitest'
import {
  fileKindFor,
  fileIconFor,
  fileColourFor,
  fileLanguageFor,
  isMarkdownPath,
} from '@/components/spec/fileIcons'
import { ICON_NAMES } from '@/components/common/Icon'
import { BRAND_MARK_KEYS, brandHex } from '@/components/common/brandMarks'

describe('fileIcons — what a file is, from its name', () => {
  it('recognises Docker by whole filename, including a suffixed variant', () => {
    expect(fileIconFor('Dockerfile')).toBe('brand:docker')
    expect(fileIconFor('deploy/Dockerfile')).toBe('brand:docker')
    expect(fileIconFor('Dockerfile.prod')).toBe('brand:docker')
    expect(fileIconFor('docker-compose.yml')).toBe('brand:docker')
    expect(fileIconFor('.dockerignore')).toBe('brand:docker')
  })

  it('recognises extensionless files a whole-name rule exists for', () => {
    // The reason whole-filename rules run before extension rules at all.
    expect(fileIconFor('Makefile')).toBe('file_config')
    expect(fileIconFor('.gitignore')).toBe('brand:git')
    expect(fileLanguageFor('Makefile')).toBe('makefile')
  })

  it('is case-insensitive, because Windows checkouts are', () => {
    expect(fileIconFor('DOCKERFILE')).toBe('brand:docker')
    expect(fileIconFor('src/Main.PY')).toBe(fileIconFor('src/main.py'))
  })

  it('maps common source extensions to a language the viewer can highlight', () => {
    expect(fileLanguageFor('src/app.ts')).toBe('typescript')
    expect(fileLanguageFor('src/app.tsx')).toBe('typescript')
    expect(fileLanguageFor('cli.py')).toBe('python')
    expect(fileLanguageFor('main.go')).toBe('go')
    expect(fileLanguageFor('lib.rs')).toBe('rust')
    expect(fileLanguageFor('run.ps1')).toBe('powershell')
    expect(fileLanguageFor('config.yaml')).toBe('yaml')
  })

  it('gives an unknown or extensionless file the neutral default rather than guessing', () => {
    const neutral = { icon: 'description', colour: 'var(--text-3)', language: null }
    expect(fileKindFor('LICENSE.unknown')).toEqual(neutral)
    expect(fileKindFor('somefile')).toEqual(neutral)
    // A leading dot is not an extension: `.bashrc` has no `.`-separated suffix to read.
    expect(fileKindFor('.bashrc').language).toBeNull()
  })

  it('treats markdown as render-not-highlight', () => {
    expect(isMarkdownPath('README.md')).toBe(true)
    expect(isMarkdownPath('docs/guide.markdown')).toBe(true)
    expect(isMarkdownPath('src/app.ts')).toBe(false)
    expect(fileIconFor('README.md')).toBe('brand:markdown')
  })

  it('handles Windows separators, since paths reach the UI from a Windows Hub', () => {
    expect(fileIconFor('src\\components\\App.tsx')).toBe('brand:typescript')
  })

  it('the fallback colour is always a palette token, never a literal hex', () => {
    // `colour` is what gets used when there is NO brand mark, so it must follow light/dark. A hex
    // here would look right in light mode and wrong in dark — the one failure a screenshot of the
    // default theme would not show. A brand's own colour is a different field entirely; see below.
    for (const sample of ['app.ts', 'main.py', 'Dockerfile', 'README.md', 'unknown.zzz', 'a.ps1']) {
      expect(fileKindFor(sample).colour).toMatch(/^var\(--[a-z0-9-]+\)$/)
    }
  })

  it('a brand-marked file draws in the brand’s own colour, not a palette token', () => {
    // Docker blue is Docker blue in both themes — that is the point of showing the mark at all.
    expect(fileColourFor('Dockerfile')).toMatch(/^#[0-9a-fA-F]{6}$/)
    expect(fileColourFor('src/app.ts')).toMatch(/^#[0-9a-fA-F]{6}$/)
    // A file with no brand mark still resolves to its palette token.
    expect(fileColourFor('notes.txt')).toMatch(/^var\(--[a-z0-9-]+\)$/)
    expect(fileColourFor('run.ps1')).toMatch(/^var\(--[a-z0-9-]+\)$/)
  })

  it('an illegible brand colour is dropped for a theme-aware one, keeping the shape', () => {
    // Markdown, JSON and Rust are officially #000000 — contrast 1.06 against the dark background,
    // i.e. invisible. This shipped that way for exactly one build before a dark-mode screenshot
    // caught it. JavaScript's yellow is the mirror failure: 1.30 against the light background.
    for (const sample of ['README.md', 'data.json', 'lib.rs', 'app.js']) {
      expect(fileColourFor(sample), sample).toMatch(/^var\(--[a-z0-9-]+\)$/)
      // The mark itself is unchanged — identity survives, only the colour is substituted.
      expect(fileIconFor(sample)).toMatch(/^brand:/)
    }
    expect(brandHex('brand:markdown')).toBeNull()
    expect(brandHex('brand:docker')).toBe('#2496ED')
  })

  it('every brand: icon it can return is a mark that actually exists', () => {
    // Same silent-failure class as the Icon map guard below: an unknown brand key renders nothing.
    const brandKeys = new Set(BRAND_MARK_KEYS)
    const samples = [
      'Dockerfile', 'docker-compose.yml', '.gitignore', 'package.json', 'yarn.lock',
      'pyproject.toml', 'app.ts', 'app.tsx', 'app.js', 'main.py', 'lib.rs', 'main.go',
      'a.rb', 'a.kt', 'a.swift', 'a.c', 'a.cpp', 'a.php', 'a.lua', 'run.sh',
      'd.json', 'd.yaml', 'd.toml', 'd.xml', 'r.md', 'i.html', 's.css', 'd.sqlite',
    ]
    for (const sample of samples) {
      const icon = fileIconFor(sample)
      if (icon.startsWith('brand:')) {
        expect(brandKeys, `brand for ${sample}`).toContain(icon.slice('brand:'.length))
      }
    }
  })

  it('keeps a generic glyph where simple-icons has withdrawn the mark', () => {
    // PowerShell, Java and C# were removed upstream over trademark objections. Borrowing a
    // near-enough logo would be both wrong and a trademark problem of our own making.
    expect(fileIconFor('run.ps1')).not.toMatch(/^brand:/)
    expect(fileIconFor('Main.java')).not.toMatch(/^brand:/)
    expect(fileIconFor('Program.cs')).not.toMatch(/^brand:/)
  })

  it('colour distinguishes the types whose glyphs look alike at 12px', () => {
    // FileCode2 and FileType2 are near-identical shapes at tree size; colour is what actually
    // separates a .py from a .ts in the operator's eye.
    expect(fileColourFor('main.py')).not.toBe(fileColourFor('app.ts'))
    expect(fileColourFor('config.yaml')).not.toBe(fileColourFor('app.ts'))
  })

  it('every icon it can return actually exists in the Icon map', () => {
    // The failure this guards is silent: Icon logs a console.warn and renders nothing, which is
    // exactly how `all_inclusive` shipped broken in JobCard. A name here that Icon does not know
    // would blank out every file row of that type with no error.
    const samples = [
      'Dockerfile', 'docker-compose.yml', 'Makefile', '.gitignore', '.env', 'package.json',
      'yarn.lock', 'pyproject.toml', 'app.ts', 'app.js', 'main.py', 'lib.rs', 'main.go',
      'a.rb', 'A.java', 'a.kt', 'a.swift', 'a.c', 'a.cpp', 'a.cs', 'a.php', 'a.lua',
      'run.sh', 'run.ps1', 'run.bat', 'd.json', 'd.yaml', 'd.toml', 'd.ini', 'd.xml',
      'd.csv', 'd.sql', 'd.db', 'r.md', 'r.rst', 'i.html', 's.css', 'p.png', 'v.svg',
      't.txt', 'l.log', 'unknown.zzz', 'noextension',
    ]
    for (const sample of samples) {
      const icon = fileIconFor(sample)
      if (icon.startsWith('brand:')) continue // covered by the brand-mark guard above
      expect(ICON_NAMES, `icon for ${sample}`).toContain(icon)
    }
  })
})
