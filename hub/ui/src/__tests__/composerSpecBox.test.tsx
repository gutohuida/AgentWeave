import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Composer, type ComposerProps } from '@/components/agents/Composer'
import { getComposerDraft } from '@/lib/composerDrafts'
import { formatSpecReference } from '@/lib/specReference'
import { composerText, setComposerText } from './testUtils/composerField'

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: undefined }) }
})

// The documents in the order the documents route returns them (insertion order, oldest first).
const SPECS = [
  { id: 'spdoc-000000000001', title: 'Ref B: older', path: 'spec/changes/b/spec.json', updated_at: '2026-11-10T10:00:00+00:00' },
  { id: 'spdoc-000000000002', title: 'Ref C: newest', path: 'spec/changes/c/spec.json', updated_at: '2026-11-18T10:00:00+00:00' },
]
const C_TOKEN = formatSpecReference({ id: 'spdoc-000000000002', title: 'Ref C: newest' })

function renderComposer(overrides: Partial<ComposerProps> = {}) {
  const onSubmit = vi.fn().mockResolvedValue(undefined)
  const props: ComposerProps = {
    agent: 'claude',
    projectId: 'proj-1',
    conversationId: 'conv-1',
    isRunning: false,
    onSubmit,
    workspacePaths: ['docs/refs.md'],
    specDocuments: SPECS,
    ...overrides,
  }
  const view = render(<Composer {...props} />)
  return { view, onSubmit, field: screen.getByRole('textbox') }
}

beforeEach(() => {
  localStorage.clear()
})

describe('Composer — a spec picked from @ becomes a box (FR-2)', () => {
  it('lists Specs above Files, newest spec first', async () => {
    const { field } = renderComposer()
    await userEvent.type(field, '@ref')
    const menu = screen.getByRole('listbox')
    expect([...menu.querySelectorAll('[data-testid=composer-menu-group]')].map((el) => el.textContent)).toEqual([
      'Specs',
      'Files',
    ])
    expect(screen.getAllByRole('option').map((el) => el.getAttribute('data-label'))).toEqual([
      'Ref C: newest',
      'Ref B: older',
      'docs/refs.md',
    ])
  })

  it('replaces the typed @query with one box and a space, and sends its text form', async () => {
    const { field, onSubmit } = renderComposer()
    await userEvent.type(field, 'The spec @ref')
    await userEvent.keyboard('{Enter}')

    expect(screen.queryByRole('listbox')).toBeNull()
    expect(field.querySelectorAll('[data-spec-box]')).toHaveLength(1)
    expect(composerText(field)).toBe(`The spec ${C_TOKEN} `)

    fireEvent.keyDown(field, { key: 'Enter' })
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(`The spec ${C_TOKEN}`))
  })

  it('stores a draft holding boxes as their text form, and draws them again on a fresh mount (FR-7)', async () => {
    const first = renderComposer()
    setComposerText(first.field, `see ${C_TOKEN} now`)
    first.view.unmount()
    expect(getComposerDraft('proj-1', 'claude', 'conv-1')).toBe(`see ${C_TOKEN} now`)

    const { field } = renderComposer()
    expect(field.querySelectorAll('[data-spec-box]')).toHaveLength(1)
    expect(composerText(field)).toBe(`see ${C_TOKEN} now`)
  })
})

describe('Composer — the @ menu while the document list is not known', () => {
  it('says the specs could not be loaded, rather than showing none, and keeps the files', async () => {
    const { field } = renderComposer({ specDocuments: undefined, specDocumentsStatus: 'error' })
    await userEvent.type(field, '@refs')
    expect(screen.getByTestId('composer-specs-notice')).toHaveTextContent('Specs could not be loaded')
    expect(screen.getAllByTestId('composer-menu-group').map((el) => el.textContent)).toEqual(['Specs', 'Files'])
    expect(screen.getAllByRole('option').map((el) => el.getAttribute('data-label'))).toEqual(['docs/refs.md'])
  })

  it('says the specs are loading while the list is on its way, and only for @', async () => {
    const { field } = renderComposer({ specDocuments: undefined, specDocumentsStatus: 'loading' })
    await userEvent.type(field, '@')
    expect(screen.getByTestId('composer-specs-notice')).toHaveTextContent('Loading specs…')
    setComposerText(field, '/mod')
    expect(screen.queryByTestId('composer-specs-notice')).toBeNull()
  })
})

describe('Composer — the visible reference control (FR-5)', () => {
  it('opens the same menu, and picking from it gives what typing @ and picking gives', async () => {
    const byControl = renderComposer({ conversationId: 'conv-control' })
    await userEvent.click(screen.getByRole('button', { name: 'Insert a reference' }))
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    fireEvent.mouseDown(screen.getAllByRole('option')[0])
    const viaControl = composerText(byControl.field)
    byControl.view.unmount()

    const byTyping = renderComposer({ conversationId: 'conv-typing' })
    await userEvent.type(byTyping.field, '@')
    fireEvent.mouseDown(screen.getAllByRole('option')[0])
    expect(composerText(byTyping.field)).toBe(viaControl)
    expect(viaControl).toBe(`${C_TOKEN} `)
  })

  it('separates the @ it types from a word the caret follows', async () => {
    const { field } = renderComposer()
    setComposerText(field, 'see')
    await userEvent.click(screen.getByRole('button', { name: 'Insert a reference' }))
    expect(composerText(field)).toBe('see @')
    expect(screen.getByRole('listbox')).toBeInTheDocument()
  })
})
