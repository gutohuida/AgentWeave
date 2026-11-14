import * as React from 'react'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import * as api from '@/api/terminal'
import { TerminalTabContainer } from '@/components/panel/TerminalTabContainer'

/* The Terminal tab fed from the Hub (`a-terminal-in-the-side-panel`, FR-4..FR-9, FR-11). The emulator
 * is replaced by a stand-in that reports what it would send; the Hub's routes are mocked. */

vi.mock('@/components/panel/TerminalSurface', () => ({
  TerminalSurface: ({ shellId, onHandle, onExit }: { shellId: string; onHandle: (id: string, h: unknown) => void; onExit: (id: string, code: number | null) => void }) => {
    React.useEffect(() => {
      onHandle(shellId, { textToSend: () => 'line one\nline two' })
      return () => onHandle(shellId, null)
    }, [shellId, onHandle])
    return (
      <div data-testid={`surface-${shellId}`}>
        <button type="button" onClick={() => onExit(shellId, 3)}>
          exit-3
        </button>
      </div>
    )
  },
}))

vi.mock('@/api/terminal', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/terminal')>()),
  useShellMenu: vi.fn(),
  listShells: vi.fn(),
  openShell: vi.fn(),
  closeShell: vi.fn(),
  restartShell: vi.fn(),
  openPageSocket: vi.fn(() => new Promise(() => undefined)),
}))

const menu = (over: Record<string, unknown> = {}) =>
  ({
    data: {
      shells: [
        { id: 'pwsh', label: 'PowerShell 7', wsl: false, last_used: false },
        { id: 'gitbash', label: 'Git Bash', wsl: false, last_used: false },
        { id: 'wsl:Ubuntu', label: 'Ubuntu', wsl: true, last_used: false },
      ],
      last_pick: null,
      unavailable: null,
      unavailable_reason: null,
      worktree_unavailable: null,
      limit: 4,
      ...over,
    },
    isError: false,
  }) as never

let counter = 0
const record = (over: Record<string, unknown> = {}) => ({
  id: `t${++counter}`,
  conversation_id: 'c1',
  shell: 'pwsh',
  label: 'PowerShell 7',
  wsl: false,
  location: 'worktree',
  directory: 'C:\\w\\agent',
  running: true,
  exit_code: null,
  ...over,
})

function mount(onSend = vi.fn(), conversationId = 'c1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <QueryClientProvider client={client}>
      <TerminalTabContainer agent="Dev" projectId="p1" conversationId={conversationId} onSendToComposer={onSend} />
    </QueryClientProvider>,
  )
  return { onSend, view }
}

