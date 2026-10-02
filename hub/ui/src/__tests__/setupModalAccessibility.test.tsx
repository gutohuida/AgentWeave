import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { SetupModal } from '@/components/layout/SetupModal'
import { useConfigStore } from '@/store/configStore'

describe('SetupModal accessibility', () => {
  it('is a named modal with associated fields, pressed mode, and initial focus', async () => {
    useConfigStore.setState({
      hubUrl: 'http://localhost:8010',
      apiKey: '',
      selectedProjectId: null,
      mode: 'dark',
    })
    render(<SetupModal open onClose={vi.fn()} />)
    expect(screen.getByRole('dialog', { name: 'Connect to AgentWeave Hub' })).toHaveAttribute('aria-modal', 'true')
    const url = screen.getByRole('textbox', { name: 'Hub URL' })
    expect(screen.getByLabelText('API Key')).toHaveAttribute('type', 'password')
    expect(screen.getByRole('button', { name: 'Dark' })).toHaveAttribute('aria-pressed', 'true')
    await waitFor(() => expect(url).toHaveFocus())
  })

  // Task 1.12: SetupModal is always mounted (App.tsx:617) and toggles via its `open` prop, not
  // unmount/remount — so this rerenders the same component instance rather than mounting a fresh
  // one, matching how useDialogFocus's `active` dependency actually fires here.
  it('returns focus to the trigger once the dialog closes (D3)', async () => {
    useConfigStore.setState({
      hubUrl: 'http://localhost:8010',
      apiKey: '',
      selectedProjectId: null,
      mode: 'dark',
    })
    function Harness({ open }: { open: boolean }) {
      return (
        <>
          <button>Open setup</button>
          <SetupModal open={open} onClose={vi.fn()} />
        </>
      )
    }
    const { rerender } = render(<Harness open={false} />)
    const trigger = screen.getByRole('button', { name: 'Open setup' })
    trigger.focus()
    expect(trigger).toHaveFocus()

    rerender(<Harness open />)
    const url = screen.getByRole('textbox', { name: 'Hub URL' })
    await waitFor(() => expect(url).toHaveFocus())

    rerender(<Harness open={false} />)
    // Red today: SetupModal's own effect (`:20-22`) only ever focuses the URL field and records
    // nothing to restore, so closing leaves focus on `<body>` instead of the trigger.
    await waitFor(() => expect(trigger).toHaveFocus())
  })
})
