import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChartersPage } from '@/components/charters/ChartersPage'
import { charterSummary } from '@/components/charters/charterSummary'

const updateMutate = vi.fn()
const deleteMutate = vi.fn()
const createMutate = vi.fn()

const TECH_LEAD_BODY = [
  '# Tech Lead',
  '',
  '## You Are Accountable For',
  '',
  "- The system's structure: how it is divided, and what crosses the boundaries",
  '- Making the call when two approaches are both defensible',
].join('\n')

const DEVELOPER_BODY = [
  '# Developer',
  '',
  '## You Are Accountable For',
  '',
  '- The code working. Not written, not plausible — working, and you having checked.',
].join('\n')

let charters = [
  { id: 'charter-001', name: 'Tech Lead', content: TECH_LEAD_BODY },
  { id: 'charter-002', name: 'Developer', content: DEVELOPER_BODY },
  { id: 'charter-003', name: 'Empty One', content: '' },
]

// importOriginal so that adding an export to @/api/charters later does not break this
// file the way seven files mocking @/api/permissions broke on one added export.
vi.mock('@/api/charters', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/charters')>()),
  useCharters: () => ({ data: charters, isLoading: false }),
  useCreateCharter: () => ({ mutate: createMutate, isPending: false }),
  useUpdateCharter: () => ({ mutate: updateMutate, isPending: false }),
  useDeleteCharter: () => ({ mutate: deleteMutate, isPending: false }),
}))

function expand(name: string) {
  fireEvent.click(screen.getByRole('button', { name: `Expand ${name}` }))
}

describe('charter read view', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    charters = [
      { id: 'charter-001', name: 'Tech Lead', content: TECH_LEAD_BODY },
      { id: 'charter-002', name: 'Developer', content: DEVELOPER_BODY },
      { id: 'charter-003', name: 'Empty One', content: '' },
    ]
  })

  it('starts with every charter collapsed', () => {
    render(<ChartersPage />)

    for (const name of ['Tech Lead', 'Developer', 'Empty One']) {
      expect(screen.getByRole('button', { name: `Expand ${name}` })).toHaveAttribute(
        'aria-expanded',
        'false',
      )
    }
  })

  it('reveals the full content when a charter is expanded', () => {
    const { container } = render(<ChartersPage />)
    expect(container.querySelector('#charter-content-charter-001')).toBeNull()

    expand('Tech Lead')

    const region = container.querySelector('#charter-content-charter-001')
    expect(region).not.toBeNull()
    expect(region!.textContent).toBe(TECH_LEAD_BODY)
  })

  it('keeps the whole document out of the DOM while collapsed', () => {
    const { container } = render(<ChartersPage />)

    // line-clamp only clamps what is painted. If the full text stayed in the DOM, a screen
    // reader would read every charter in full and the disclosure would buy its user nothing.
    // "defensible" is the tail of the fixture, past the summary's cut.
    expect(container.textContent).not.toContain('defensible')
    expect(container.textContent).toContain('You Are Accountable For')

    expand('Tech Lead')
    expect(container.textContent).toContain('defensible')
  })

  it('shows the content outside any editable element', () => {
    render(<ChartersPage />)
    expand('Tech Lead')

    const body = screen.getByText(/Making the call when two approaches/)
    // The defect being fixed is that reading and editing were the same surface.
    expect(body.closest('textarea')).toBeNull()
    expect(body.closest('input')).toBeNull()
    expect(body.closest('form')).toBeNull()
    expect(body.getAttribute('contenteditable')).toBeNull()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('keeps the first charter open when a second is expanded', () => {
    render(<ChartersPage />)

    expand('Tech Lead')
    expand('Developer')

    // The requirement a read-only modal would fail, and the reason this is a disclosure.
    expect(screen.getByText(/Making the call when two approaches/)).toBeInTheDocument()
    expect(screen.getByText(/Not written, not plausible/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Collapse Tech Lead' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    expect(screen.getByRole('button', { name: 'Collapse Developer' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
  })

  it('collapses again without touching the other charters', () => {
    const { container } = render(<ChartersPage />)
    expand('Tech Lead')
    expand('Developer')

    fireEvent.click(screen.getByRole('button', { name: 'Collapse Tech Lead' }))

    expect(container.querySelector('#charter-content-charter-001')).toBeNull()
    expect(container.querySelector('#charter-content-charter-002')).not.toBeNull()
  })

  describe('charterSummary', () => {
    it('drops the leading heading, which repeats the name shown above it', () => {
      const summary = charterSummary(TECH_LEAD_BODY)
      expect(summary).not.toContain('# Tech Lead')
      expect(summary.startsWith('## You Are Accountable For')).toBe(true)
    })

    it('truncates long content and marks it as truncated', () => {
      const summary = charterSummary(TECH_LEAD_BODY)
      expect(summary.length).toBeLessThanOrEqual(161)
      expect(summary.endsWith('…')).toBe(true)
    })

    it('leaves short content whole and unmarked', () => {
      expect(charterSummary('Just a sentence.')).toBe('Just a sentence.')
    })

    it('returns empty for empty content, so the row can say "No content"', () => {
      expect(charterSummary('')).toBe('')
      expect(charterSummary('# Only A Title\n')).toBe('')
    })

    it('does not break a word in half at the cut', () => {
      const long = `word ${'alpha '.repeat(60)}`
      expect(charterSummary(long)).not.toMatch(/alph…$/)
    })
  })

  it('names each disclosure after its charter so they are distinguishable', () => {
    render(<ChartersPage />)

    expect(screen.getByRole('button', { name: 'Expand Tech Lead' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Expand Developer' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Expand Empty One' })).toBeInTheDocument()
  })

  it('explains an empty charter rather than showing a blank region', () => {
    render(<ChartersPage />)
    expand('Empty One')

    expect(screen.getByText(/contributes nothing to an agent's turn/)).toBeInTheDocument()
  })

  it('fires no mutation when a charter is read', () => {
    render(<ChartersPage />)

    expand('Tech Lead')
    expand('Developer')
    fireEvent.click(screen.getByRole('button', { name: 'Collapse Tech Lead' }))

    expect(updateMutate).not.toHaveBeenCalled()
    expect(deleteMutate).not.toHaveBeenCalled()
    expect(createMutate).not.toHaveBeenCalled()
  })

  it('does not open the editor when the row is expanded', () => {
    render(<ChartersPage />)
    expand('Tech Lead')

    expect(screen.queryByRole('dialog', { name: 'Edit Charter' })).not.toBeInTheDocument()
  })

  it('keeps a charter open across a refetch that re-renders the rows', () => {
    const { rerender } = render(<ChartersPage />)
    expand('Tech Lead')

    // React Query refetches in the background and hands back fresh objects.
    charters = charters.map((charter) => ({ ...charter }))
    rerender(<ChartersPage />)

    expect(screen.getByText(/Making the call when two approaches/)).toBeInTheDocument()
  })

  it('still offers the editor as a separate action', () => {
    render(<ChartersPage />)

    fireEvent.click(screen.getByRole('button', { name: 'Edit Tech Lead' }))

    expect(screen.getByRole('dialog', { name: 'Edit Charter' })).toBeInTheDocument()
    expect(screen.getByLabelText('Charter content')).toHaveValue(TECH_LEAD_BODY)
  })
})
