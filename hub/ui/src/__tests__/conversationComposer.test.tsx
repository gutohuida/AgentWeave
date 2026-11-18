import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  Composer,
  COMPOSER_DRAFT_DEBOUNCE_MS,
  COMPOSER_MAX_HEIGHT_PX,
  COMPOSER_MIN_HEIGHT_PX,
  type ComposerProps,
} from '@/components/agents/Composer'
import { getComposerDraft } from '@/lib/composerDrafts'
import { setComposerText, composerText } from './testUtils/composerField'

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
    setComposerText(screen.getByRole('textbox'), 'Ship this carefully')
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    const composer = view.container.querySelector('[data-slot="composer"]')
    await waitFor(() => expect(composer).toHaveAttribute('aria-busy', 'true'))
    expect(composer).toHaveAttribute('data-submitting', 'true')
    // The field is contenteditable: while sending it stops being editable and says it is disabled.
    expect(screen.getByRole('textbox')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('textbox')).toHaveAttribute('contenteditable', 'false')
    expect(screen.getByRole('button', { name: 'Send message' })).toHaveAttribute('data-state', 'busy')

    finish()
    await waitFor(() => expect(composer).toHaveAttribute('aria-busy', 'false'))
  })
})

// The field is contenteditable, so it grows with its content by layout: no height is computed in
// script, so there is none to go stale after a programmatic change (the defect the textarea's
// effect fixed). What remains to hold is the bounds: three rows at rest, the maximum, then scroll.
describe('Composer — bounded autosizing', () => {
  it('rests at a minimum of 3 text rows', () => {
    renderComposer()
    const field = screen.getByRole('textbox')
    expect(COMPOSER_MIN_HEIGHT_PX).toBeGreaterThanOrEqual(3 * 20)
    expect(field.style.minHeight).toBe(`${COMPOSER_MIN_HEIGHT_PX}px`)
  })

  it('stops growing at the maximum height and scrolls the overflow', () => {
    renderComposer()
    const field = screen.getByRole('textbox')
    setComposerText(field, 'line\n'.repeat(40))

    expect(field.style.maxHeight).toBe(`${COMPOSER_MAX_HEIGHT_PX}px`)
    expect(field.style.overflowY).toBe('auto')
  })

  it('empties the field once a long message is sent', async () => {
    const { onSubmit } = renderComposer()
    const field = screen.getByRole('textbox')
    setComposerText(field, 'line\n'.repeat(40))
    fireEvent.keyDown(field, { key: 'Enter' })

    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    expect(field.textContent).toBe('')
  })

  it('draws a restored draft it did not receive as keystrokes', () => {
    localStorage.clear()
    const first = renderComposer({ projectId: 'proj-draft', conversationId: 'conv-draft' })
    setComposerText(screen.getByRole('textbox'), 'a restored draft\n'.repeat(3))
    first.view.unmount()
    renderComposer({ projectId: 'proj-draft', conversationId: 'conv-draft' })
    expect(composerText(screen.getByRole('textbox'))).toBe('a restored draft\n'.repeat(3))
  })
})

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
    setComposerText(screen.getByRole('textbox'), 'draft for conv-1')
    view.unmount()

    render(<Composer agent="claude" projectId="proj-1" conversationId="conv-1" isRunning={false} onSubmit={vi.fn()} />)
    expect(composerText(screen.getByRole('textbox'))).toBe('draft for conv-1')
  })

  it('survives a reload, modelled as a fresh mount reading the same storage', () => {
    const { view } = renderComposer({ conversationId: 'conv-1' })
    setComposerText(screen.getByRole('textbox'), 'reload me')
    view.unmount()

    render(<Composer agent="claude" projectId="proj-1" conversationId="conv-1" isRunning={false} onSubmit={vi.fn()} />)
    expect(composerText(screen.getByRole('textbox'))).toBe('reload me')
  })

  it('does not leak between two conversations of one agent', () => {
    const first = renderComposer({ conversationId: 'conv-a' })
    setComposerText(screen.getByRole('textbox'), 'text for A')
    first.view.unmount()

    const second = renderComposer({ conversationId: 'conv-b' })
    expect(composerText(screen.getByRole('textbox'))).toBe('')
    setComposerText(screen.getByRole('textbox'), 'text for B')
    second.view.unmount()

    render(<Composer agent="claude" projectId="proj-1" conversationId="conv-a" isRunning={false} onSubmit={vi.fn()} />)
    expect(composerText(screen.getByRole('textbox'))).toBe('text for A')
  })

  it('does not leak between two projects for the same agent and not-yet-created conversation', () => {
    const first = renderComposer({ projectId: 'proj-1', conversationId: null })
    setComposerText(screen.getByRole('textbox'), 'proj-1 draft')
    first.view.unmount()

    render(<Composer agent="claude" projectId="proj-2" conversationId={null} isRunning={false} onSubmit={vi.fn()} />)
    expect(composerText(screen.getByRole('textbox'))).toBe('')
  })

  it('clears the draft on successful submission with no delayed write restoring it', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    renderComposer({ conversationId: 'conv-1', onSubmit })
    setComposerText(screen.getByRole('textbox'), 'send me')
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith('send me'))
    await new Promise((resolve) => setTimeout(resolve, COMPOSER_DRAFT_DEBOUNCE_MS + 100))

    expect(getComposerDraft('proj-1', 'claude', 'conv-1')).toBe('')
  })

  it('restores the composer text when submission fails', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('failed'))
    renderComposer({ conversationId: 'conv-1', onSubmit })
    setComposerText(screen.getByRole('textbox'), 'keep me')
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    expect(composerText(screen.getByRole('textbox'))).toBe('')
    await waitFor(() => expect(composerText(screen.getByRole('textbox'))).toBe('keep me'))
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
    expect(() => setComposerText(textarea, 'no storage available')).not.toThrow()
    expect(composerText(textarea)).toBe('no storage available')

    getItem.mockRestore()
    setItem.mockRestore()
  })
})

