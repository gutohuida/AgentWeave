import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  Composer,
  COMPOSER_DRAFT_DEBOUNCE_MS,
  COMPOSER_MAX_HEIGHT_PX,
  type ComposerProps,
} from '@/components/agents/Composer'
import { getComposerDraft } from '@/lib/composerDrafts'

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: undefined }) }
})

function renderComposer(overrides: Partial<ComposerProps> = {}) {
  const onSubmit = vi.fn().mockResolvedValue(undefined)
  const props: ComposerProps = {
    agent: 'claude',
    projectId: 'proj-1',
    conversationId: 'conv-1',
    isRunning: false,
    onSubmit,
    ...overrides,
  }
  const view = render(<Composer {...props} />)
  return { view, onSubmit, props }
}

describe('Composer considered interaction state', () => {
  it('exposes a stable busy state while submission is pending', async () => {
    let finish!: () => void
    const onSubmit = vi.fn(() => new Promise<void>((resolve) => { finish = resolve }))
    const { view } = renderComposer({ onSubmit })
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Ship this carefully' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    const composer = view.container.querySelector('[data-slot="composer"]')
    await waitFor(() => expect(composer).toHaveAttribute('aria-busy', 'true'))
    expect(composer).toHaveAttribute('data-submitting', 'true')
    expect(screen.getByRole('textbox')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Send message' })).toHaveAttribute('data-state', 'busy')

    finish()
    await waitFor(() => expect(composer).toHaveAttribute('aria-busy', 'false'))
  })
})

describe('Composer — bounded autosizing', () => {
  it('rests at a minimum of 3 text rows', () => {
    renderComposer()
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement
    expect(textarea.rows).toBeGreaterThanOrEqual(3)
  })

  it('stops growing at the maximum height and scrolls the overflow', () => {
    renderComposer()
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement
    Object.defineProperty(textarea, 'scrollHeight', { configurable: true, value: 900 })

    fireEvent.input(textarea, { target: { value: 'line\n'.repeat(40) } })

    expect(textarea.style.height).toBe(`${COMPOSER_MAX_HEIGHT_PX}px`)
    expect(textarea.style.overflowY).toBe('auto')
  })

  it('collapses back to its resting height once a long message is sent', async () => {
    // The reported defect: the box grew as a long prompt was typed and then stayed that
    // tall after sending, until the operator switched conversation and React remounted it.
    // Sizing used to happen in `onInput`, which never fires for a programmatic clear.
    const { onSubmit } = renderComposer()
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement

    Object.defineProperty(textarea, 'scrollHeight', { configurable: true, value: 900 })
    fireEvent.change(textarea, { target: { value: 'line\n'.repeat(40) } })
    await waitFor(() => expect(textarea.style.height).toBe(`${COMPOSER_MAX_HEIGHT_PX}px`))

    // An emptied textarea reports its `rows`-derived height, well under the maximum.
    Object.defineProperty(textarea, 'scrollHeight', { configurable: true, value: 60 })
    fireEvent.keyDown(textarea, { key: 'Enter' })

    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    await waitFor(() => expect(textarea.style.height).toBe('60px'))
  })

  it('grows to fit text it did not receive as keystrokes', async () => {
    // The same gap in the other direction: a restored draft arrives as state, not as
    // input, so the box used to stay short around text that overflowed it.
    const textarea = renderComposerWithDraft()
    await waitFor(() => expect(textarea.style.height).toBe('240px'))
  })
})

function renderComposerWithDraft(): HTMLTextAreaElement {
  const view = render(
    <Composer
      agent="claude"
      projectId="proj-draft"
      conversationId="conv-draft"
      isRunning={false}
      onSubmit={vi.fn().mockResolvedValue(undefined)}
    />
  )
  const textarea = view.container.querySelector('textarea') as HTMLTextAreaElement
  Object.defineProperty(textarea, 'scrollHeight', { configurable: true, value: 240 })
  fireEvent.change(textarea, { target: { value: 'a restored draft\n'.repeat(20) } })
  return textarea
}

describe('Composer — column layout (2026-08-04-hub-charcoal-visual-refresh)', () => {
  it('renders the text area with no control preceding it, and the control row beneath it', () => {
    const { view } = renderComposer()
    const root = view.container.firstElementChild as HTMLElement
    const textarea = screen.getByRole('textbox')
    const controlRow = root.querySelector('[data-slot="composer-control-row"]') as HTMLElement

    // The text area's row is the column's first child — nothing (agent selector, send
    // button) sits before it in the DOM, matching the requirement that the composer's
    // leading edge belongs to text, not a control.
    expect(root.firstElementChild?.contains(textarea)).toBe(true)
    expect(controlRow).not.toBeNull()
    expect(root.contains(controlRow)).toBe(true)
    // The control row is a later sibling of the text area's row, so it renders beneath it.
    const textareaRowIndex = Array.from(root.children).findIndex((child) => child.contains(textarea))
    const controlRowIndex = Array.from(root.children).indexOf(controlRow)
    expect(controlRowIndex).toBeGreaterThan(textareaRowIndex)
  })

  it('keeps a leading slot for composer controls and a trailing slot for send', () => {
    const { view } = renderComposer()
    const root = view.container.firstElementChild as HTMLElement
    const leading = root.querySelector('[data-slot="composer-control-row-leading"]') as HTMLElement
    const trailing = root.querySelector('[data-slot="composer-control-row-trailing"]') as HTMLElement

    expect(leading).not.toBeNull()
    expect(trailing.querySelector('[aria-label="Send message"]')).not.toBeNull()
    expect(
      leading.compareDocumentPosition(trailing) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    // The conversation-routing pill used to live in the leading slot. Conversation selection is
    // navigation's job now, and no control on this surface may act as a second switcher.
    expect(root.textContent).not.toContain('New conversation')
  })
})

describe('Composer — project- and conversation-scoped drafts', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('survives leaving the conversation and returning to it', () => {
    const { view } = renderComposer({ conversationId: 'conv-1' })
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'draft for conv-1' } })
    view.unmount()

    render(<Composer agent="claude" projectId="proj-1" conversationId="conv-1" isRunning={false} onSubmit={vi.fn()} />)
    expect(screen.getByRole('textbox')).toHaveValue('draft for conv-1')
  })

  it('survives a reload, modelled as a fresh mount reading the same storage', () => {
    const { view } = renderComposer({ conversationId: 'conv-1' })
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'reload me' } })
    view.unmount()

    render(<Composer agent="claude" projectId="proj-1" conversationId="conv-1" isRunning={false} onSubmit={vi.fn()} />)
    expect(screen.getByRole('textbox')).toHaveValue('reload me')
  })

  it('does not leak between two conversations of one agent', () => {
    const first = renderComposer({ conversationId: 'conv-a' })
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'text for A' } })
    first.view.unmount()

    const second = renderComposer({ conversationId: 'conv-b' })
    expect(screen.getByRole('textbox')).toHaveValue('')
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'text for B' } })
    second.view.unmount()

    render(<Composer agent="claude" projectId="proj-1" conversationId="conv-a" isRunning={false} onSubmit={vi.fn()} />)
    expect(screen.getByRole('textbox')).toHaveValue('text for A')
  })

  it('does not leak between two projects for the same agent and not-yet-created conversation', () => {
    const first = renderComposer({ projectId: 'proj-1', conversationId: null })
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'proj-1 draft' } })
    first.view.unmount()

    render(<Composer agent="claude" projectId="proj-2" conversationId={null} isRunning={false} onSubmit={vi.fn()} />)
    expect(screen.getByRole('textbox')).toHaveValue('')
  })

  it('clears the draft on successful submission with no delayed write restoring it', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    renderComposer({ conversationId: 'conv-1', onSubmit })
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'send me' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith('send me'))
    await new Promise((resolve) => setTimeout(resolve, COMPOSER_DRAFT_DEBOUNCE_MS + 100))

    expect(getComposerDraft('proj-1', 'claude', 'conv-1')).toBe('')
  })

  it('restores the composer text when submission fails', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('failed'))
    renderComposer({ conversationId: 'conv-1', onSubmit })
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'keep me' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    expect(screen.getByRole('textbox')).toHaveValue('')
    await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue('keep me'))
  })

  it('stays fully functional when storage is unavailable', () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied')
    })
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied')
    })

    expect(() => renderComposer()).not.toThrow()
    const textarea = screen.getByRole('textbox')
    expect(() => fireEvent.change(textarea, { target: { value: 'no storage available' } })).not.toThrow()
    expect(textarea).toHaveValue('no storage available')

    getItem.mockRestore()
    setItem.mockRestore()
  })
})

