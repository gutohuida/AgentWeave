import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SpecStepsSection } from '@/components/settings/sections/SpecStepsSection'
import { ApiError } from '@/api/client'
import type { ProjectJourney } from '@/api/spec'
import { chooseMenuOption } from './support/menuSelect'

/**
 * Project settings → Spec steps (`settings-in-the-app-s-style-where-you-expect-them`, FR-6 and
 * ac-spec-steps). Built-in steps read in words and are marked built in; every change is saved as
 * the whole list at once, with no Save button; a refusal shows the Hub's reason and the list stays
 * as the Hub last stored it.
 *
 * `GET /project/journey` answers `{steps, diagnostics}`, steps in file order.
 */
const save = vi.fn()
let journey: ProjectJourney
let saveError: unknown = null
let loadError: unknown = null

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useProjectJourney: () => ({ data: loadError ? undefined : journey, error: loadError, refetch: vi.fn() }),
    useSaveProjectJourney: () => ({ mutate: save, reset: vi.fn(), isPending: false, isError: Boolean(saveError), error: saveError }),
  }
})

const BUILT_INS = ['intake', 'requirements', 'requirements-and-acceptance', 'acceptance', 'approach', 'tasks', 'build']
const CUSTOM = { key: 'threat-model', title: 'Threat model', instructions: 'List threats.', sizes: ['large' as const] }

beforeEach(() => {
  save.mockReset()
  saveError = null
  loadError = null
  journey = { steps: BUILT_INS.map((key) => ({ key })), diagnostics: [] }
})

/** The steps listed, by the title each row shows, in order. */
const titlesOnPage = () => Array.from(document.querySelectorAll('.aw-step-label')).map((label) => label.textContent!.replace(/^\d+/, '').replace(/Built in$/, ''))
const BUILT_IN_TITLES = ['Intake', 'Requirements', 'Requirements and acceptance', 'Acceptance criteria', 'Approach', 'Tasks', 'Build']
const savedKeys = (call = 0) => save.mock.calls[call]![0].steps.map((s: { key: string }) => s.key)

