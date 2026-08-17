import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Composer, type ComposerProps } from '@/components/agents/Composer'
import { formatElapsedSeconds } from '@/hooks/useElapsedSeconds'

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
  return render(<Composer {...props} />)
}

describe('formatElapsedSeconds', () => {
  it('reads as bare seconds under a minute', () => {
    expect(formatElapsedSeconds(0)).toBe('0s')
    expect(formatElapsedSeconds(59)).toBe('59s')
  })

  it('switches to m:ss at and beyond a minute', () => {
    expect(formatElapsedSeconds(60)).toBe('1:00')
    expect(formatElapsedSeconds(63)).toBe('1:03')
    expect(formatElapsedSeconds(600)).toBe('10:00')
  })
})

describe('Composer — working indicator', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('is absent while idle', () => {
    renderComposer({ isRunning: false })
    expect(screen.queryByTestId('composer-working-indicator')).not.toBeInTheDocument()
  })

  it('appears at 0s the moment a run starts and counts up while it runs', () => {
    const { rerender } = renderComposer({ isRunning: false })
    expect(screen.queryByTestId('composer-working-indicator')).not.toBeInTheDocument()

    rerender(
      <Composer
        agent="claude"
        projectId="proj-1"
        conversationId="conv-1"
        isRunning
        onSubmit={vi.fn().mockResolvedValue(undefined)}
      />,
    )
    expect(screen.getByTestId('composer-working-indicator')).toHaveTextContent('Working · 0s')

    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(screen.getByTestId('composer-working-indicator')).toHaveTextContent('Working · 3s')
  })

  it('disappears the moment the run ends', () => {
    const { rerender } = renderComposer({ isRunning: true })
    expect(screen.getByTestId('composer-working-indicator')).toBeInTheDocument()

    rerender(
      <Composer
        agent="claude"
        projectId="proj-1"
        conversationId="conv-1"
        isRunning={false}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
      />,
    )
    expect(screen.queryByTestId('composer-working-indicator')).not.toBeInTheDocument()
  })

  it('restarts the count from 0 on a fresh run rather than resuming a stale one', () => {
    const { rerender } = renderComposer({ isRunning: true })
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(screen.getByTestId('composer-working-indicator')).toHaveTextContent('Working · 5s')

    rerender(
      <Composer
        agent="claude"
        projectId="proj-1"
        conversationId="conv-1"
        isRunning={false}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
      />,
    )
    rerender(
      <Composer
        agent="claude"
        projectId="proj-1"
        conversationId="conv-1"
        isRunning
        onSubmit={vi.fn().mockResolvedValue(undefined)}
      />,
    )
    expect(screen.getByTestId('composer-working-indicator')).toHaveTextContent('Working · 0s')
  })
})
