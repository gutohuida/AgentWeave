import { describe, it, expect } from 'vitest'
import {
  fileKindFor,
  fileIconFor,
  fileLanguageFor,
  isMarkdownPath,
} from '@/components/spec/fileIcons'
import { ICON_NAMES } from '@/components/common/Icon'

describe('fileIcons — what a file is, from its name', () => {
  it('recognises Docker by whole filename, including a suffixed variant', () => {
    expect(fileIconFor('Dockerfile')).toBe('file_container')
    expect(fileIconFor('deploy/Dockerfile')).toBe('file_container')
    expect(fileIconFor('Dockerfile.prod')).toBe('file_container')
    expect(fileIconFor('docker-compose.yml')).toBe('file_container')
    expect(fileIconFor('.dockerignore')).toBe('file_container')
  })

  it('recognises extensionless files a whole-name rule exists for', () => {
    // The reason whole-filename rules run before extension rules at all.
    expect(fileIconFor('Makefile')).toBe('file_config')
    expect(fileIconFor('.gitignore')).toBe('file_vcs')
    expect(fileLanguageFor('Makefile')).toBe('makefile')
  })

  it('is case-insensitive, because Windows checkouts are', () => {
    expect(fileIconFor('DOCKERFILE')).toBe('file_container')
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
    expect(fileIconFor('README.md')).toBe('file_markdown')
  })

  it('handles Windows separators, since paths reach the UI from a Windows Hub', () => {
    expect(fileIconFor('src\\components\\App.tsx')).toBe('file_type')
  })

  it('colours come from the palette, never a literal, so dark mode follows for free', () => {
    // A hex here would look right in light mode and wrong in dark, which is the one failure a
    // screenshot of the default theme would not show.
    for (const sample of ['app.ts', 'main.py', 'Dockerfile', 'README.md', 'unknown.zzz']) {
      expect(fileKindFor(sample).colour).toMatch(/^var\(--[a-z0-9-]+\)$/)
    }
  })

  it('colour distinguishes the types whose glyphs look alike at 12px', () => {
    // FileCode2 and FileType2 are near-identical shapes at tree size; colour is what actually
    // separates a .py from a .ts in the operator's eye.
    expect(fileKindFor('main.py').colour).not.toBe(fileKindFor('app.ts').colour)
    expect(fileKindFor('config.yaml').colour).not.toBe(fileKindFor('app.ts').colour)
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
      expect(ICON_NAMES, `icon for ${sample}`).toContain(fileIconFor(sample))
    }
  })
})
