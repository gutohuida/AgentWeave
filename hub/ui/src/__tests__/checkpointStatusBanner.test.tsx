import { render, screen } from '@testing-library/react'
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
})
