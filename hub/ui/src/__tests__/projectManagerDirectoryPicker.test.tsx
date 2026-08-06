import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { ProjectManagerModal } from '@/components/projects/ProjectManagerModal'

vi.mock('@/api/fsBrowse', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/fsBrowse')>()
  return {
    ...actual,
    useDirectoryListing: () => ({
      data: { path: '/home/projects', parent: '/home', entries: [{ name: 'agentweave', path: '/home/projects/agentweave' }] },
      isLoading: false,
    }),
  }
})

vi.mock('@/api/projects', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/projects')>()
  return {
    ...actual,
    useCreateProject: () => ({ mutate: vi.fn(), isPending: false, error: null, reset: vi.fn() }),
    useOpenProject: () => ({ mutate: vi.fn(), isPending: false, error: null, reset: vi.fn() }),
  }
})

const nativeDialogAvailability = vi.fn()
const nativeDialogMutate = vi.fn()

vi.mock('@/api/nativeDialog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/nativeDialog')>()
  return {
    ...actual,
    useNativeDialogAvailability: () => nativeDialogAvailability(),
    useOpenNativeDialog: () => ({ mutate: nativeDialogMutate, isPending: false }),
  }
})

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('ProjectManagerModal — directory browsing supplements typing', () => {
  beforeEach(() => {
    nativeDialogAvailability.mockReturnValue({ data: { available: false } })
    nativeDialogMutate.mockReset()
  })

  it('typing a path remains available without opening the picker', () => {
    render(<ProjectManagerModal mode="open" onClose={vi.fn()} onComplete={vi.fn()} />, { wrapper })
    fireEvent.change(screen.getByLabelText('Directory path'), { target: { value: '/typed/path' } })
    expect(screen.getByLabelText('Directory path')).toHaveValue('/typed/path')
    expect(screen.queryByRole('dialog', { name: 'Browse for a directory' })).not.toBeInTheDocument()
  })

  it('opens the picker and fills the path field when a directory is chosen (native dialog unavailable)', () => {
    render(<ProjectManagerModal mode="open" onClose={vi.fn()} onComplete={vi.fn()} />, { wrapper })
    fireEvent.click(screen.getByRole('button', { name: 'Open directory browser' }))
    expect(screen.getByRole('dialog', { name: 'Browse for a directory' })).toBeInTheDocument()
    fireEvent.doubleClick(screen.getByText('agentweave'))
    expect(screen.getByLabelText('Directory path')).toHaveValue('/home/projects/agentweave')
    expect(screen.queryByRole('dialog', { name: 'Browse for a directory' })).not.toBeInTheDocument()
  })
})

describe('ProjectManagerModal — native folder dialog (composer/chrome refinement §8)', () => {
  beforeEach(() => {
    nativeDialogMutate.mockReset()
  })

  it('offers the native dialog only when the Hub reports it available', () => {
    nativeDialogAvailability.mockReturnValue({ data: { available: false } })
    render(<ProjectManagerModal mode="open" onClose={vi.fn()} onComplete={vi.fn()} />, { wrapper })
    expect(screen.queryByRole('button', { name: 'Choose a folder' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open directory browser' })).toBeInTheDocument()
  })

  it('fills the path field when the operator chooses a folder', () => {
    nativeDialogAvailability.mockReturnValue({ data: { available: true } })
    nativeDialogMutate.mockImplementation((_arg, opts) =>
      opts.onSuccess({ outcome: 'chosen', path: 'C:\\chosen\\project' }),
    )
    render(<ProjectManagerModal mode="open" onClose={vi.fn()} onComplete={vi.fn()} />, { wrapper })
    fireEvent.click(screen.getByRole('button', { name: 'Choose a folder' }))
    expect(screen.getByLabelText('Directory path')).toHaveValue('C:\\chosen\\project')
  })

  it('cancel leaves the typed path untouched and shows no error', () => {
    nativeDialogAvailability.mockReturnValue({ data: { available: true } })
    nativeDialogMutate.mockImplementation((_arg, opts) => opts.onSuccess({ outcome: 'cancelled' }))
    render(<ProjectManagerModal mode="open" onClose={vi.fn()} onComplete={vi.fn()} />, { wrapper })
    fireEvent.change(screen.getByLabelText('Directory path'), { target: { value: '/kept/path' } })
    fireEvent.click(screen.getByRole('button', { name: 'Choose a folder' }))
    expect(screen.getByLabelText('Directory path')).toHaveValue('/kept/path')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('reports a timeout in its own terms, with typing still available', () => {
    nativeDialogAvailability.mockReturnValue({ data: { available: true } })
    nativeDialogMutate.mockImplementation((_arg, opts) => opts.onSuccess({ outcome: 'timeout' }))
    render(<ProjectManagerModal mode="open" onClose={vi.fn()} onComplete={vi.fn()} />, { wrapper })
    fireEvent.click(screen.getByRole('button', { name: 'Choose a folder' }))
    expect(screen.getByRole('status')).toHaveTextContent(/did not respond in time/)
    fireEvent.change(screen.getByLabelText('Directory path'), { target: { value: '/typed/anyway' } })
    expect(screen.getByLabelText('Directory path')).toHaveValue('/typed/anyway')
  })

  it('reports a failure in its own terms, distinct from a timeout', () => {
    nativeDialogAvailability.mockReturnValue({ data: { available: true } })
    nativeDialogMutate.mockImplementation((_arg, opts) =>
      opts.onSuccess({ outcome: 'failed', detail: 'Tcl error: no display' }),
    )
    render(<ProjectManagerModal mode="open" onClose={vi.fn()} onComplete={vi.fn()} />, { wrapper })
    fireEvent.click(screen.getByRole('button', { name: 'Choose a folder' }))
    expect(screen.getByRole('status')).toHaveTextContent('Tcl error: no display')
  })

  it('keeps the in-app browser reachable alongside the native dialog', () => {
    nativeDialogAvailability.mockReturnValue({ data: { available: true } })
    render(<ProjectManagerModal mode="open" onClose={vi.fn()} onComplete={vi.fn()} />, { wrapper })
    fireEvent.click(screen.getByRole('button', { name: 'Browse within the Hub instead' }))
    expect(screen.getByRole('dialog', { name: 'Browse for a directory' })).toBeInTheDocument()
  })
})
