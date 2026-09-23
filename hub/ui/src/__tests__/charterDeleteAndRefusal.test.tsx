import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { ChartersPage } from '@/components/charters/ChartersPage'

// F186: the delete control hard-deleted on one click. F187: the create/update form dropped the
// Hub's refusal on the floor. Both are exercised through the real page with the mutations mocked
// at the API-hook boundary, so what is asserted is what the operator sees.

const createMutate = vi.fn()
const updateMutate = vi.fn()
const deleteMutate = vi.fn()

vi.mock('@/api/charters', () => ({
  useCharters: () => ({
    data: [
      {
        id: 'charter-authored',
        project_id: 'proj-test',
        name: 'House Rules',
        content: 'Line one.\nLine two.\nLine three.\n',
        created_at: '2026-08-03T00:00:00Z',
        updated_at: '2026-08-03T00:00:00Z',
      },
    ],
    isLoading: false,
  }),
  useCreateCharter: () => ({ mutate: createMutate, isPending: false }),
  useUpdateCharter: () => ({ mutate: updateMutate, isPending: false }),
  useDeleteCharter: () => ({ mutate: deleteMutate, isPending: false }),
}))

// The body FastAPI returns for a name past VisibleName's 256 characters.
const TOO_LONG = new ApiError(422, JSON.stringify({
  detail: [{
    type: 'string_too_long',
    loc: ['body', 'name'],
    msg: 'String should have at most 256 characters',
    input: 'x'.repeat(300),
    ctx: { max_length: 256 },
  }],
}))

describe('charter delete asks first (F186)', () => {
  beforeEach(() => {
    createMutate.mockReset()
    updateMutate.mockReset()
    deleteMutate.mockReset()
  })

  it('does not delete on the first click, and says what would be lost', async () => {
    const user = userEvent.setup()
    render(<ChartersPage />)

    await user.click(screen.getByRole('button', { name: 'Delete House Rules' }))

    expect(deleteMutate).not.toHaveBeenCalled()
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('Delete the charter “House Rules”?')
    expect(dialog).toHaveTextContent('3 lines of authored text will be lost')
    expect(dialog).toHaveTextContent('AgentWeave keeps no copy')
  })

  it('deletes only after the confirmation', async () => {
    const user = userEvent.setup()
    render(<ChartersPage />)

    await user.click(screen.getByRole('button', { name: 'Delete House Rules' }))
    await user.click(screen.getByRole('button', { name: 'Delete charter' }))

    expect(deleteMutate).toHaveBeenCalledTimes(1)
    expect(deleteMutate).toHaveBeenCalledWith('charter-authored', expect.any(Object))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('cancel keeps the charter', async () => {
    const user = userEvent.setup()
    render(<ChartersPage />)

    await user.click(screen.getByRole('button', { name: 'Delete House Rules' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(deleteMutate).not.toHaveBeenCalled()
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it("shows the route's refusal when the charter is still bound", async () => {
    deleteMutate.mockImplementation((_id: string, options: { onError: (e: unknown) => void }) => {
      options.onError(new ApiError(409, JSON.stringify({
        detail: 'Charter is bound to agent(s): claude. Unbind before deleting.',
      })))
    })
    const user = userEvent.setup()
    render(<ChartersPage />)

    await user.click(screen.getByRole('button', { name: 'Delete House Rules' }))
    await user.click(screen.getByRole('button', { name: 'Delete charter' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Charter is bound to agent(s): claude. Unbind before deleting.')
  })
})

describe('the charter form renders its own refusal (F187)', () => {
  beforeEach(() => {
    createMutate.mockReset()
    updateMutate.mockReset()
  })

  it('a refused create says why, inside the form, and the form stays open', async () => {
    createMutate.mockImplementation((_values: unknown, options: { onError: (e: unknown) => void }) => {
      options.onError(TOO_LONG)
    })
    const user = userEvent.setup()
    render(<ChartersPage />)

    await user.click(screen.getByRole('button', { name: 'New Charter' }))
    await user.type(screen.getByLabelText('Charter name'), 'x'.repeat(30))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    const dialog = screen.getByRole('dialog', { name: 'New Charter' })
    expect(dialog).toContainElement(screen.getByRole('alert'))
    expect(screen.getByRole('alert')).toHaveTextContent('String should have at most 256 characters')
  })

  it('a refused edit says why', async () => {
    updateMutate.mockImplementation((_values: unknown, options: { onError: (e: unknown) => void }) => {
      options.onError(TOO_LONG)
    })
    const user = userEvent.setup()
    render(<ChartersPage />)

    await user.click(screen.getByRole('button', { name: 'Edit House Rules' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(screen.getByRole('alert')).toHaveTextContent('String should have at most 256 characters')
  })

  it('a reopened form does not carry the previous refusal', async () => {
    createMutate.mockImplementation((_values: unknown, options: { onError: (e: unknown) => void }) => {
      options.onError(TOO_LONG)
    })
    const user = userEvent.setup()
    render(<ChartersPage />)

    await user.click(screen.getByRole('button', { name: 'New Charter' }))
    await user.type(screen.getByLabelText('Charter name'), 'y')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await user.click(screen.getByRole('button', { name: 'New Charter' }))

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
