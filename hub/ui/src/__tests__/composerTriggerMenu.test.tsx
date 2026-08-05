import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Composer, type ComposerProps } from '@/components/agents/Composer'

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: undefined }) }
})

const WORKSPACE_PATHS = [
  'src/index.ts',
  'src/components/agents/Composer.tsx',
  '.claude/skills/aw-status/SKILL.md',
  '.claude/skills/aw-delegate.md',
]

function renderComposer(overrides: Partial<ComposerProps> = {}) {
  const onSubmit = vi.fn().mockResolvedValue(undefined)
  const props: ComposerProps = {
    agent: 'claude',
    projectId: 'proj-1',
    conversationId: 'conv-1',
    isRunning: false,
    onSubmit,
    workspacePaths: WORKSPACE_PATHS,
    ...overrides,
  }
  render(<Composer {...props} />)
  return { onSubmit, textarea: screen.getByRole('textbox') as HTMLTextAreaElement }
}

beforeEach(() => {
  localStorage.clear()
})

describe('Composer — trigger menu', () => {
  it('opens a path menu on "@" scoped to the workspace path listing', async () => {
    const { textarea } = renderComposer()
    await userEvent.type(textarea, '@src')

    const options = screen.getAllByRole('option')
    expect(options.map((el) => el.textContent)).toEqual([
      'src/index.ts',
      'src/components/agents/Composer.tsx',
    ])
  })

  it('opens a skill menu on "$" scoped to .claude/skills/, prefix and suffix stripped', async () => {
    const { textarea } = renderComposer()
    await userEvent.type(textarea, '$aw')

    const options = screen.getAllByRole('option')
    expect(options.map((el) => el.textContent)).toEqual(['aw-status', 'aw-delegate'])
  })

  it('opens a built-in command menu on "/" at line start', async () => {
    const { textarea } = renderComposer()
    await userEvent.type(textarea, '/mod')

    expect(screen.getByRole('option').textContent).toBe('/model')
  })

  it('does not open a menu for a slash mid-sentence', async () => {
    const { textarea } = renderComposer()
    await userEvent.type(textarea, 'see /mod')

    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('arrow-down moves the active result without inserting any text', async () => {
    const { textarea } = renderComposer()
    await userEvent.type(textarea, '@src')

    await userEvent.keyboard('{ArrowDown}')

    expect(textarea.value).toBe('@src')
    const options = screen.getAllByRole('option')
    expect(options[0].getAttribute('aria-selected')).toBe('false')
    expect(options[1].getAttribute('aria-selected')).toBe('true')
  })

  it('Enter accepts the active result, replacing the trigger range and closing the menu', async () => {
    const { textarea } = renderComposer()
    await userEvent.type(textarea, '@src')
    await userEvent.keyboard('{ArrowDown}')

    await userEvent.keyboard('{Enter}')

    expect(textarea.value).toBe('@src/components/agents/Composer.tsx')
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('Tab accepts the active result without moving focus out of the composer', async () => {
    const { textarea } = renderComposer()
    await userEvent.type(textarea, '/mod')

    await userEvent.keyboard('{Tab}')

    expect(textarea.value).toBe('/model')
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(document.activeElement).toBe(textarea)
  })

  it('Escape dismisses the menu without altering text and keeps focus on the composer', async () => {
    const { textarea } = renderComposer()
    await userEvent.type(textarea, '@src')

    await userEvent.keyboard('{Escape}')

    expect(screen.queryByRole('listbox')).toBeNull()
    expect(textarea.value).toBe('@src')
    expect(document.activeElement).toBe(textarea)
  })

  it('Escape does not submit the message', async () => {
    const { textarea, onSubmit } = renderComposer()
    await userEvent.type(textarea, '@src')

    await userEvent.keyboard('{Escape}')

    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('shows a "no matches" state rather than an error for a query with no results', async () => {
    const { textarea } = renderComposer()
    await userEvent.type(textarea, '$nomatch')

    expect(screen.getByText('No matches')).toBeInTheDocument()
    expect(screen.queryByRole('option')).toBeNull()
  })
})
