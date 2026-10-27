import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { AgentCreateDialog } from '@/components/agents/AgentCreateDialog'

// Task 1.6: measure design.md's D3 inference before judging it, rather than trusting the
// source-reading argument on its own. AgentCreateDialog's name input still uses `autoFocus`
// (task 2.3 has not replaced it with the D1 mark yet), so this is the shape D3 is about.

vi.mock('@/api/agents', () => ({
  useCreateAgent: () => ({ mutate: vi.fn(), isPending: false, error: null, reset: vi.fn() }),
}))
const model = (id: string) => ({ id, label: id, default: true, aliases: [] })
const catalog = {
  providers: [
    { provider: 'claude', label: 'Claude Code', models: [model('sonnet')], controls: [] },
    { provider: 'codex', label: 'Codex CLI', models: [model('gpt')], controls: [] },
  ],
}
vi.mock('@/api/runners', () => ({
  useProviderLaunchability: () => ({
    data: { providers: { claude: { runnable: true }, codex: { runnable: true } } },
  }),
}))
vi.mock('@/api/modelCatalog', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/modelCatalog')>()),
  useModelCatalog: () => ({ data: catalog }),
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

// F1027: the Provider list was hand-built, took no arrow keys and never claimed Escape, so one
// Escape on it closed the whole dialog and threw the typed name away.
describe('the Provider list is one layer (F1027)', () => {
  it('moves with the arrow keys, picks with Enter, and Escape closes only the list', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: 'Add agent' }))
    await user.type(screen.getByLabelText('Agent name'), 'kbtwo')

    const provider = screen.getByRole('button', { name: 'Provider' })
    provider.focus()
    await user.keyboard('{Enter}')
    await screen.findByRole('menu')
    await user.keyboard('{ArrowDown}{Enter}')
    // The arrow moved off the first provider, and Enter picked the one it moved to.
    expect(await screen.findByRole('button', { name: 'Provider' })).toHaveTextContent('Codex CLI')

    provider.focus()
    await user.keyboard('{Enter}')
    await screen.findByRole('menu')
    await user.keyboard('{Escape}')

    expect(screen.queryByRole('menu')).toBeNull()
    expect(screen.getByRole('dialog', { name: 'Create agent' })).toBeInTheDocument()
    expect(screen.getByLabelText('Agent name')).toHaveValue('kbtwo')
    expect(screen.getByRole('button', { name: 'Provider' })).toHaveFocus()

    // A second Escape is the dialog's.
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Create agent' })).toBeNull()
  })
})