describe('Spec steps', () => {
  it('names the built-in steps in words, marks them built in, and has no Save or native control', () => {
    render(<SpecStepsSection />)
    for (const title of ['Intake', 'Requirements', 'Requirements and acceptance', 'Acceptance criteria', 'Approach', 'Tasks', 'Build']) {
      expect(screen.getAllByText(title, { exact: true }).length).toBeGreaterThan(0)
    }
    expect(screen.queryByText('requirements-and-acceptance')).toBeNull()
    expect(screen.getAllByText('Built in')).toHaveLength(7)
    expect(screen.queryByRole('button', { name: /^save/i })).toBeNull()
    expect(document.querySelector('input[type=checkbox], input[type=date], select')).toBeNull()
  })

  it('moves an operator step up and stores the whole list at once, built-ins as their key alone', async () => {
    const user = userEvent.setup()
    journey = { steps: [{ key: 'intake' }, { key: 'requirements' }, CUSTOM, ...BUILT_INS.slice(2).map((key) => ({ key }))], diagnostics: [] }
    render(<SpecStepsSection />)
    await user.click(screen.getByLabelText('Move Threat model up'))
    expect(save).toHaveBeenCalledTimes(1)
    expect(savedKeys().slice(0, 3)).toEqual(['intake', 'threat-model', 'requirements'])
    expect(save.mock.calls[0]![0].steps[0]).toEqual({ key: 'intake' })
    expect(save.mock.calls[0]![0].steps[1]).toEqual(CUSTOM)
  })

  it("changes an operator step's sizes in one write", async () => {
    const user = userEvent.setup()
    journey = { steps: [CUSTOM, ...BUILT_INS.map((key) => ({ key }))], diagnostics: [] }
    render(<SpecStepsSection />)
    await user.click(within(screen.getByRole('group', { name: 'Sizes Threat model runs for' })).getByRole('button', { name: 'Small' }))
    expect(save).toHaveBeenCalledTimes(1)
    expect(save.mock.calls[0]![0].steps[0].sizes).toEqual(['small', 'large'])
  })

  it('adds a step after the chosen one with the new step carrying its text and sizes', async () => {
    const user = userEvent.setup()
    render(<SpecStepsSection />)
    await chooseMenuOption(user, /Comes/, 'After Requirements')
    await user.type(screen.getByTestId('spec-steps-new-title'), 'Accessibility check')
    await user.click(screen.getByTestId('spec-steps-new-markdown'))
    await user.paste('## Check\n\n- Name the WCAG level.')
    await user.click(screen.getByTestId('spec-steps-add'))
    expect(savedKeys().slice(0, 3)).toEqual(['intake', 'requirements', 'accessibility-check'])
    expect(save.mock.calls[0]![0].steps[2]).toEqual({ key: 'accessibility-check', title: 'Accessibility check', instructions: '## Check\n\n- Name the WCAG level.', sizes: ['small', 'large'] })
  })

  it('refuses an added step whose title collides with a step, with a reason, and stores nothing', async () => {
    const user = userEvent.setup()
    render(<SpecStepsSection />)
    expect(screen.getByTestId('spec-steps-add')).toBeDisabled()
    await user.type(screen.getByTestId('spec-steps-new-title'), 'Intake')
    await user.click(screen.getByTestId('spec-steps-new-markdown'))
    await user.paste('x')
    await user.click(screen.getByTestId('spec-steps-add'))
    expect(screen.getByText(/already exists/)).toBeInTheDocument()
    expect(save).not.toHaveBeenCalled()
    expect(titlesOnPage()).toEqual(BUILT_IN_TITLES)
  })

  it('removes an operator step but offers no removal or move for a built-in one', async () => {
    const user = userEvent.setup()
    journey = { steps: [{ key: 'intake' }, CUSTOM, ...BUILT_INS.slice(1).map((key) => ({ key }))], diagnostics: [] }
    render(<SpecStepsSection />)
    expect(screen.queryByLabelText('Remove Intake')).toBeNull()
    expect(screen.queryByLabelText('Move Intake down')).toBeNull()
    await user.click(screen.getByLabelText('Remove Threat model'))
    expect(savedKeys()).toEqual(BUILT_INS)
  })

  it('adds an instruction to a built-in step when its field is left, sent as `append`', async () => {
    const user = userEvent.setup()
    render(<SpecStepsSection />)
    await user.click(within(screen.getByText('Intake').closest('[data-slot]') ?? document.body).getAllByRole('button', { name: /Add an instruction/ })[0]!)
    await user.type(screen.getByLabelText('Instruction added to Intake'), 'Ask about sentinel.')
    await user.tab()
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
    expect(save.mock.calls[0]![0].steps[0]).toEqual({ key: 'intake', append: 'Ask about sentinel.' })
  })

  it("shows the Hub's reason for a refused change, and the list as last stored", () => {
    saveError = new ApiError(422, JSON.stringify({ detail: { code: 'journey_invalid', message: 'step threat-model: instructions exceed 2,000 characters' } }))
    journey = { steps: [{ key: 'intake' }, CUSTOM, ...BUILT_INS.slice(1).map((key) => ({ key }))], diagnostics: [{ code: 'journey_file_invalid', message: 'spec/journey.json does not parse' }] }
    render(<SpecStepsSection />)
    expect(screen.getByTestId('spec-steps-refusal')).toHaveTextContent('exceed 2,000 characters')
    expect(screen.getByTestId('spec-steps-diagnostics')).toHaveTextContent('does not parse')
    expect(titlesOnPage()).toEqual(['Intake', 'Threat model', ...BUILT_IN_TITLES.slice(1)])
  })

  it('says so when the steps cannot be read, and shows no list to save over', () => {
    loadError = new ApiError(500, JSON.stringify({ detail: 'the project directory is unavailable' }))
    render(<SpecStepsSection />)
    expect(screen.getByTestId('spec-steps-load-error')).toHaveTextContent('directory is unavailable')
    expect(titlesOnPage()).toEqual([])
  })
})
