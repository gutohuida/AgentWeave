import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
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

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('ProjectManagerModal — directory browsing supplements typing', () => {
  it('typing a path remains available without opening the picker', () => {
    render(<ProjectManagerModal mode="open" onClose={vi.fn()} onComplete={vi.fn()} />, { wrapper })
    fireEvent.change(screen.getByLabelText('Directory path'), { target: { value: '/typed/path' } })
    expect(screen.getByLabelText('Directory path')).toHaveValue('/typed/path')
    expect(screen.queryByRole('dialog', { name: 'Browse for a directory' })).not.toBeInTheDocument()
  })

  it('opens the picker and fills the path field when a directory is chosen', () => {
    render(<ProjectManagerModal mode="open" onClose={vi.fn()} onComplete={vi.fn()} />, { wrapper })
    fireEvent.click(screen.getByRole('button', { name: 'Open directory browser' }))
    expect(screen.getByRole('dialog', { name: 'Browse for a directory' })).toBeInTheDocument()
    fireEvent.doubleClick(screen.getByText('agentweave'))
    expect(screen.getByLabelText('Directory path')).toHaveValue('/home/projects/agentweave')
    expect(screen.queryByRole('dialog', { name: 'Browse for a directory' })).not.toBeInTheDocument()
  })
})
