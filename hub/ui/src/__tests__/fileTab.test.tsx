import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { FileTab } from '@/components/spec/FileTab'
import { ApiError } from '@/api/client'
import { useWorkspaceFile } from '@/api/workspace'

vi.mock('@/api/workspace', () => ({
  useWorkspaceFile: vi.fn(),
}))

const mockedUseWorkspaceFile = vi.mocked(useWorkspaceFile)

afterEach(() => cleanup())

describe('FileTab — the files tab detail kind (tasks 5.3-5.4, 2026-08-18-one-shell-three-panels)', () => {
  it('shows a loading state before the read resolves', () => {
    mockedUseWorkspaceFile.mockReturnValue({ data: undefined, isLoading: true, error: null } as never)
    render(<FileTab path="src/a.ts" onClose={vi.fn()} />)

    // A shape-matched skeleton, not the word "Loading…" — the index tabs already worked this way
    // and the two detail tabs were the last places still saying it in prose.
    expect(screen.getByLabelText('Loading file')).toBeInTheDocument()
    // Still closable while the read is in flight: the header only renders inside `FilePreview`,
    // which this branch does not reach, so the tab draws its own strip here.
    expect(screen.getByTestId('file-tab-close')).toBeInTheDocument()
  })

  it('renders text content', () => {
    mockedUseWorkspaceFile.mockReturnValue({
      data: { path: 'src/a.ts', binary: false, size: 11, content: 'hello world' },
      isLoading: false,
      error: null,
    } as never)
    render(<FileTab path="src/a.ts" onClose={vi.fn()} />)

    expect(screen.getByTestId('file-tab-content')).toHaveTextContent('hello world')
  })

  it('states binary explicitly rather than attempting to render it', () => {
    mockedUseWorkspaceFile.mockReturnValue({
      data: { path: 'assets/logo.png', binary: true, size: 4096, content: null },
      isLoading: false,
      error: null,
    } as never)
    render(<FileTab path="assets/logo.png" onClose={vi.fn()} />)

    const notice = screen.getByTestId('file-tab-binary')
    expect(notice).toHaveTextContent('binary')
    expect(notice).toHaveTextContent('4,096 bytes')
  })

  it('states an oversized refusal naming both the size and the bound', () => {
    mockedUseWorkspaceFile.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new ApiError(413, JSON.stringify({ detail: 'file is 9000000 bytes, exceeding the 5000000 byte limit' })),
    } as never)
    render(<FileTab path="big.bin" onClose={vi.fn()} />)

    const notice = screen.getByTestId('file-tab-error')
    expect(notice).toHaveTextContent('9000000')
    expect(notice).toHaveTextContent('5000000')
  })

  it('"Insert into composer" produces the same mention text the composer trigger would (task 5.4)', async () => {
    const user = userEvent.setup()
    mockedUseWorkspaceFile.mockReturnValue({
      data: { path: 'docs/release notes.md', binary: false, size: 5, content: 'hi' },
      isLoading: false,
      error: null,
    } as never)
    const onInsert = vi.fn()
    render(<FileTab path="docs/release notes.md" onInsertIntoComposer={onInsert} onClose={vi.fn()} />)

    await user.click(screen.getByTestId('file-tab-insert'))

    expect(onInsert).toHaveBeenCalledWith('docs/release notes.md')
  })

  it('omits the insert button when no handler is given', () => {
    mockedUseWorkspaceFile.mockReturnValue({
      data: { path: 'src/a.ts', binary: false, size: 1, content: 'x' },
      isLoading: false,
      error: null,
    } as never)
    render(<FileTab path="src/a.ts" onClose={vi.fn()} />)

    expect(screen.queryByTestId('file-tab-insert')).not.toBeInTheDocument()
  })

  it('closes via the close control', async () => {
    const user = userEvent.setup()
    mockedUseWorkspaceFile.mockReturnValue({
      data: { path: 'src/a.ts', binary: false, size: 1, content: 'x' },
      isLoading: false,
      error: null,
    } as never)
    const onClose = vi.fn()
    render(<FileTab path="src/a.ts" onClose={onClose} />)

    await user.click(screen.getByTestId('file-tab-close'))

    expect(onClose).toHaveBeenCalled()
  })
})
