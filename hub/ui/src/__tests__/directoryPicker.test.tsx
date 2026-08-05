import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { DirectoryPicker } from '@/components/projects/DirectoryPicker'
import type { DirectoryListing } from '@/api/fsBrowse'

const LISTINGS: Record<string, DirectoryListing> = {
  '/home': {
    path: '/home',
    parent: '/',
    entries: [{ name: 'projects', path: '/home/projects' }],
  },
  '/home/projects': {
    path: '/home/projects',
    parent: '/home',
    entries: [{ name: 'agentweave', path: '/home/projects/agentweave' }],
  },
  '/unreadable': {
    path: '/unreadable',
    parent: '/',
    entries: [],
    reason: 'Permission denied',
  },
}

vi.mock('@/api/fsBrowse', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/fsBrowse')>()
  return {
    ...actual,
    useDirectoryListing: (path: string | null) => ({
      data: path ? LISTINGS[path] : undefined,
      isLoading: false,
    }),
  }
})

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('DirectoryPicker', () => {
  it('lists the subdirectories of the start path', () => {
    render(<DirectoryPicker startPath="/home" onChoose={vi.fn()} onClose={vi.fn()} />, { wrapper })
    expect(screen.getByText('projects')).toBeInTheDocument()
  })

  it('navigates into a subdirectory on click', async () => {
    render(<DirectoryPicker startPath="/home" onChoose={vi.fn()} onClose={vi.fn()} />, { wrapper })
    fireEvent.click(screen.getByText('projects'))
    await waitFor(() => expect(screen.getByText('agentweave')).toBeInTheDocument())
  })

  it('navigates to the parent directory when "up" is clicked', async () => {
    render(
      <DirectoryPicker startPath="/home/projects" onChoose={vi.fn()} onClose={vi.fn()} />,
      { wrapper },
    )
    expect(screen.getByText('agentweave')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Up to parent directory' }))
    await waitFor(() => expect(screen.getByText('projects')).toBeInTheDocument())
  })

  it('calls onChoose with the current directory when "Choose this directory" is clicked', () => {
    const onChoose = vi.fn()
    render(<DirectoryPicker startPath="/home" onChoose={onChoose} onClose={vi.fn()} />, { wrapper })
    fireEvent.click(screen.getByRole('button', { name: 'Choose this directory' }))
    expect(onChoose).toHaveBeenCalledWith('/home')
  })

  it('calls onChoose on double-click of an entry, without requiring navigation first', () => {
    const onChoose = vi.fn()
    render(<DirectoryPicker startPath="/home" onChoose={onChoose} onClose={vi.fn()} />, { wrapper })
    fireEvent.doubleClick(screen.getByText('projects'))
    expect(onChoose).toHaveBeenCalledWith('/home/projects')
  })

  it('shows the unreadable-directory reason and does not end browsing', () => {
    render(<DirectoryPicker startPath="/unreadable" onChoose={vi.fn()} onClose={vi.fn()} />, { wrapper })
    expect(screen.getByRole('status')).toHaveTextContent('Permission denied')
    // Still able to go up — browsing continues rather than ending on an error.
    expect(screen.getByRole('button', { name: 'Up to parent directory' })).toBeEnabled()
  })
})
