/**
 * A refusal is only a feature if it reaches the person it is for.
 *
 * The gate composes a sentence naming every blocking requirement and what would satisfy it — and
 * the task board rendered "The Hub refused this change." instead, because `readableApiError` only
 * understood a string or a Pydantic error array. An object-shaped `detail` fell through to the
 * fallback and the sentence was discarded.
 *
 * That is precisely the failure the gate's design warned about: an unactionable gate gets switched
 * off. These tests hold the sentence on its way to the surface.
 */
import { describe, expect, it } from 'vitest'

import { ApiError, readableApiError } from '@/api/client'

function refusal(detail: unknown): ApiError {
  return new ApiError(409, JSON.stringify({ detail }))
}

describe('readableApiError', () => {
  it('keeps a plain string detail', () => {
    expect(readableApiError(refusal('Cannot move a task from A to B.'), 'fallback')).toBe(
      'Cannot move a task from A to B.',
    )
  })

  it('surfaces the sentence inside a structured gate refusal', () => {
    const detail = {
      code: 'gate_unsatisfied',
      blocking: [{ identifier: 'FR-14', state: 'in_progress', remedy: 'record what demonstrates it' }],
      diagnostics: [],
      unmergeable: [],
      message:
        'This task serves requirements a gate is enforcing, and they are not verified: FR-14 is ' +
        'in_progress: its linked work has produced no evidence — record what demonstrates it.',
    }
    const readable = readableApiError(refusal(detail), 'The Hub refused this change.')
    expect(readable).toContain('FR-14')
    expect(readable).toContain('record what demonstrates it')
    expect(readable).not.toBe('The Hub refused this change.')
  })

  it('surfaces the conflicting paths when work will not merge', () => {
    const detail = {
      code: 'gate_unsatisfied',
      blocking: [],
      diagnostics: [],
      unmergeable: [{ target_branch: 'main', paths: ['src/ledger.py'] }],
      message:
        "This task's work does not merge cleanly into main: src/ledger.py. Resolve the conflict " +
        'on the branch, then approve — approving is what merges it.',
    }
    const readable = readableApiError(refusal(detail), 'The Hub refused this change.')
    expect(readable).toContain('src/ledger.py')
    expect(readable).toContain('main')
  })

  it('surfaces the waiting evidence when approval is refused for want of a decision', () => {
    const detail = {
      code: 'gate_unsatisfied',
      blocking: [],
      diagnostics: [],
      unmergeable: [],
      unaccepted: [
        {
          kind: 'awaiting_evidence',
          evidence_id: 'ev-4c1f',
          identifier: 'FR-14',
          commit_sha: '0123456789abcdef',
          source_branch: 'agentweave/builder',
          target_branch: 'main',
          recorded_by_task: 'task-9f21',
          recorded_by_another_task: false,
        },
      ],
      message:
        "This task's work has been recorded and nobody has judged it: FR-14 at 0123456789ab. " +
        'Approving now would record that the work is good and merge none of it, because only ' +
        'accepted evidence is merged. To land it, accept the evidence, or grant an agent the ' +
        "capability to accept it — both are the operator's, so an agent reading this has to ask " +
        'for one rather than take it.',
    }
    const readable = readableApiError(refusal(detail), 'The Hub refused this change.')
    expect(readable).toContain('FR-14')
    expect(readable).toContain('0123456789ab')
    expect(readable).toContain('accept the evidence')
    expect(readable).toContain('grant an agent')
    expect(readable).not.toBe('The Hub refused this change.')
  })

  it('falls back when a structured detail carries no sentence', () => {
    const readable = readableApiError(refusal({ code: 'something_else' }), 'fallback')
    expect(readable).toBe('fallback')
  })
})
