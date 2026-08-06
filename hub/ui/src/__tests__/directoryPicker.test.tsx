import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { DirectoryPicker } from '@/components/projects/DirectoryPicker'
import type { DirectoryListing } from '@/api/fsBrowse'

const LISTINGS: Record<string, DirectoryListing> = {
  '/': {
    path: '/',
    parent: null,
    entries: [{ name: 'home', path: '/home' }],
  },
  '/home': {
    path: '/home',
    parent: '/',
    entries: [{ name: 'projects', path: '/home/projects' }],
  },
  '/home/projects': {
    path: '/home/projects',
    parent: '/home',
    entries: [
      { name: 'agentweave', path: '/home/projects/agentweave' },
      { name: 'other', path: '/home/projects/other' },
    ],
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
    useFilesystemRoots: () => ({
      data: { roots: [{ name: '/', path: '/' }] },
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

  it('a single click never chooses — double-click has no shortcut behaviour (task 9.3)', () => {
    const onChoose = vi.fn()
    render(<DirectoryPicker startPath="/home" onChoose={onChoose} onClose={vi.fn()} />, { wrapper })
    fireEvent.doubleClick(screen.getByText('projects'))
    expect(onChoose).not.toHaveBeenCalled()
  })

  it('shows the unreadable-directory reason and does not end browsing', () => {
    render(<DirectoryPicker startPath="/unreadable" onChoose={vi.fn()} onClose={vi.fn()} />, { wrapper })
    expect(screen.getByRole('status')).toHaveTextContent('Permission denied')
    // Still able to go up — browsing continues rather than ending on an error.
    expect(screen.getByRole('button', { name: 'Up to parent directory' })).toBeEnabled()
  })

  describe('filesystem roots (task 9.1)', () => {
    it('presents the available roots and navigates to one on click', async () => {
      render(
        <DirectoryPicker startPath="/home/projects" onChoose={vi.fn()} onClose={vi.fn()} />,
        { wrapper },
      )
      fireEvent.click(screen.getByRole('button', { name: '/' }))
      await waitFor(() => {
        const listbox = screen.getByRole('listbox', { name: 'Directory entries' })
        expect(within(listbox).getByText('home')).toBeInTheDocument()
      })
    })
  })

  describe('breadcrumb ancestor navigation (task 9.2)', () => {
    it('renders every path segment as its own clickable ancestor', () => {
      render(
        <DirectoryPicker startPath="/home/projects" onChoose={vi.fn()} onClose={vi.fn()} />,
        { wrapper },
      )
      // The root segment keeps its anchor prefix ("/home", not bare "home") — the same
      // convention elidePathSegments already uses for ProjectHeader's own path display.
      expect(screen.getByRole('button', { name: '/home' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'projects' })).toBeInTheDocument()
    })

    it('jumps directly to a distant ancestor, not just one level up', async () => {
      render(
        <DirectoryPicker startPath="/home/projects" onChoose={vi.fn()} onClose={vi.fn()} />,
        { wrapper },
      )
      fireEvent.click(screen.getByRole('button', { name: '/home' }))
      await waitFor(() => {
        const listbox = screen.getByRole('listbox', { name: 'Directory entries' })
        expect(within(listbox).getByText('projects')).toBeInTheDocument()
      })
    })
  })

  describe('keyboard operation (task 9.4)', () => {
    it('moves the highlight between entries with arrow keys', () => {
      render(
        <DirectoryPicker startPath="/home/projects" onChoose={vi.fn()} onClose={vi.fn()} />,
        { wrapper },
      )
      const dialog = screen.getByRole('dialog', { name: 'Browse for a directory' })
      expect(screen.getByRole('option', { name: 'agentweave' })).toHaveAttribute('data-highlighted', 'true')
      fireEvent.keyDown(dialog, { key: 'ArrowDown' })
      expect(screen.getByRole('option', { name: 'other' })).toHaveAttribute('data-highlighted', 'true')
      fireEvent.keyDown(dialog, { key: 'ArrowUp' })
      expect(screen.getByRole('option', { name: 'agentweave' })).toHaveAttribute('data-highlighted', 'true')
    })

    it('Enter navigates into the highlighted entry', async () => {
      render(<DirectoryPicker startPath="/home" onChoose={vi.fn()} onClose={vi.fn()} />, { wrapper })
      const dialog = screen.getByRole('dialog', { name: 'Browse for a directory' })
      fireEvent.keyDown(dialog, { key: 'Enter' })
      await waitFor(() => expect(screen.getByText('agentweave')).toBeInTheDocument())
    })

    it('Backspace goes to the parent directory', async () => {
      render(
        <DirectoryPicker startPath="/home/projects" onChoose={vi.fn()} onClose={vi.fn()} />,
        { wrapper },
      )
      const dialog = screen.getByRole('dialog', { name: 'Browse for a directory' })
      fireEvent.keyDown(dialog, { key: 'Backspace' })
      await waitFor(() => {
        const listbox = screen.getByRole('listbox', { name: 'Directory entries' })
        expect(within(listbox).getByText('projects')).toBeInTheDocument()
      })
    })

    it('Escape closes without choosing', () => {
      const onClose = vi.fn()
      const onChoose = vi.fn()
      render(<DirectoryPicker startPath="/home" onChoose={onChoose} onClose={onClose} />, { wrapper })
      const dialog = screen.getByRole('dialog', { name: 'Browse for a directory' })
      fireEvent.keyDown(dialog, { key: 'Escape' })
      expect(onClose).toHaveBeenCalledOnce()
      expect(onChoose).not.toHaveBeenCalled()
    })
  })
})