beforeEach(() => {
  counter = 0
  vi.mocked(api.useShellMenu).mockReturnValue(menu())
  vi.mocked(api.listShells).mockResolvedValue([])
  vi.mocked(api.openShell).mockImplementation(async () => record() as never)
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('TerminalTabContainer', () => {
  it('starts one fresh shell, in the worktree, when the conversation has none', async () => {
    mount(vi.fn(), 'fresh-1')
    await waitFor(() => expect(api.openShell).toHaveBeenCalledTimes(1))
    expect(api.openShell).toHaveBeenCalledWith('p1', 'fresh-1', expect.objectContaining({ shell: 'pwsh', location: 'worktree', page: api.PAGE_ID }))
    expect(await screen.findByTestId('surface-t1')).toBeTruthy()
  })

  it('opens in the project root and the last pick first when the agent has no worktree', async () => {
    vi.mocked(api.useShellMenu).mockReturnValue(
      menu({ worktree_unavailable: 'This agent has no worktree.', last_pick: { option_id: 'gitbash', location: 'worktree' } }),
    )
    mount(vi.fn(), 'fresh-2')
    await waitFor(() => expect(api.openShell).toHaveBeenCalledTimes(1))
    expect(api.openShell).toHaveBeenCalledWith('p1', 'fresh-2', expect.objectContaining({ shell: 'gitbash', location: 'root' }))
  })

  it('reattaches to the shells the Hub still holds instead of starting another', async () => {
    vi.mocked(api.listShells).mockResolvedValue([record({ id: 'kept' }), record({ id: 'kept2' })] as never)
    mount(vi.fn(), 'back-1')
    expect(await screen.findByTestId('surface-kept')).toBeTruthy()
    expect(api.openShell).not.toHaveBeenCalled()
  })

  it('shows the Hub refusal naming the limit and adds no tab', async () => {
    vi.mocked(api.listShells).mockResolvedValue([record({ id: 'a' }), record({ id: 'b' }), record({ id: 'c' })] as never)
    vi.mocked(api.openShell).mockRejectedValue(new ApiError(409, JSON.stringify({ detail: 'A conversation can have 4 shells open. Close one to open another.' })))
    mount(vi.fn(), 'cap-1')
    await screen.findByTestId('surface-a')
    await userEvent.click(screen.getByRole('button', { name: 'New shell' }))
    await userEvent.click(await screen.findByText('Git Bash'))
    expect((await screen.findByTestId('terminal-refusal')).textContent).toContain('4 shells')
    expect(screen.getAllByRole('tab')).toHaveLength(3)
  })

  it('closes a shell through the Hub and drops its tab', async () => {
    vi.mocked(api.listShells).mockResolvedValue([record({ id: 'a' }), record({ id: 'b' })] as never)
    vi.mocked(api.closeShell).mockResolvedValue({ id: 'a', closed: true })
    mount(vi.fn(), 'close-1')
    await screen.findByTestId('surface-a')
    await userEvent.click(screen.getAllByRole('button', { name: /^Close/ })[0])
    await waitFor(() => expect(screen.getAllByRole('tab')).toHaveLength(1))
    expect(api.closeShell).toHaveBeenCalledWith('p1', 'close-1', 'a')
    expect(await screen.findByTestId('surface-b')).toBeTruthy()
  })

  it('shows the ended state with the exit code and Open it again restarts the shell', async () => {
    vi.mocked(api.listShells).mockResolvedValue([record({ id: 'a' })] as never)
    vi.mocked(api.restartShell).mockResolvedValue({ ...record({ id: 'a2' }), replaces: 'a' } as never)
    mount(vi.fn(), 'end-1')
    await userEvent.click(await screen.findByText('exit-3'))
    expect((await screen.findByRole('status')).textContent).toContain('exit code 3')
    await userEvent.click(screen.getByRole('button', { name: 'Open it again' }))
    expect(await screen.findByTestId('surface-a2')).toBeTruthy()
    expect(api.restartShell).toHaveBeenCalledWith('p1', 'end-1', 'a')
  })

  it('sends the selection, marked with the shell name and directory, to the composer', async () => {
    vi.mocked(api.listShells).mockResolvedValue([record({ id: 'a' })] as never)
    const { onSend } = mount(vi.fn(), 'send-1')
    await screen.findByTestId('surface-a')
    await userEvent.click(screen.getByRole('button', { name: /Send to Dev/ }))
    expect(onSend).toHaveBeenCalledTimes(1)
    const text = onSend.mock.calls[0][0] as string
    expect(text).toContain('PowerShell 7')
    expect(text).toContain('C:\\w\\agent')
    expect(text).toContain('line one\nline two')
  })

  it.each([
    ['remote', 'opens only on the computer AgentWeave runs on'],
    ['docker', 'not available in Docker mode'],
  ])('says why when the terminal is %s-unavailable and starts nothing', async (reason, words) => {
    vi.mocked(api.useShellMenu).mockReturnValue(menu({ shells: [], unavailable: reason }))
    mount(vi.fn(), `un-${reason}`)
    expect((await screen.findByTestId('terminal-tab')).textContent).toContain(words)
    expect(api.openShell).not.toHaveBeenCalled()
  })
})
