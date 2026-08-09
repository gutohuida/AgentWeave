import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
// @ts-expect-error Vitest runs in Node; the browser bundle never includes this contract test.
import { readFileSync } from 'node:fs'
import { ModelPicker } from '@/components/agents/ModelPicker'
import type { ProviderDescriptor } from '@/api/modelCatalog'

const PROVIDER: ProviderDescriptor = {
  provider: 'claude',
  label: 'Claude Code',
  models: [
    { id: 'claude-sonnet-5', label: 'Sonnet 5', aliases: [], context_window: 1_000_000, default: true },
    { id: 'claude-opus-5', label: 'Opus 5', aliases: [], context_window: null, default: false },
    { id: 'claude-haiku-5', label: 'Haiku 5', aliases: [], context_window: 200_000, default: false },
  ],
  controls: [],
}

function open() {
  fireEvent.click(screen.getByTitle('Model'))
}

describe('ModelPicker — search, grouping, favourites (composer/chrome refinement §4b)', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('finds a model by a non-prefix substring match', () => {
    render(<ModelPicker provider={PROVIDER} effectiveModel={null} onChangeModel={vi.fn()} />)
    open()
    fireEvent.change(screen.getByLabelText('Search models'), { target: { value: 'aik' } })
    expect(screen.getByRole('option', { name: 'Haiku 5' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Sonnet 5' })).not.toBeInTheDocument()
  })

  it('finds every model in a group by the provider name alone', () => {
    render(<ModelPicker provider={PROVIDER} effectiveModel={null} onChangeModel={vi.fn()} />)
    open()
    fireEvent.change(screen.getByLabelText('Search models'), { target: { value: 'claude code' } })
    expect(screen.getAllByRole('option')).toHaveLength(3)
  })

  it('groups entries under a labelled provider section', () => {
    render(<ModelPicker provider={PROVIDER} effectiveModel={null} onChangeModel={vi.fn()} />)
    open()
    expect(screen.getByText('Claude Code')).toBeInTheDocument()
  })

  it('never surfaces a model outside the offered set — filters, does not widen', () => {
    render(<ModelPicker provider={PROVIDER} effectiveModel={null} onChangeModel={vi.fn()} />)
    open()
    fireEvent.change(screen.getByLabelText('Search models'), { target: { value: 'gpt' } })
    expect(screen.queryAllByRole('option')).toHaveLength(0)
  })

  it('shows an empty-result state that clears back to the full list', () => {
    render(<ModelPicker provider={PROVIDER} effectiveModel={null} onChangeModel={vi.fn()} />)
    open()
    fireEvent.change(screen.getByLabelText('Search models'), { target: { value: 'nonexistent-model' } })
    expect(screen.getByText(/No models match/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Clear search' }))
    expect(screen.getAllByRole('option')).toHaveLength(3)
  })

  it('presents a favourited model first', () => {
    render(<ModelPicker provider={PROVIDER} effectiveModel={null} onChangeModel={vi.fn()} />)
    open()
    fireEvent.click(screen.getByRole('button', { name: 'Add Haiku 5 to favourites' }))
    const options = screen.getAllByRole('option')
    expect(options[0]).toHaveAccessibleName('Haiku 5')
  })

  it('persists a favourite across a remount (reload)', () => {
    const { unmount } = render(<ModelPicker provider={PROVIDER} effectiveModel={null} onChangeModel={vi.fn()} />)
    open()
    fireEvent.click(screen.getByRole('button', { name: 'Add Opus 5 to favourites' }))
    unmount()

    render(<ModelPicker provider={PROVIDER} effectiveModel={null} onChangeModel={vi.fn()} />)
    open()
    expect(screen.getAllByRole('option')[0]).toHaveAccessibleName('Opus 5')
  })

  it('favouriting changes ordering only — the resolved model is untouched', () => {
    const onChangeModel = vi.fn()
    render(<ModelPicker provider={PROVIDER} effectiveModel={null} onChangeModel={onChangeModel} />)
    open()
    fireEvent.click(screen.getByRole('button', { name: 'Add Haiku 5 to favourites' }))
    expect(onChangeModel).not.toHaveBeenCalled()
    expect(screen.getByTitle('Model')).toHaveTextContent('Sonnet 5')
  })

  it('supports full keyboard operation: open, narrow, move, select', () => {
    const onChangeModel = vi.fn()
    render(<ModelPicker provider={PROVIDER} effectiveModel={null} onChangeModel={onChangeModel} />)
    open()
    const search = screen.getByLabelText('Search models')
    fireEvent.change(search, { target: { value: 'o' } }) // Sonnet 5, Opus 5
    fireEvent.keyDown(search, { key: 'ArrowDown' })
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(onChangeModel).toHaveBeenCalledWith('claude-opus-5')
  })

  it('dismiss (Escape) selects nothing and leaves the current model unchanged', () => {
    const onChangeModel = vi.fn()
    render(<ModelPicker provider={PROVIDER} effectiveModel="claude-sonnet-5" onChangeModel={onChangeModel} />)
    open()
    fireEvent.keyDown(screen.getByLabelText('Search models'), { key: 'Escape' })
    expect(onChangeModel).not.toHaveBeenCalled()
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(screen.getByTitle('Model')).toHaveTextContent('Sonnet 5')
  })

  it('declares no fixed width on the picker (content-derived per §2, task 4b.10)', () => {
    // A bare `w-N` (a fixed width) is banned; `max-w-N` (a content-derived cap, per
    // design.md Decision 2) is exactly the allowed pattern — excluded by requiring the
    // token start at a class-string boundary, never preceded by "max-".
    const code = readFileSync('src/components/agents/ModelPicker.tsx', 'utf8')
    expect(code).not.toMatch(/\bmin-w-\[/)
    expect(code).not.toMatch(/(?:^|[\s"'`])w-\d/)
  })
})
