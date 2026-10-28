import { describe, it, expect, vi, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
// @ts-expect-error Vitest runs in Node; the browser bundle never includes this test.
import { readFileSync } from 'node:fs'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecPickerContainer } from '@/components/spec/page/SpecPanelContainer'
import { GapLines } from '@/components/spec/SpecPhaseParts'
import { CommandPalette } from '@/components/palette/CommandPalette'

/* Slice F drive: the picker dialog clipped (B), the approval-gaps block overflowed at 360 px (B),
 * and Ctrl+Shift+K opened the palette under the picker (C). jsdom cannot measure widths, so the
 * layout cases assert the structural cause. */

vi.mock('@/api/spec', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...real,
    useSpecList: () => ({
      data: {
        specs: [{ path: 'spec/a.json', title: 'A', state: 'filed', document_id: 'spdoc-1', parent: null }],
        home: null,
        manifest: { state: 'absent', version: 1 },
        missing: [],
        diagnostics: [],
      },
      isLoading: false,
      refetch: () => undefined,
    }),
    useSpecDocuments: () => ({ data: { documents: [] } }),
  }
})

afterEach(cleanup)

const headerCss = readFileSync('src/styles/spec-header.css', 'utf8') as string

describe('picker dialog layout', () => {
  it('stacks the corpus strip above the picker instead of beside it', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <SpecPickerContainer onOpen={vi.fn()} onNew={vi.fn()} />
      </QueryClientProvider>,
    )
    const wrapper = screen.getByTestId('spec-picker')
    // `.aw-sp` is a flex ROW (spec-page.css); two children beside each other overflow the dialog.
    expect(wrapper.style.flexDirection).toBe('column')
    expect(wrapper.style.minWidth).toBe('0px')
  })
})

describe('approval gaps at 360 px', () => {
  it('lets gap lines shrink and wrap long unbreakable text', () => {
    render(
      <GapLines
        gaps={[{ code: 'steps_skipped', where: 'spec/changes/x/spec.json', message: 'POST /api/v1/spec/journey?path=spec/changes/some-very-long-name/spec.json' }]}
      />,
    )
    const li = screen.getByTestId('approval-warning-steps_skipped')
    expect(li.parentElement!.className).toContain('min-w-0')
    expect(li.className).toContain('min-w-0')
    expect(li.querySelector('span')!.className).toContain('min-w-0')
    expect(li.querySelector('span')!.className).toContain('overflow-wrap:anywhere')
  })

  it('does not give the message text a fixed 200px floor, and wraps anywhere', () => {
    const sheet = headerCss
    expect(sheet).not.toMatch(/\.aw-spec-message-text\s*\{[^}]*min-width:\s*200px/)
    expect(sheet).toMatch(/\.aw-spec-message\s*\{[^}]*overflow-wrap:\s*anywhere/)
  })
})

describe('Ctrl+Shift+K', () => {
  it('does not open the command palette (the picker owns the chord)', () => {
    render(
      <CommandPalette
        agents={[]}
        conversations={[]}
        documents={[]}
        tasks={[]}
        onOpenConversation={vi.fn()}
        onOpenAgent={vi.fn()}
        onOpenDocument={vi.fn()}
        onOpenTask={vi.fn()}
      />,
    )
    fireEvent.keyDown(document, { key: 'K', ctrlKey: true, shiftKey: true })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true })
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})