describe('Composer — insertPathRequest (task 5.4, 2026-08-18-one-shell-three-panels)', () => {
  it('appends a @path mention on the composer’s current text', () => {
    const { view } = renderComposer({
      insertPathRequest: { path: 'src/a.ts', requestId: 1 },
    })

    expect(composerText(screen.getByRole('textbox'))).toBe('@src/a.ts ')
    view.unmount()
  })

  it('quote-escapes a path containing whitespace, same as the @path trigger', () => {
    renderComposer({ insertPathRequest: { path: 'docs/release notes.md', requestId: 1 } })

    expect(composerText(screen.getByRole('textbox'))).toBe('@"docs/release notes.md" ')
  })

  it('appends to existing text rather than replacing it, adding a separating space', () => {
    const { view, props } = renderComposer({ insertPathRequest: null })
    setComposerText(screen.getByRole('textbox'), 'see')

    view.rerender(<Composer {...props} insertPathRequest={{ path: 'src/a.ts', requestId: 1 }} />)

    expect(composerText(screen.getByRole('textbox'))).toBe('see @src/a.ts ')
  })

  it('a repeated requestId for the same path does not insert a second time', () => {
    const { view, props } = renderComposer({ insertPathRequest: { path: 'src/a.ts', requestId: 1 } })

    view.rerender(<Composer {...props} insertPathRequest={{ path: 'src/a.ts', requestId: 1 }} />)

    expect(composerText(screen.getByRole('textbox'))).toBe('@src/a.ts ')
  })

  it('ignores an unsafe path (F409 D10) and inserts a safe one as today', () => {
    const { view, props } = renderComposer({ insertPathRequest: null })
    view.rerender(
      <Composer {...props} insertPathRequest={{ path: 'x @/home/u/.ssh/id_rsa', requestId: 1 }} />,
    )
    expect(composerText(screen.getByRole('textbox'))).toBe('')

    view.rerender(<Composer {...props} insertPathRequest={{ path: 'src/app.py', requestId: 2 }} />)
    expect(composerText(screen.getByRole('textbox'))).toBe('@src/app.py ')
  })

  it('a new requestId for the same path inserts again', () => {
    const { view, props } = renderComposer({ insertPathRequest: { path: 'src/a.ts', requestId: 1 } })

    view.rerender(<Composer {...props} insertPathRequest={{ path: 'src/a.ts', requestId: 2 }} />)

    expect(composerText(screen.getByRole('textbox'))).toBe('@src/a.ts @src/a.ts ')
  })
})

describe('Composer — insertTextRequest (the terminal tab\'s Send to agent)', () => {
  it('appends the text to the draft, on its own line, and does not send it', () => {
    const { view, props } = renderComposer({ insertTextRequest: null })
    setComposerText(screen.getByRole('textbox'), 'look at this')

    view.rerender(<Composer {...props} insertTextRequest={{ text: 'Terminal output:\nok', requestId: 1 }} />)
    expect(composerText(screen.getByRole('textbox'))).toBe('look at this\nTerminal output:\nok')

    view.rerender(<Composer {...props} insertTextRequest={{ text: 'Terminal output:\nok', requestId: 1 }} />)
    expect(composerText(screen.getByRole('textbox'))).toBe('look at this\nTerminal output:\nok')
  })
})
