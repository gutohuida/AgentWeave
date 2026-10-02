import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { AgentCreateDialog } from '@/components/agents/AgentCreateDialog'

// Task 1.6: measure design.md's D3 inference before judging it, rather than trusting the
// source-reading argument on its own. AgentCreateDialog's name input still uses `autoFocus`
// (task 2.3 has not replaced it with the D1 mark yet), so this is the shape D3 is about.

vi.mock('@/api/agents', () => ({
  useCreateAgent: () => ({ mutate: vi.fn(), isPending: false, error: null, reset: vi.fn() }),
}))
vi.mock('@/api/runners', () => ({
  useProviderLaunchability: () => ({ data: { providers: {} } }),
}))
vi.mock('@/api/modelCatalog', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/modelCatalog')>()),
  useModelCatalog: () => ({ data: { providers: [] } }),
}))
vi.mock('@/api/charters', () => ({
  useCharters: () => ({ data: [], isLoading: false }),
}))

function Harness() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button onClick={() => setOpen(true)}>Add agent</button>
      <AgentCreateDialog open={open} onClose={() => setOpen(false)} onCreated={vi.fn()} />
    </>
  )
}

describe('useDialogFocus — restore on close (D3)', () => {
  it('returns focus to the trigger after Escape, even when the dialog opened with autoFocus', () => {
    render(<Harness />)
    const trigger = screen.getByRole('button', { name: 'Add agent' })
    trigger.focus()
    fireEvent.click(trigger)

    // React's own `autoFocus` has already moved the keyboard onto the name input by the time
    // this assertion runs -- this is the condition D3's argument describes, not a simulation of it.
    expect(screen.getByLabelText('Agent name')).toHaveFocus()

    fireEvent.keyDown(document, { key: 'Escape' })

    // D3's claim, measured: `returnFocusTo` is captured in the hook's effect, which runs after
    // `autoFocus` has already moved focus onto the input in the commit phase -- so it captures
    // the input, not the trigger. The input unmounts before the cleanup's `returnFocusTo?.focus()`
    // runs, targeting a detached node, so focus is left on `<body>` instead of the trigger. This
    // is red today for that reason; task 1.7 is this same assertion passing after the fix.
    expect(trigger).toHaveFocus()
  })
})
