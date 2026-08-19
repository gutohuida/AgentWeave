import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { FilesIndexTab } from '@/components/spec/FilesIndexTab'

afterEach(() => cleanup())

const PATHS = ['README.md', 'src/lib/composerTrigger.ts', 'src/components/agents/Composer.tsx']

describe('FilesIndexTab — the files tab (task 5.1, 2026-08-18-one-shell-three-panels)', () => {
  it('browses the workspace as a tree when nothing is typed', () => {
    render(<FilesIndexTab paths={PATHS} isLoading={false} currentPath={null} onSelect={vi.fn()} />)

    expect(screen.getByTestId('file-tree-file-README.md')).toBeInTheDocument()
    expect(screen.getByTestId('file-tree-directory-src')).toBeInTheDocument()
  })

  it('selecting a file in the tree calls onSelect with its path', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(<FilesIndexTab paths={PATHS} isLoading={false} currentPath={null} onSelect={onSelect} />)

    await user.click(screen.getByTestId('file-tree-file-README.md'))

    expect(onSelect).toHaveBeenCalledWith('README.md')
  })

  it('typing switches to a ranked flat list of matches', async () => {
    const user = userEvent.setup()
    render(<FilesIndexTab paths={PATHS} isLoading={false} currentPath={null} onSelect={vi.fn()} />)

    await user.type(screen.getByLabelText('Search files'), 'composer')

    expect(screen.getByTestId('files-search-result-src/lib/composerTrigger.ts')).toBeInTheDocument()
    expect(screen.getByTestId('files-search-result-src/components/agents/Composer.tsx')).toBeInTheDocument()
    expect(screen.queryByTestId('files-search-result-README.md')).not.toBeInTheDocument()
  })

  it('reports no matches rather than an empty box', async () => {
    const user = userEvent.setup()
    render(<FilesIndexTab paths={PATHS} isLoading={false} currentPath={null} onSelect={vi.fn()} />)

    await user.type(screen.getByLabelText('Search files'), 'nothing-matches-this')

    expect(screen.getByText('No matching files.')).toBeInTheDocument()
  })

  it('marks the currently open file in the tree', () => {
    render(
      <FilesIndexTab paths={PATHS} isLoading={false} currentPath="README.md" onSelect={vi.fn()} />,
    )

    expect(screen.getByTestId('file-tree-file-README.md')).toHaveAttribute('aria-current', 'true')
  })
})
