/// <reference types="vite/client" />
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
// @ts-expect-error Vitest runs in Node; the browser bundle never includes this contract test.
import { readFileSync } from 'node:fs'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { ComposerModelControls, composerControlClassName } from '@/components/agents/ComposerModelControls'
import type { ModelCatalogResponse } from '@/api/modelCatalog'

const CATALOG: ModelCatalogResponse = {
  providers: [
    {
      provider: 'claude',
      label: 'Claude Code',
      models: [
        { id: 'claude-sonnet-5', label: 'Sonnet 5', aliases: [], context_window: 1_000_000, default: true, windows: [] },
        { id: 'claude-opus-5', label: 'Opus 5', aliases: [], context_window: null, default: false, windows: [] },
        // The one model in the real catalog whose two windows genuinely differ.
        {
          id: 'claude-haiku-4-5-20251001',
          label: 'Haiku 4.5',
          aliases: [],
          context_window: 200_000,
          default: false,
          windows: [
            { id: 'claude-haiku-4-5-20251001', label: '200K', context_window: 200_000, default: true },
            { id: 'claude-haiku-4-5-20251001[1m]', label: '1M', context_window: 1_000_000, default: false },
          ],
        },
      ],
      controls: [
        {
          id: 'effort',
          label: 'Effort',
          kind: 'enum',
          values: [
            { id: 'medium', label: 'Medium' },
            { id: 'high', label: 'High' },
          ],
          default: 'medium',
          apply: { style: 'flag', template: '--effort {value}' },
        },
      ],
    },
    {
      provider: 'codex',
      label: 'Codex CLI',
      models: [
        { id: 'gpt-5.6-sol', label: 'GPT-5.6-Sol', aliases: [], context_window: 272_000, default: true, windows: [] },
      ],
      controls: [
        {
          id: 'effort',
          label: 'Effort',
          kind: 'enum',
          values: [{ id: 'low', label: 'Low' }],
          default: 'low',
          apply: { style: 'config', template: 'model_reasoning_effort={value}' },
        },
      ],
    },
  ],
}

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: CATALOG }) }
})

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('ComposerModelControls — controls follow the provider', () => {
  it('renders the Claude model and effort pills for a claude runner', () => {
    render(
      <ComposerModelControls
        runner="claude"
        effectiveModel={null}
        effectiveControls={{}}
        onChangeModel={vi.fn()}
        onChangeControl={vi.fn()}
      />,
      { wrapper },
    )
    expect(screen.getByTitle('Model')).toHaveTextContent('Sonnet 5')
    expect(screen.getByTitle('Effort')).toHaveTextContent('Medium')
  })

  it('re-derives the presented controls when the runner changes to a different provider', () => {
    const { rerender } = render(
      <ComposerModelControls
        runner="claude"
        effectiveModel={null}
        effectiveControls={{}}
        onChangeModel={vi.fn()}
        onChangeControl={vi.fn()}
      />,
      { wrapper },
    )
    expect(screen.getByTitle('Model')).toHaveTextContent('Sonnet 5')

    rerender(
      <ComposerModelControls
        runner="codex"
        effectiveModel={null}
        effectiveControls={{}}
        onChangeModel={vi.fn()}
        onChangeControl={vi.fn()}
      />,
    )
    expect(screen.getByTitle('Model')).toHaveTextContent('GPT-5.6-Sol')
    expect(screen.getByTitle('Effort')).toHaveTextContent('Low')
  })

  it('renders nothing for a runner the catalog does not declare', () => {
    const { container } = render(
      <ComposerModelControls
        runner="manual"
        effectiveModel={null}
        effectiveControls={{}}
        onChangeModel={vi.fn()}
        onChangeControl={vi.fn()}
      />,
      { wrapper },
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('calls onChangeModel with the selected model id', () => {
    const onChangeModel = vi.fn()
    render(
      <ComposerModelControls
        runner="claude"
        effectiveModel={null}
        effectiveControls={{}}
        onChangeModel={onChangeModel}
        onChangeControl={vi.fn()}
      />,
      { wrapper },
    )
    fireEvent.click(screen.getByTitle('Model'))
    fireEvent.click(screen.getByRole('option', { name: 'Opus 5' }))
    expect(onChangeModel).toHaveBeenCalledWith('claude-opus-5')
  })

  it('calls onChangeControl with the control id and selected value', () => {
    const onChangeControl = vi.fn()
    render(
      <ComposerModelControls
        runner="claude"
        effectiveModel={null}
        effectiveControls={{}}
        onChangeModel={vi.fn()}
        onChangeControl={onChangeControl}
      />,
      { wrapper },
    )
    fireEvent.click(screen.getByTitle('Effort'))
    fireEvent.click(screen.getByRole('option', { name: 'High' }))
    expect(onChangeControl).toHaveBeenCalledWith('effort', 'high')
  })
})

function stripComments(source: string): string {
  return source.replace(/\/\*\*?[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')
}

describe('composer controls share one bare, content-sized appearance (composer/chrome refinement §2)', () => {
  it('composerControlClassName declares no border and no fixed width', () => {
    expect(composerControlClassName).not.toMatch(/\bborder/)
    expect(composerControlClassName).not.toMatch(/\bw-\d/)
  })

  it('composerControlClassName rounds fully, matching the pill size variant it pairs with', () => {
    expect(composerControlClassName).toContain('rounded-full')
  })

  it('the model pill trigger renders as a real <button> exposing a focus indicator', () => {
    render(
      <ComposerModelControls
        runner="claude"
        effectiveModel={null}
        effectiveControls={{}}
        onChangeModel={vi.fn()}
        onChangeControl={vi.fn()}
      />,
      { wrapper },
    )
    const trigger = screen.getByTitle('Model')
    expect(trigger.tagName).toBe('BUTTON')
    expect(trigger.className).toMatch(/focus-visible:ring-2/)
  })

  it('ControlPill.tsx declares no fixed minimum-width on its popover', () => {
    // `min-w-0` elsewhere in this file is the ordinary flex-truncation escape hatch, not a
    // padded-out minimum — only a pixel/token minimum (`min-w-[...]`) is the regression.
    const code = readFileSync('src/components/agents/ComposerModelControls.tsx', 'utf8')
    expect(code).not.toMatch(/\bmin-w-\[/)
  })
})

describe('the composer control components hardcode no provider models or control values', () => {
  it('ComposerModelControls.tsx declares no provider/model/control literal in code (comments aside)', () => {
    const code = stripComments(
      readFileSync('src/components/agents/ComposerModelControls.tsx', 'utf8'),
    ).toLowerCase()
    for (const literal of ['claude', 'codex', 'sonnet', 'opus', 'gpt-', 'effort', 'medium', 'high']) {
      expect(code, `should not hardcode "${literal}"`).not.toContain(literal)
    }
  })
})

describe('ComposerModelControls — the context window is a choice where there is one', () => {
  it('offers no context pill for a model with one window', () => {
    // A control offering one choice is not a choice, and the composer is already dense.
    render(
      <ComposerModelControls
        runner="claude"
        effectiveModel="claude-sonnet-5"
        effectiveControls={{}}
        onChangeModel={vi.fn()}
        onChangeControl={vi.fn()}
      />,
      { wrapper },
    )
    expect(screen.queryByTitle('Context')).not.toBeInTheDocument()
  })

  it('offers the windows a model declares, showing the default at rest', () => {
    render(
      <ComposerModelControls
        runner="claude"
        effectiveModel="claude-haiku-4-5-20251001"
        effectiveControls={{}}
        onChangeModel={vi.fn()}
        onChangeControl={vi.fn()}
      />,
      { wrapper },
    )
    const pill = screen.getByTitle('Context')
    expect(pill).toHaveTextContent('200K')

    fireEvent.click(pill)
    expect(screen.getByRole('option', { name: '1M' })).toBeInTheDocument()
  })

  it('selects a window by setting the model override to that window own id', () => {
    // A variant *is* a model id — nothing downstream of this pill learns a second concept.
    const onChangeModel = vi.fn()
    render(
      <ComposerModelControls
        runner="claude"
        effectiveModel="claude-haiku-4-5-20251001"
        effectiveControls={{}}
        onChangeModel={onChangeModel}
        onChangeControl={vi.fn()}
      />,
      { wrapper },
    )
    fireEvent.click(screen.getByTitle('Context'))
    fireEvent.click(screen.getByRole('option', { name: '1M' }))

    expect(onChangeModel).toHaveBeenCalledWith('claude-haiku-4-5-20251001[1m]')
  })

  it('still names the model when one of its windows is selected', () => {
    // A bare id comparison would fail to find the model and the pill would read "—" for a model
    // that is plainly selected.
    render(
      <ComposerModelControls
        runner="claude"
        effectiveModel="claude-haiku-4-5-20251001[1m]"
        effectiveControls={{}}
        onChangeModel={vi.fn()}
        onChangeControl={vi.fn()}
      />,
      { wrapper },
    )
    expect(screen.getByTitle('Model')).toHaveTextContent('Haiku 4.5')
    expect(screen.getByTitle('Context')).toHaveTextContent('1M')
  })
})
