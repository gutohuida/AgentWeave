import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FilesTabContainer } from '@/components/panel/FilesTabContainer'
import { useConversationFiles } from '@/api/workspace'
import { fileLocation, fileOwner, fileTabId, filePath } from '@/store/panelTabsStore'

vi.mock('@/api/workspace', () => ({ useConversationFiles: vi.fn() }))
const mocked = vi.mocked(useConversationFiles)

const listing = (over: Record<string, unknown>) =>
  ({
    data: { location: 'worktree', state: 'ok', has_checkout: true, branch: 'agentweave/agent/x', paths: ['a.py'], changed: {}, ...over },
    isError: false,
  }) as never

const props = { agent: 'Dev', projectId: 'p1', currentPath: null, currentLocation: null, onOpen: vi.fn() }

beforeEach(() => window.localStorage.clear())
afterEach(() => cleanup())

describe('FilesTabContainer', () => {
  it('opens on the checkout by default (no location requested) and remembers a switch per conversation', async () => {
    mocked.mockReturnValue(listing({}))
    render(<FilesTabContainer {...props} conversationId="c1" />)
    expect(mocked).toHaveBeenLastCalledWith('c1', undefined)
    await userEvent.click(screen.getByRole('radio', { name: 'Project root' }))
    expect(mocked).toHaveBeenLastCalledWith('c1', 'root')
    cleanup()
    // After a "reload" the same conversation asks for root; another still asks for the default.
    render(<FilesTabContainer {...props} conversationId="c1" />)
    expect(mocked).toHaveBeenLastCalledWith('c1', 'root')
    cleanup()
    render(<FilesTabContainer {...props} conversationId="c2" />)
    expect(mocked).toHaveBeenLastCalledWith('c2', undefined)
  })

  it('offers no switch and says why when the agent has no checkout', () => {
    mocked.mockReturnValue(listing({ location: 'root', has_checkout: false, state: 'no_checkout', message: 'Dev works in the project directory.' }))
    render(<FilesTabContainer {...props} conversationId="c1" />)
    expect(screen.queryByRole('radio')).toBeNull()
    expect(screen.getByTestId('files-note')).toHaveTextContent('works in the project directory')
  })

  it('marks changed files and opens a file with its location', async () => {
    const onOpen = vi.fn()
    mocked.mockReturnValue(listing({ paths: ['a.py'], changed: { 'a.py': 'A', 'old.py': 'D' } }))
    render(<FilesTabContainer {...props} onOpen={onOpen} conversationId="c1" />)
    expect(screen.getByLabelText('Deleted')).toBeInTheDocument()
    await userEvent.click(screen.getByText('a.py'))
    expect(onOpen).toHaveBeenCalledWith('a.py', 'worktree')
  })
})

describe('file tab ids carry the location', () => {
  it('keeps the same path in two locations distinct and round-trips both', () => {
    expect(fileTabId('README.md')).not.toBe(fileTabId('README.md', 'worktree'))
    expect(filePath(fileTabId('README.md', 'worktree'))).toBe('README.md')
    expect(fileLocation(fileTabId('README.md', 'worktree'))).toBe('worktree')
    expect(fileLocation(fileTabId('README.md'))).toBe('root')
    expect(filePath(fileTabId('worktree:x'))).toBe('worktree:x')
    expect(fileLocation(fileTabId('worktree:x'))).toBe('root')

    // A worktree tab names whose checkout it is, so switching conversations cannot re-point it.
    const maker = { agent: 'Maker', conversationId: 'conv-aaa' }
    const tasker = { agent: 'Tasker', conversationId: 'conv-bbb' }
    const idM = fileTabId('README.md', 'worktree', maker)
    expect(idM).not.toBe(fileTabId('README.md', 'worktree', tasker))
    expect(fileOwner(idM)).toEqual(maker)
    expect(filePath(idM)).toBe('README.md')
    expect(fileLocation(idM)).toBe('worktree')
    expect(fileOwner(fileTabId('README.md'))).toBeNull()
    expect(fileOwner(fileTabId('a:b.md', 'worktree', maker))).toEqual(maker)
    expect(filePath(fileTabId('a:b.md', 'worktree', maker))).toBe('a:b.md')
  })
})
