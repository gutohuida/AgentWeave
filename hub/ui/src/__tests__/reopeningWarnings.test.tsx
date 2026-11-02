import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { ReopeningWarnings } from '@/components/overview/ReopeningWarnings'
import type { ReopeningWarning } from '@/api/reopeningWarnings'

/** Fed as `GET /project/reopening-warnings` answers: newest first, each key as
 *  `test_recommended_people.py::test_ac_warning_route_payload` pins it. */
const NEWEST: ReopeningWarning = {
  build_id: 'build-new',
  document_id: 'spdoc-new',
  path: 'spec/changes/notes/spec.json',
  title: 'Notes and schema',
  reopened_at: '2026-11-02T10:00:00+00:00',
  finished_at: '2026-10-03T10:00:00+00:00',
  finished_ago: '30 days',
  tasks: [
    { id: 'task-1', display_id: 'NAS-3', title: 'Add FOLLOWUP.md', filer: 'Checker' },
    { id: 'task-2', display_id: 'NAS-4', title: 'Add ANOTHER.md', filer: 'QA' },
  ],
}
const OLDER: ReopeningWarning = {
  ...NEWEST,
  build_id: 'build-old',
  title: 'An older spec',
  reopened_at: '2026-11-01T10:00:00+00:00',
  finished_ago: '1 hour',
  tasks: [{ id: 'task-3', display_id: 'OLD-1', title: 'Older', filer: 'the operator' }],
}

let warnings: ReopeningWarning[] = []
const stop = vi.fn()
const dismiss = vi.fn()
vi.mock('@/lib/toast', () => ({ toast: vi.fn() }))
vi.mock('@/api/reopeningWarnings', () => ({
  useStopReopenedBuild: () => ({ mutate: stop, isPending: false }),
  useDismissReopeningWarning: () => ({ mutate: dismiss, isPending: false }),
}))

describe('ac_warning: the Overview warns of a reopened build', () => {
  beforeEach(() => {
    warnings = [NEWEST, OLDER]
    stop.mockClear()
    dismiss.mockClear()
  })

  it('names the spec, every task, each filer and the age, in the route order', () => {
    render(<ReopeningWarnings warnings={warnings} />)
    const shown = screen.getAllByTestId('reopening-warning')
    expect(shown).toHaveLength(2)
    expect(shown[0]).toHaveTextContent('Notes and schema')
    expect(shown[0]).toHaveTextContent('30 days')
    expect(shown[0]).toHaveTextContent('NAS-3 “Add FOLLOWUP.md”, filed by Checker')
    expect(shown[0]).toHaveTextContent('NAS-4 “Add ANOTHER.md”, filed by QA')
    expect(shown[1]).toHaveTextContent('An older spec')
  })

  it('stops that build from its own warning', () => {
    render(<ReopeningWarnings warnings={warnings} />)
    const second = screen.getAllByTestId('reopening-warning')[1]
    fireEvent.click(within(second).getByTestId('reopening-warning-stop'))
    expect(stop.mock.calls[0][0]).toBe('build-old')
    expect(dismiss).not.toHaveBeenCalled()
  })

  it('dismisses without stopping', () => {
    render(<ReopeningWarnings warnings={warnings} />)
    fireEvent.click(within(screen.getAllByTestId('reopening-warning')[0]).getByTestId('reopening-warning-dismiss'))
    expect(dismiss.mock.calls[0][0]).toBe('build-new')
    expect(stop).not.toHaveBeenCalled()
  })

  it('shows nothing when no warning stands', () => {
    warnings = []
    const { container } = render(<ReopeningWarnings warnings={warnings} />)
    expect(container).toBeEmptyDOMElement()
  })
})