describe('Composer — insertPathRequest (task 5.4, 2026-08-18-one-shell-three-panels)', () => {
  it('appends a @path mention on the composer’s current text', () => {
    const { view } = renderComposer({
      insertPathRequest: { path: 'src/a.ts', requestId: 1 },
    })

    expect(screen.getByRole('textbox')).toHaveValue('@src/a.ts ')
    view.unmount()
  })

  it('quote-escapes a path containing whitespace, same as the @path trigger', () => {
    renderComposer({ insertPathRequest: { path: 'docs/release notes.md', requestId: 1 } })

    expect(screen.getByRole('textbox')).toHaveValue('@"docs/release notes.md" ')
  })

  it('appends to existing text rather than replacing it, adding a separating space', () => {
    const { view, props } = renderComposer({ insertPathRequest: null })
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'see' } })

    view.rerender(<Composer {...props} insertPathRequest={{ path: 'src/a.ts', requestId: 1 }} />)

    expect(screen.getByRole('textbox')).toHaveValue('see @src/a.ts ')
  })

  it('a repeated requestId for the same path does not insert a second time', () => {
    const { view, props } = renderComposer({ insertPathRequest: { path: 'src/a.ts', requestId: 1 } })

    view.rerender(<Composer {...props} insertPathRequest={{ path: 'src/a.ts', requestId: 1 }} />)

    expect(screen.getByRole('textbox')).toHaveValue('@src/a.ts ')
  })

  it('a new requestId for the same path inserts again', () => {
    const { view, props } = renderComposer({ insertPathRequest: { path: 'src/a.ts', requestId: 1 } })

    view.rerender(<Composer {...props} insertPathRequest={{ path: 'src/a.ts', requestId: 2 }} />)

    expect(screen.getByRole('textbox')).toHaveValue('@src/a.ts @src/a.ts ')
  })
})
