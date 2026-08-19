/**
 * The Hub refuses to open a folder whose marker names a project this database has never heard
 * of, and the sentence it returns tells the operator to "register the copy explicitly as new."
 * `ProjectManagerModal` offers a button for exactly that remedy, gated on the refusal's `code`
 * (never its prose, which is free to be reworded) — this holds the button's visibility to that
 * one code, and its click to the one field (`register_copy_as_new: true`) the remedy is.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { ProjectManagerModal } from '@/components/projects/ProjectManagerModal'
import { ApiError } from '@/api/client'

function refusal(detail: unknown): ApiError {
  return new ApiError(409, JSON.stringify({ detail }))
}

const openMutate = vi.fn()
const createMutate = vi.fn()
let openError: ApiError | null = null
let createError: ApiError | null = null

vi.mock('@/api/projects', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/projects')>()
  return {
    ...actual,
    useCreateProject: () => ({ mutate: createMutate, isPending: false, error: createError, reset: vi.fn() }),
    useOpenProject: () => ({ mutate: openMutate, isPending: false, error: openError, reset: vi.fn() }),
  }
})

vi.mock('@/api/nativeDialog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/nativeDialog')>()
  return {
    ...actual,
    useNativeDialogAvailability: () => ({ data: { available: false } }),
    useOpenNativeDialog: () => ({ mutate: vi.fn(), isPending: false }),
  }
})

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('ProjectManagerModal — the identity-conflict remedy', () => {
  beforeEach(() => {
    openMutate.mockReset()
    createMutate.mockReset()
    openError = null
    createError = null
  })

  it('offers no remedy while there is no error', () => {
    render(<ProjectManagerModal mode="open" onClose={vi.fn()} onComplete={vi.fn()} />, { wrapper })
    expect(screen.queryByTestId('register-copy-as-new')).not.toBeInTheDocument()
  })

  it('offers no remedy for a refusal that is not an identity conflict', () => {
    openError = refusal({ code: 'validation_error', message: 'That path does not exist.' })
    render(<ProjectManagerModal mode="open" onClose={vi.fn()} onComplete={vi.fn()} />, { wrapper })
    expect(screen.getByRole('alert')).toHaveTextContent('That path does not exist.')
    expect(screen.queryByTestId('register-copy-as-new')).not.toBeInTheDocument()
  })

  it('offers no remedy in create mode, even on that code — the conflict only arises when opening', () => {
    createError = refusal({ code: 'project_identity_conflict', message: 'irrelevant here' })
    render(<ProjectManagerModal mode="create" onClose={vi.fn()} onComplete={vi.fn()} />, { wrapper })
    expect(screen.getByRole('alert')).toHaveTextContent('irrelevant here')
    expect(screen.queryByTestId('register-copy-as-new')).not.toBeInTheDocument()
  })

  it('offers the remedy on a project_identity_conflict refusal, and resubmits with register_copy_as_new', () => {
    openError = refusal({
      code: 'project_identity_conflict',
      message: 'This folder is already bound to a different AgentWeave database.',
    })
    render(<ProjectManagerModal mode="open" onClose={vi.fn()} onComplete={vi.fn()} />, { wrapper })
    fireEvent.change(screen.getByLabelText('Directory path'), { target: { value: '/some/path' } })

    const remedy = screen.getByTestId('register-copy-as-new')
    expect(remedy).toBeInTheDocument()
    fireEvent.click(remedy)

    expect(openMutate).toHaveBeenCalledTimes(1)
    const [input] = openMutate.mock.calls[0]
    expect(input).toEqual({ path: '/some/path', register_copy_as_new: true })
  })
})
