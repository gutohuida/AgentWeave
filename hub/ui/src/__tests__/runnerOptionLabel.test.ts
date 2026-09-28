import { describe, expect, it } from 'vitest'
import { runnerOptionLabel } from '@/lib/runnerLabel'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

function runner(overrides: Partial<Parameters<typeof runnerOptionLabel>[0]> = {}) {
  return {
    id: 'runner-1',
    project_id: 'proj-a',
    name: 'Claude Code',
    cli: 'claude' as const,
    model: null,
    flags: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    model_unrecognised: false,
    ...overrides,
  }
}

describe('runnerOptionLabel (F268)', () => {
  it('names the catalog label for a declared model', () => {
    expect(runnerOptionLabel(runner({ model: 'claude-opus-5' }), MODEL_CATALOG_FIXTURE))
      .toBe('Claude Code — Opus 5 (claude)')
  })

  it('says "Provider default" for a runner with no model', () => {
    expect(runnerOptionLabel(runner({ model: null }), MODEL_CATALOG_FIXTURE))
      .toBe('Claude Code — Provider default (claude)')
  })

  it('marks a model the catalog does not declare as unrecognised', () => {
    expect(runnerOptionLabel(runner({ model: 'claude-opus-4' }), MODEL_CATALOG_FIXTURE))
      .toBe('Claude Code — claude-opus-4 (unrecognised) (claude)')
  })

  it('falls back to the raw id when the catalog has not loaded', () => {
    expect(runnerOptionLabel(runner({ model: 'claude-opus-5-5' }), undefined))
      .toBe('Claude Code — claude-opus-5-5 (claude)')
  })

  it('two same-named runners with different models get different labels', () => {
    const a = runnerOptionLabel(runner({ model: 'claude-opus-5' }), MODEL_CATALOG_FIXTURE)
    const b = runnerOptionLabel(runner({ model: 'claude-haiku-4-5-20251001' }), MODEL_CATALOG_FIXTURE)
    expect(a).not.toBe(b)
  })

  it('does not double the model for a runner the Hub named for itself', () => {
    const hubNamed = runner({ name: 'Claude Code — Opus 5', model: 'claude-opus-5' })
    const label = runnerOptionLabel(hubNamed, MODEL_CATALOG_FIXTURE)
    expect(label).toBe('Claude Code — Opus 5 (claude)')
    expect(label.match(/Opus 5/g)).toHaveLength(1)
  })

  it('reads the truth once the same named runner is later moved to a different model', () => {
    const moved = runner({ name: 'Claude Code — Opus 5', model: 'claude-haiku-4-5-20251001' })
    expect(runnerOptionLabel(moved, MODEL_CATALOG_FIXTURE))
      .toBe('Claude Code — Opus 5 — Haiku 4.5 (claude)')
  })

  it('an override replaces the model part, and is not suffix-matched against the un-overridden name', () => {
    const hubNamed = runner({ name: 'Claude Code — Opus 5', model: 'claude-opus-5' })
    expect(runnerOptionLabel(hubNamed, MODEL_CATALOG_FIXTURE, { model: 'claude-haiku-4-5-20251001' }))
      .toBe('Claude Code — Opus 5 — Haiku 4.5 (claude)')
  })

  it('a falsy override falls back to the runner\'s own model', () => {
    expect(runnerOptionLabel(runner({ model: 'claude-opus-5' }), MODEL_CATALOG_FIXTURE, { model: null }))
      .toBe('Claude Code — Opus 5 (claude)')
  })

  it('names a declared alias as what the runner records, not its current target (a-model-alias-is-a-model-choice D2)', () => {
    expect(runnerOptionLabel(runner({ model: 'opus' }), MODEL_CATALOG_FIXTURE))
      .toBe('Claude Code — opus (latest) (claude)')
  })

  it('does not double an alias for a runner the Hub named for itself', () => {
    const hubNamed = runner({ name: 'Claude Code — opus (latest)', model: 'opus' })
    const label = runnerOptionLabel(hubNamed, MODEL_CATALOG_FIXTURE)
    expect(label).toBe('Claude Code — opus (latest) (claude)')
    expect(label.match(/opus/g)).toHaveLength(1)
  })
})
