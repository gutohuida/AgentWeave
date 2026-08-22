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
})
