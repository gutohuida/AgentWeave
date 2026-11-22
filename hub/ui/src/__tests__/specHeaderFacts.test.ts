import { describe, expect, it } from 'vitest'
import { checkerOf, firstTaskId, phaseLabel } from '@/components/spec/page/model'

/* `starting-a-spec-from-a-thread-and-a-spec-page-that-agrees-with-itself`, task `header-facts`:
 * the words the spec page header derives from the document and its build. */

describe('who checks the work (header-names-checker)', () => {
  it("names the one checker every task has, its own or the build's default (ac-checker-single)", () => {
    expect(checkerOf(['a'], null, { a: 'QA' })).toEqual({ kind: 'one', name: 'QA' })
    expect(checkerOf(['a', 'b'], 'QA', { a: 'QA', b: null })).toEqual({ kind: 'one', name: 'QA' })
    expect(checkerOf(['a', 'b'], 'QA', {})).toEqual({ kind: 'one', name: 'QA' })
  })

  it('says per task when the tasks name different checkers, or only some name one (ac-checker-mixed)', () => {
    expect(checkerOf(['a', 'b'], null, { a: 'QA', b: 'Architect' })).toEqual({ kind: 'per-task' })
    expect(checkerOf(['a', 'b'], '', { a: 'QA' })).toEqual({ kind: 'per-task' })
  })

  it('says nobody only when no task has a checker', () => {
    expect(checkerOf(['a', 'b'], null, {})).toEqual({ kind: 'none' })
    expect(checkerOf([], null, {})).toEqual({ kind: 'none' })
  })

  it("falls back to the build's own task keys when the document declares none", () => {
    expect(checkerOf([], null, { a: 'QA', b: 'QA' })).toEqual({ kind: 'one', name: 'QA' })
  })
})

describe('the task-id example (task-id-example-real)', () => {
  it("shows the first real task's id, else the first it will get, never -N (ac-task-id)", () => {
    expect(firstTaskId('ASFGP', [])).toBe('ASFGP-1')
    expect(firstTaskId('ASFGP', ['ASFGP-10', null, 'ASFGP-2', 'OTHER-1', 'ASFGP-x'])).toBe('ASFGP-2')
  })
})

describe('the phase badge (badge-names-step)', () => {
  it('names the step while written and the phase alone after (ac-badge-step)', () => {
    expect(phaseLabel({ state: 'writing', step: 'intake' }, 'writing')).toBe('Writing · Intake')
    expect(phaseLabel({ state: 'writing', step: 'build' }, 'writing')).toBe('Writing · Build')
    expect(phaseLabel({ state: 'approved', step: null }, 'approved')).toBe('Approved')
    expect(phaseLabel({ state: 'building', step: null }, 'building')).toBe('Building')
  })
})
