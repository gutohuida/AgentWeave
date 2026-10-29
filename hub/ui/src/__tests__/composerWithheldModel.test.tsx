import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Composer } from '@/components/agents/Composer'
import { overridesForRunner, withheldStoredModel } from '@/lib/runnerProvider'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

// `rebinding-an-agents-runner-starts-clean` (FR-10, F1024): a conversation can store a model its
// agent's bound CLI does not offer — Claude's `haiku` on an agent since rebound to Copilot. The Hub
// withholds it at the launch (`model_applies_to_cli`) and runs the runner's own model; the
// composer's pill has to say the same, or it reads a model the next turn will not run.

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: MODEL_CATALOG_FIXTURE }) }
})

beforeEach(() => {
  localStorage.clear()
})

function renderComposer(props: {
  runner: string
  runnerModel: string | null
  stored: Record<string, string>
}) {
  const onSubmit = vi.fn().mockResolvedValue(undefined)
  const onPendingOverridesChange = vi.fn()
  render(
    <Composer
      agent="a1"
      projectId="proj-1"
      conversationId="conv-1"
      isRunning={false}
      onSubmit={onSubmit}
      runner={props.runner}
      effectiveModel={props.runnerModel}
      pendingOverrides={props.stored}
      onPendingOverridesChange={onPendingOverridesChange}
    />,
  )
  return { onSubmit, onPendingOverridesChange }
}

describe('the composer shows the model that will run', () => {
  it('reads the runner model, with a line naming the withheld one, when the CLI does not offer it', () => {
    renderComposer({ runner: 'copilot', runnerModel: 'claude-haiku-4.5', stored: { model: 'haiku' } })

    const pill = screen.getByTitle(/^Model:/)
    expect(pill).toHaveTextContent('Claude Haiku 4.5')
    expect(pill).not.toHaveTextContent('unrecognised')
    const line = screen.getByTestId('composer-withheld-model')
    expect(line).toHaveTextContent('haiku')
    expect(line).toHaveTextContent('not offered by copilot')
  })

  it('shows the stored model and no line when the bound CLI offers it (by alias, as the Hub does)', () => {
    renderComposer({ runner: 'claude', runnerModel: 'claude-sonnet-5', stored: { model: 'haiku' } })

    expect(screen.getByTitle(/^Model:/)).toHaveTextContent('Haiku 4.5')
    expect(screen.queryByTestId('composer-withheld-model')).toBeNull()
  })

  it('applies a model no CLI declares, as the Hub does: a retired model keeps working where it is stored', () => {
    renderComposer({ runner: 'copilot', runnerModel: 'auto', stored: { model: 'retired-model-x' } })

    expect(screen.getByTitle(/^Model:/)).toHaveTextContent('retired-model-x')
    expect(screen.queryByTestId('composer-withheld-model')).toBeNull()
  })

  it('keeps the withheld model in the pending overrides when the operator changes another control', async () => {
    const { onPendingOverridesChange } = renderComposer({
      runner: 'copilot',
      runnerModel: 'claude-haiku-4.5',
      stored: { model: 'haiku' },
    })

    await userEvent.click(screen.getByTitle(/^Permissions:/))
    await userEvent.click(screen.getByRole('option', { name: 'Ask me' }))

    expect(onPendingOverridesChange).toHaveBeenCalledWith({ model: 'haiku', permission_mode: 'manual' })
  })

  it('sends without removing the withheld model from the stored overrides', async () => {
    const { onSubmit, onPendingOverridesChange } = renderComposer({
      runner: 'copilot',
      runnerModel: 'claude-haiku-4.5',
      stored: { model: 'haiku' },
    })

    await userEvent.type(screen.getByRole('textbox'), 'carry on')
    await userEvent.click(screen.getByRole('button', { name: 'Send message' }))

    expect(onSubmit).toHaveBeenCalledWith('carry on')
    // The panel sends the pending overrides back with the message, and the Hub refuses a model it
    // was not given stored: dropping `haiku` here would get the next send a 400.
    expect(onPendingOverridesChange).not.toHaveBeenCalled()
    expect(screen.getByTestId('composer-withheld-model')).toHaveTextContent('haiku')
    expect(overridesForRunner({ model: 'haiku', effort: 'high' }, { provider_config: null })).toEqual({
      model: 'haiku',
      effort: 'high',
    })
  })
})

describe('withheldStoredModel', () => {
  it('names a stored model only another CLI declares', () => {
    expect(withheldStoredModel(MODEL_CATALOG_FIXTURE, 'copilot', 'haiku')).toBe('haiku')
    expect(withheldStoredModel(MODEL_CATALOG_FIXTURE, 'claude', 'claude-haiku-4.5')).toBe('claude-haiku-4.5')
    expect(withheldStoredModel(MODEL_CATALOG_FIXTURE, 'codex', 'haiku')).toBe('haiku')
  })

  it('names nothing when the CLI declares it, when none does, or when there is nothing stored', () => {
    expect(withheldStoredModel(MODEL_CATALOG_FIXTURE, 'claude', 'haiku')).toBeNull()
    expect(withheldStoredModel(MODEL_CATALOG_FIXTURE, 'copilot', 'claude-haiku-4.5')).toBeNull()
    expect(withheldStoredModel(MODEL_CATALOG_FIXTURE, 'copilot', 'retired-model-x')).toBeNull()
    expect(withheldStoredModel(MODEL_CATALOG_FIXTURE, 'copilot', undefined)).toBeNull()
    expect(withheldStoredModel(undefined, 'copilot', 'haiku')).toBeNull()
    expect(withheldStoredModel(MODEL_CATALOG_FIXTURE, 'manual', 'haiku')).toBeNull()
  })
})
