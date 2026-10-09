import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SpecStepsSection } from '@/components/environment/SpecStepsSection'
import { ApiError } from '@/api/client'
import type { ProjectJourney } from '@/api/spec'

/**
 * The project page's Spec steps section (`a-project-orders-its-own-spec-steps`, FR-6): the
 * operator reads the project's steps in file order, inserts a pasted-Markdown step at any
 * position, appends an instruction to a step, removes a custom step, and saves.
 *
 * `GET /project/journey` answers `{steps, diagnostics}`, steps in file order (the seven built-in
 * keys with `requirements-and-acceptance` between requirements and acceptance).
 */
const save = vi.fn()
let journey: ProjectJourney
let saveError: unknown = null
let loadError: unknown = null

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useProjectJourney: () => ({ data: loadError ? undefined : journey, error: loadError }),
    useSaveProjectJourney: () => ({ mutate: save, isPending: false, error: saveError }),
  }
})

const BUILT_INS = [
  'intake',
  'requirements',
  'requirements-and-acceptance',
  'acceptance',
  'approach',
  'tasks',
  'delivery',
]

beforeEach(() => {
  save.mockReset()
  saveError = null
  loadError = null
  journey = { steps: BUILT_INS.map((key) => ({ key })), diagnostics: [] }
})

const keysOnPage = () =>
  screen
    .getAllByTestId(/^spec-steps-row-/)
    .map((row) => row.getAttribute('data-testid')!.replace('spec-steps-row-', ''))

describe('Spec steps section', () => {
  it('lists the project steps in the order the file holds them', () => {
    render(<SpecStepsSection />)
    expect(keysOnPage()).toEqual(BUILT_INS)
  })

  it('inserts pasted Markdown as a custom step after the chosen one, and saves exactly that', async () => {
    const user = userEvent.setup()
    render(<SpecStepsSection />)
    await user.selectOptions(screen.getByTestId('spec-steps-add-after'), 'requirements')
    await user.type(screen.getByTestId('spec-steps-new-title'), 'Accessibility check')
    await user.click(screen.getByTestId('spec-steps-new-markdown'))
    await user.paste('## Check\n\n- Name the WCAG level.')
    await user.click(screen.getByTestId('spec-steps-add'))
    expect(keysOnPage().slice(0, 3)).toEqual(['intake', 'requirements', 'accessibility-check'])

    await user.click(screen.getByTestId('spec-steps-save'))
    const saved = save.mock.calls[0][0].steps
    expect(saved.map((s: { key: string }) => s.key)).toEqual([
      'intake',
      'requirements',
      'accessibility-check',
      'requirements-and-acceptance',
      'acceptance',
      'approach',
      'tasks',
      'delivery',
    ])
    expect(saved[2]).toEqual({
      key: 'accessibility-check',
      title: 'Accessibility check',
      instructions: '## Check\n\n- Name the WCAG level.',
      sizes: ['small', 'large'],
    })
    // Built-in entries carry their key alone (the wire shape the route stores).
    expect(saved[0]).toEqual({ key: 'intake' })
  })

  it('appends an instruction to a built-in step and sends it as `append`', async () => {
    const user = userEvent.setup()
    render(<SpecStepsSection />)
    const row = screen.getByTestId('spec-steps-row-intake')
    await user.type(within(row).getByLabelText('Instruction appended to intake'), 'Ask about sentinel.')
    await user.click(screen.getByTestId('spec-steps-save'))
    expect(save.mock.calls[0][0].steps[0]).toEqual({ key: 'intake', append: 'Ask about sentinel.' })
  })

  it('removes a custom step but offers no removal for a built-in one', async () => {
    const user = userEvent.setup()
    journey = {
      steps: [
        { key: 'intake' },
        { key: 'threat-model', title: 'Threat model', instructions: 'List threats.', sizes: ['large'] },
        ...BUILT_INS.slice(1).map((key) => ({ key })),
      ],
      diagnostics: [],
    }
    render(<SpecStepsSection />)
    expect(
      within(screen.getByTestId('spec-steps-row-intake')).queryByLabelText('Remove intake'),
    ).toBeNull()
    await user.click(within(screen.getByTestId('spec-steps-row-threat-model')).getByLabelText('Remove threat-model'))
    expect(keysOnPage()).toEqual(BUILT_INS)
  })

  it('moves a custom step up and down among the others', async () => {
    const user = userEvent.setup()
    journey = {
      steps: [
        { key: 'intake' },
        { key: 'requirements' },
        { key: 'threat-model', title: 'Threat model', instructions: 'List threats.', sizes: ['large'] },
        ...BUILT_INS.slice(2).map((key) => ({ key })),
      ],
      diagnostics: [],
    }
    render(<SpecStepsSection />)
    await user.click(screen.getByLabelText('Move threat-model down'))
    expect(keysOnPage().slice(2, 5)).toEqual([
      'requirements-and-acceptance',
      'threat-model',
      'acceptance',
    ])
  })

  it('shows the diagnostics the Hub read the file with and the refusal a save met', () => {
    journey = {
      steps: BUILT_INS.map((key) => ({ key })),
      diagnostics: [{ code: 'journey_file_invalid', message: 'spec/journey.json does not parse' }],
    }
    saveError = new ApiError(
      422,
      JSON.stringify({
        detail: { code: 'journey_invalid', message: 'step threat-model: instructions exceed 2,000 characters' },
      }),
    )
    render(<SpecStepsSection />)
    expect(screen.getByTestId('spec-steps-diagnostics')).toHaveTextContent('does not parse')
    expect(screen.getByTestId('spec-steps-refusal')).toHaveTextContent('exceed 2,000 characters')
  })

  it('refuses to add a step with no title or no Markdown, and a key already in use', async () => {
    const user = userEvent.setup()
    render(<SpecStepsSection />)
    expect(screen.getByTestId('spec-steps-add')).toBeDisabled()
    await user.type(screen.getByTestId('spec-steps-new-title'), 'Intake')
    await user.click(screen.getByTestId('spec-steps-new-markdown'))
    await user.paste('x')
    await user.click(screen.getByTestId('spec-steps-add'))
    expect(screen.getByTestId('spec-steps-add-error')).toHaveTextContent('intake')
    expect(keysOnPage()).toEqual(BUILT_INS)
  })

  it('says so when the steps cannot be read, and offers no save over a journey it never saw', () => {
    loadError = new ApiError(500, JSON.stringify({ detail: 'the project directory is unavailable' }))
    render(<SpecStepsSection />)
    expect(screen.getByTestId('spec-steps-load-error')).toHaveTextContent('directory is unavailable')
    expect(screen.getByTestId('spec-steps-save')).toBeDisabled()
  })
})
