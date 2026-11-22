import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { QuarantineList } from '@/components/overview/QuarantineList'
import type { NeverQuarantineMark, QuarantinedTest } from '@/api/quarantine'

// `first-run-and-the-overview-read-cleanly` FR-1, FR-2 and FR-3. Layout itself (the action at the
// row end, the 360 px fit, the computed borders) is measured in a browser by the acceptance drive,
// scripts/drive/d1122_first_run_polish.py; jsdom computes no layout, so this pins the markup those
// measurements rely on.

const LONG = 'tests/test_' + 'very_long_module_name_'.repeat(4) + 'x.py::TestSomething::test_a_case_whose_id_is_far_too_long'
const LONG_MARK = LONG.replace(/very/g, 'VERY')

// The shape `GET /checks/quarantine` returns: newest entry first, one of each.
const quarantined: QuarantinedTest[] = [
  {
    id: 'qt-long',
    check: 'hub-tests',
    test: LONG,
    flake_rate: 0.31,
    flips: 4,
    entered_at: '2026-11-22T09:00:00+00:00',
    passes: 1,
    passes_to_exit: 20,
    fix_task_id: null,
    fix_task: null,
  },
]
const marks: NeverQuarantineMark[] = [{ id: 'nqm-long', check: 'hub-tests', test: LONG_MARK, marked_at: '2026-11-22T08:00:00+00:00' }]

const renderList = (q: QuarantinedTest[], m: NeverQuarantineMark[]) =>
  render(
    <QuarantineList
      quarantined={q}
      marks={m}
      onSetMark={vi.fn()}
      onRemoveMark={vi.fn()}
      onOpenTask={vi.fn()}
      now={new Date('2026-11-22T10:00:00Z')}
    />,
  )

describe('the quarantine section reads cleanly', () => {
  it('says nothing is quarantined, nothing is marked, and what the form does (FR-3)', () => {
    renderList([], [])
    const section = screen.getByTestId('quarantine-list')
    expect(section).toHaveTextContent('No test is quarantined.')
    expect(within(screen.getByTestId('never-quarantine-marks')).getByText(/^No test is marked\./)).toHaveTextContent(
      'No test is marked. Name one below and its failures always count.',
    )
    expect(section.querySelectorAll('li')).toHaveLength(0)
  })

  it('lists a quarantined test and a mark in the same row shape, each with a glyph and its full id on hover (FR-2)', () => {
    renderList(quarantined, marks)
    const qrow = screen.getByTestId('quarantined-qt-long')
    const mrow = screen.getByTestId('never-quarantine-nqm-long')
    for (const [row, id] of [
      [qrow, LONG],
      [mrow, LONG_MARK],
    ] as const) {
      expect(id.length).toBeGreaterThan(90)
      expect(row.className).toBe('aw-ov-row aw-ov-kf-row aw-ov-q-row')
      expect([...row.children].map((c) => c.className)).toEqual(['aw-ov-row-icon', 'aw-ov-row-text', 'aw-ov-row-end'])
      const svg = row.querySelector('.aw-ov-row-icon svg')
      expect(svg).not.toBeNull()
      expect(svg!.innerHTML.trim()).not.toBe('')
      const title = row.querySelector('.aw-ov-row-title')!
      expect(title).toHaveTextContent(id)
      expect(title.getAttribute('title')).toBe(id)
      expect(row.querySelector('.aw-ov-row-end button')).not.toBeNull()
    }
    expect(within(mrow).getByText('hub-tests')).toBeInTheDocument()
  })

  it('labels each field above it and uses the app’s input and button (FR-1)', () => {
    renderList([], [])
    const fields = [...screen.getByTestId('never-quarantine-marks').querySelectorAll('.aw-ov-q-field')]
    expect(fields.map((f) => f.firstElementChild?.textContent)).toEqual(['Check', 'Test id'])
    for (const name of ['Check name', 'Test id']) {
      const input = screen.getByLabelText(name)
      expect(input.getAttribute('data-slot')).toBe('input')
      expect(input).toHaveClass('control-field')
    }
    const submit = screen.getByRole('button', { name: 'Never quarantine a test' })
    expect(submit.getAttribute('data-slot')).toBe('button')
    expect(submit).toBeDisabled()
  })
})
