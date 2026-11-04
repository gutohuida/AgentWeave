import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { CheckpointStatusBanner } from '@/components/checkpoints/CheckpointStatusBanner'
import { useConfigStore } from '@/store/configStore'
import { useCheckpointOperationStore } from '@/store/checkpointOperationStore'

describe('checkpoint status across navigation', () => {
  beforeEach(() => {
    useConfigStore.setState({ selectedProjectId: 'proj-test' })
    useCheckpointOperationStore.setState({ operations: {} })
  })

  it('keeps showing an in-flight checkpoint after the current screen unmounts', () => {
    useCheckpointOperationStore.getState().setOperation('proj-test:conv-old', {
      projectId: 'proj-test',
      conversationId: 'conv-old',
      status: 'writing',
      message: 'Writing checkpoint…',
      startedAt: 1,
    })

    const firstScreen = render(<CheckpointStatusBanner />)
    expect(screen.getByTestId('checkpoint-global-status')).toHaveTextContent('Writing checkpoint')
    firstScreen.unmount()

    render(<CheckpointStatusBanner />)
    expect(screen.getByTestId('checkpoint-global-status')).toHaveTextContent('Writing checkpoint')
  })

  it('shows the worker failure instead of an empty-summary euphemism', () => {
    useCheckpointOperationStore.getState().setOperation('proj-test:conv-old', {
      projectId: 'proj-test',
      conversationId: 'conv-old',
      status: 'failed',
      message: 'Checkpoint failed: worker exceeded 180s',
      startedAt: 1,
    })

    render(<CheckpointStatusBanner />)
    expect(screen.getByRole('status')).toHaveTextContent('worker exceeded 180s')
  })

  it('opens the checkpoint it names once there is one (FR-14)', () => {
    window.history.replaceState(null, '', '/')
    useCheckpointOperationStore.getState().setOperation('proj-test:conv-old', {
      projectId: 'proj-test',
      conversationId: 'conv-old',
      status: 'succeeded',
      message: 'Checkpoint written — continuing in the successor conversation.',
      checkpointId: 'ckpt-9',
      startedAt: 1,
    })
    render(<CheckpointStatusBanner />)
    fireEvent.click(screen.getByTestId('checkpoint-status-open'))
    const params = new URLSearchParams(window.location.search)
    expect(params.get('tab')).toBe('checkpoints')
    expect(params.get('checkpoint')).toBe('ckpt-9')
  })

  it('offers nothing to open while the checkpoint is still being written', () => {
    useCheckpointOperationStore.getState().setOperation('proj-test:conv-old', {
      projectId: 'proj-test',
      conversationId: 'conv-old',
      status: 'writing',
      message: 'Writing checkpoint…',
      startedAt: 1,
    })
    render(<CheckpointStatusBanner />)
    expect(screen.queryByTestId('checkpoint-status-open')).not.toBeInTheDocument()
  })
})
