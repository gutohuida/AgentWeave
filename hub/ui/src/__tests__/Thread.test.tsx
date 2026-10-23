import * as React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Thread } from '@/components/thread/Thread'
import { SURFACE, type ThreadKnot, type ThreadLevelData } from '@/api/thread'

function knot(key: string, kind: ThreadKnot['kind'], title: string, children = 0): ThreadKnot {
  return {
    key,
    address: key,
    kind,
    fold_of: null,
    word: kind === 'document' ? 'Document' : kind === 'task' ? 'Task' : 'Run',
    title,
    start: '2026-10-01T09:00:00+00:00',
    end: '2026-10-02T09:00:00+00:00',
    actors: ['Operator'],
    child_count: children,
    descendant_count: children,
    link: kind === 'run' ? { object: 'run', id: 'run-1' } : null,
  }
}

const levels: Record<string, ThreadLevelData> = {
  [SURFACE]: { knots: [knot('d1', 'document', 'First change', 2)], hasBefore: false, hasAfter: false },
  d1: { knots: [knot('t1', 'task', 'Build it'), knot('r1', 'run', 'Builder worked')], hasBefore: false, hasAfter: false },
}

function Harness({ onLink = () => undefined }: { onLink?: () => void }) {
  const [open, setOpen] = React.useState<ReadonlySet<string>>(new Set())
  return (
    <Thread
      levels={levels}
      open={open}
      current={null}
      reveal={0}
      now={new Date('2026-10-23T00:00:00Z')}
      atBeginning
      atPresent
      onToggle={(key) =>
        setOpen((prev) => {
          const next = new Set(prev)
          if (!next.delete(key)) next.add(key)
          return next
        })
      }
      onMore={() => undefined}
      onJumpToBeginning={() => undefined}
      onBackToPresent={() => undefined}
      onOpenLink={onLink}
    />
  )
}

describe('Thread', () => {
  it('shows the face of a knot and opens its children in place', () => {
    render(<Harness />)
    const head = screen.getByRole('button', { name: /First change/ })
    expect(head).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('Document')).toBeInTheDocument()
    expect(screen.getByText('2 knots')).toBeInTheDocument()
    expect(screen.queryByText('Build it')).toBeNull()
    fireEvent.click(head)
    expect(head).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Build it')).toBeInTheDocument()
    fireEvent.click(head)
    expect(screen.queryByText('Build it')).toBeNull()
  })

  it('moves between knots with the arrow keys and opens with ArrowRight', () => {
    render(<Harness />)
    const head = screen.getByRole('button', { name: /First change/ })
    head.focus()
    fireEvent.keyDown(head, { key: 'ArrowRight' })
    expect(head).toHaveAttribute('aria-expanded', 'true')
    fireEvent.keyDown(head, { key: 'ArrowDown' })
    expect(document.activeElement?.textContent).toContain('Build it')
    fireEvent.keyDown(document.activeElement!, { key: 'ArrowLeft' })
    expect(document.activeElement).toBe(head)
  })

  it('offers a link only on a knot that stands for an object', () => {
    const onLink = vi.fn()
    render(<Harness onLink={onLink} />)
    fireEvent.click(screen.getByRole('button', { name: /First change/ }))
    fireEvent.click(screen.getByRole('button', { name: /Open the transcript/ }))
    expect(onLink).toHaveBeenCalledWith({ object: 'run', id: 'run-1' })
    expect(screen.getAllByRole('button', { name: /^Open the/ })).toHaveLength(1)
  })
})
