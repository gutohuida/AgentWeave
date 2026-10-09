import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Composer } from '@/components/agents/Composer'
import type { ModelCatalogResponse } from '@/api/modelCatalog'

const CATALOG: ModelCatalogResponse = {
  providers: [
    {
      provider: 'claude',
      label: 'Claude Code',
      models: [
        { id: 'claude-sonnet-5', label: 'Sonnet 5', aliases: [], context_window: 1_000_000, default: true },
        { id: 'claude-opus-5', label: 'Opus 5', aliases: [], context_window: null, default: false },
      ],
      controls: [],
    },
  ],
}

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: CATALOG }) }
})

beforeEach(() => {
  localStorage.clear()
})

// F553 / overhaul-model-command: the composer's only built-in command used to insert the text
// "/model" and nothing acted on it. It now opens the composer's own model picker.
describe('Composer — the /model command', () => {
  function renderComposer(onPendingOverridesChange = vi.fn()) {
    render(
      <Composer
        agent="claude"
        projectId="proj-1"
        conversationId="conv-1"
        isRunning={false}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        runner="claude"
        onPendingOverridesChange={onPendingOverridesChange}
      />,
    )
    return { textarea: screen.getByRole('textbox') as HTMLTextAreaElement, onPendingOverridesChange }
  }

  it('Enter on /model opens the model picker and leaves no command text behind', async () => {
    const { textarea } = renderComposer()
    await userEvent.type(textarea, '/mod')
    expect(screen.queryByRole('listbox', { name: 'Model' })).toBeNull()

    await userEvent.keyboard('{Enter}')

    expect(screen.getByRole('listbox', { name: 'Model' })).toBeInTheDocument()
    expect(textarea.value).toBe('')
  })

  it('picking a model from the opened picker sets the pending model override', async () => {
    const { textarea, onPendingOverridesChange } = renderComposer()
    await userEvent.type(textarea, '/model')
    await userEvent.keyboard('{Tab}')

    await userEvent.click(screen.getByRole('option', { name: /Opus 5/ }))

    expect(onPendingOverridesChange).toHaveBeenCalledWith({ model: 'claude-opus-5' })
  })

  it('leaves the box empty and ready to type once the picker is open', async () => {
    const { textarea } = renderComposer()
    await userEvent.type(textarea, '/mod')
    await userEvent.keyboard('{Enter}')
    await userEvent.type(textarea, 'hello')

    expect(textarea.value).toBe('hello')
  })
})
