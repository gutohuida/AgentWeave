import * as React from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  PAGE_ID,
  closeShell,
  listShells,
  openPageSocket,
  openShell,
  refusalText,
  restartShell,
  useShellMenu,
  type ShellLocation,
  type ShellRecord,
} from '@/api/terminal'
import { TerminalSurface, type TerminalHandle } from './TerminalSurface'
import { TerminalTab, type OpenShell, type ShellOption } from './TerminalTab'

/** Held for as long as this page is loaded: the Hub ends the page's shells when it goes away (FR-9). */
let pageSocket: { projectId: string; socket: Promise<WebSocket> } | null = null
function holdPage(projectId: string) {
  if (pageSocket?.projectId === projectId) return
  const held = { projectId, socket: openPageSocket(projectId) }
  pageSocket = held
  held.socket.catch(() => {
    if (pageSocket === held) pageSocket = null
  })
}

/** Conversations that already got their one fresh shell in this page load. */
const started = new Set<string>()

/** Where a block sent to the composer says it came from (FR-11). */
function terminalBlock(shell: Pick<OpenShell, 'option' | 'directory'>, text: string): string {
  return `Terminal output (${shell.option.label}, ${shell.directory}):\n\`\`\`\n${text}\n\`\`\`\n`
}

export interface TerminalTabContainerProps {
  agent: string
  projectId: string
  conversationId: string | null
  /** Puts text into the conversation composer, unsent. */
  onSendToComposer: (text: string) => void
}

function toOpenShell(record: ShellRecord, exitCodes: Record<string, number | null>): OpenShell {
  return {
    id: record.id,
    option: { id: record.shell, label: record.label, wsl: record.wsl },
    location: record.location,
    directory: record.directory,
    exitCode: record.id in exitCodes ? exitCodes[record.id] : record.running ? null : record.exit_code,
  }
}

/** The Terminal tab fed from the Hub: shells open, close and restart through its routes, and the
 *  active one is drawn by an emulator attached to it. */
export function TerminalTabContainer({ agent, projectId, conversationId, onSendToComposer }: TerminalTabContainerProps) {
  const queryClient = useQueryClient()
  const menu = useShellMenu(conversationId)
  const [records, setRecords] = React.useState<ShellRecord[] | null>(null)
  const [activeId, setActiveId] = React.useState<string | null>(null)
  const [exitCodes, setExitCodes] = React.useState<Record<string, number | null>>({})
  const [refusal, setRefusal] = React.useState<string | null>(null)
  const handles = React.useRef(new Map<string, TerminalHandle>())

  const menuData = menu.data
  const unavailable = menuData?.unavailable ? (menuData.unavailable === 'docker' ? 'docker' : 'remote') : null

  React.useEffect(() => {
    if (unavailable || !menuData) return
    holdPage(projectId)
  }, [projectId, unavailable, menuData])

  React.useEffect(() => {
    setRecords(null)
    setActiveId(null)
    setExitCodes({})
    setRefusal(null)
    if (!conversationId) return undefined
    let cancelled = false
    listShells(projectId, conversationId)
      .then((list) => {
        if (cancelled) return
        setRecords(list)
        setActiveId(list[0]?.id ?? null)
      })
      .catch((error) => {
        if (!cancelled) setRefusal(refusalText(error))
      })
    return () => {
      cancelled = true
    }
  }, [projectId, conversationId])

  const open = React.useCallback(
    async (optionId: string, location: ShellLocation) => {
      if (!conversationId) return
      setRefusal(null)
      try {
        const record = await openShell(projectId, conversationId, { shell: optionId, location, page: PAGE_ID })
        setRecords((list) => [...(list ?? []), record])
        setActiveId(record.id)
        await queryClient.invalidateQueries({ queryKey: ['project', projectId, 'terminal', 'menu'] })
      } catch (error) {
        setRefusal(refusalText(error))
      }
    },
    [projectId, conversationId, queryClient],
  )

  // One fresh shell when the tab opens on a conversation that has none (FR-9), once per page load.
  React.useEffect(() => {
    if (!conversationId || !menuData || unavailable || records === null || records.length > 0) return
    if (started.has(conversationId)) return
    const pick = menuData.last_pick
    const first = menuData.shells.find((s) => s.id === pick?.option_id) ?? menuData.shells[0]
    if (!first) return
    started.add(conversationId)
    const location: ShellLocation = menuData.worktree_unavailable ? 'root' : (pick?.location ?? 'worktree')
    void open(first.id, location)
  }, [conversationId, menuData, unavailable, records, open])

  const close = async (id: string) => {
    if (!conversationId) return
    try {
      await closeShell(projectId, conversationId, id)
      const rest = (records ?? []).filter((r) => r.id !== id)
      setRecords(rest)
      if (activeId === id) setActiveId(rest[0]?.id ?? null)
    } catch (error) {
      setRefusal(refusalText(error))
    }
  }

  const restart = async (id: string) => {
    if (!conversationId) return
    try {
      const fresh = await restartShell(projectId, conversationId, id)
      setRecords((list) => (list ?? []).map((r) => (r.id === id ? fresh : r)))
      setActiveId(fresh.id)
    } catch (error) {
      setRefusal(refusalText(error))
    }
  }

  const options: ShellOption[] = (menuData?.shells ?? []).map((s) => ({ id: s.id, label: s.label, detail: s.detail ?? undefined, wsl: s.wsl }))
  const shells = (records ?? []).map((r) => toOpenShell(r, exitCodes))
  const active = shells.find((s) => s.id === activeId) ?? null

  const send = (id: string) => {
    const shell = shells.find((s) => s.id === id)
    const text = handles.current.get(id)?.textToSend()
    if (shell && text !== undefined) onSendToComposer(terminalBlock(shell, text))
  }

  if (!conversationId) return <p className="aw-ptab-note">Start a conversation to open a terminal in its worktree.</p>
  if (!menuData) return <p className="aw-ptab-note">{menu.isError ? 'The terminal could not be reached.' : 'Loading terminal'}</p>

  return (
    <>
      {refusal && (
        <p role="alert" className="aw-ptab-note" data-testid="terminal-refusal">
          {refusal}
        </p>
      )}
      <TerminalTab
        agent={agent}
        unavailable={unavailable}
        shells={shells}
        activeId={activeId}
        onSelect={setActiveId}
        onClose={(id) => void close(id)}
        onRestart={(id) => void restart(id)}
        options={options}
        lastPick={menuData.last_pick ? { optionId: menuData.last_pick.option_id, location: menuData.last_pick.location } : null}
        onOpen={(optionId, location) => void open(optionId, location)}
        worktreeUnavailable={menuData.worktree_unavailable}
        onSendToAgent={send}
        limit={menuData.limit}
      >
        {active && (
          <TerminalSurface
            key={active.id}
            projectId={projectId}
            conversationId={conversationId}
            shellId={active.id}
            onHandle={(id, handle) => (handle ? handles.current.set(id, handle) : handles.current.delete(id))}
            onExit={(id, code) => setExitCodes((codes) => ({ ...codes, [id]: code }))}
          />
        )}
      </TerminalTab>
    </>
  )
}
