import * as React from 'react'
import type { ChatHistoryResponse } from '@/api/agentChat'
import { conversationLabel } from '@/api/agentChat'
import { AgentTimeline } from '@/components/agents/AgentTimeline'
import { Icon } from '@/components/common/Icon'
import type { DiffFile } from '@/components/common/DiffView'
import { diffStat } from '@/lib/diffLines'
import { ChangesTab } from '@/components/panel/ChangesTab'
import { FilesTab } from '@/components/panel/FilesTab'
import type { PanelLocation } from '@/components/panel/LocationSwitch'
import { RunningTab } from '@/components/panel/RunningTab'
import { runningItems } from '@/components/panel/runningModel'
import { TerminalTab, type OpenShell, type ShellOption } from '@/components/panel/TerminalTab'
import { WatchTab } from '@/components/panel/WatchTab'
import { FilePreview } from '@/components/spec/FilePreview'
import { PanelShell, type PanelTabDescriptor } from '@/components/spec/PanelShell'
import { fileIconFor } from '@/components/spec/fileIcons'
import { SPEC_DOC_MIN_WIDTH } from '@/components/spec/specPreferences'
import { Button } from '@/components/ui/button'
import { setComposerDraft } from '@/lib/composerDrafts'
import { formatAgo } from '@/lib/format'
import { toast } from '@/lib/toast'
import { filePath, fileTabId, isFileTabId, usePanelTabsStore, type TabId } from '@/store/panelTabsStore'
import { agentAttention, agents, conversations, PROJECT_ID } from '../fixtures'
import builderChat from '../fixtures/chat_builder_e3aba2.json'
import architectChat from '../fixtures/chat_architect_9cdda4.json'
import {
  BASE_BRANCH,
  BRANCH_CHANGES,
  CHANGE_MARKS,
  contentFor,
  ROOT_DIR,
  ROOT_FILES,
  TERMINAL_LINES,
  TURN_CHANGES,
  WORKTREE_DIR,
  WORKTREE_FILES,
} from '../panelMock'
import type { MockRoute, ScreenProps } from '../routes'
import { RUNNING_BUILDS, RUNNING_JOBS, RUNNING_LOOPS } from '../runningMock'

export type SidePanelTab = 'running' | 'changes' | 'files' | 'terminal' | 'terminal-full' | 'terminal-remote' | 'terminal-docker' | 'watch'

const CHATS: Record<string, ChatHistoryResponse> = {
  'conv-e3aba2c5956a': builderChat as unknown as ChatHistoryResponse,
  'conv-9cdda4865e0b': architectChat as unknown as ChatHistoryResponse,
}

// mock state: the panel store's ids are the app's three index kinds today. The roadmap's new tabs are
// given ids of their own here (`loops` is shown as Running, which replaces it); the store's union
// gains them when the slices are built.
const ID: Record<'specs' | 'files' | 'running' | 'changes' | 'terminal' | 'watch', TabId> = {
  specs: 'specs',
  files: 'files',
  running: 'loops',
  changes: 'changes' as TabId,
  terminal: 'terminal' as TabId,
  watch: 'watch' as TabId,
}
const ORDER = ['specs', 'files', 'changes', 'running', 'terminal', 'watch'] as const

/** The conversation's side panel with the roadmap's tabs (roadmap
 *  `a-side-panel-worth-keeping-open-activity-changes-files-terminal-and-peers`), in the app's own shell. */
export function SidePanelMock({ tab, agent, go, now, route }: { tab: SidePanelTab; agent: string; go: ScreenProps['go']; now: Date; route: MockRoute }) {
  React.useEffect(() => {
    const store = usePanelTabsStore.getState()
    for (const key of ORDER) store.openTab(PROJECT_ID, ID[key])
    store.activateTab(PROJECT_ID, ID[tab.startsWith('terminal') ? 'terminal' : (tab as 'running' | 'changes' | 'files' | 'watch')])
  }, [tab])

  const items = React.useMemo(() => runningItems({ builds: RUNNING_BUILDS, loops: RUNNING_LOOPS, jobs: RUNNING_JOBS, now }), [now])
  const live = items.filter((i) => i.phase === 'needs-you' || i.phase === 'working').length
  const [location, setLocation] = React.useState<PanelLocation>('worktree')
  const term = useMockShells(agent, tab === 'terminal-full')
  const peers = agents.filter((a) => a.name !== agent)
  const [peer, setPeer] = React.useState(() => (peers.find((p) => p.name === 'Builder') ?? peers[0])?.name ?? '')
  const peerConversations = conversations.filter((c) => c.agent === peer)
  const [peerConversation, setPeerConversation] = React.useState<string | null>(null)
  const watchedId = peerConversation && peerConversations.some((c) => c.id === peerConversation) ? peerConversation : (peerConversations.find((c) => CHATS[c.id])?.id ?? peerConversations[0]?.id ?? null)
  const watchedChat = watchedId ? CHATS[watchedId] : undefined
  const openTab = usePanelTabsStore((s) => s.openTab)
  const closeTab = usePanelTabsStore((s) => s.closeTab)

  const describe = (id: TabId): PanelTabDescriptor => {
    if (id === ID.running) return { id, label: 'Running', icon: 'monitoring', count: live }
    if (id === ID.changes) return { id, label: 'Changes', icon: 'file_pen_line', count: TURN_CHANGES.length }
    if (id === ID.terminal) return { id, label: 'Terminal', icon: 'terminal' }
    if (id === ID.watch) return { id, label: 'Watch', icon: 'visibility' }
    if (id === ID.files) return { id, label: 'Files', icon: 'folder_open' }
    if (isFileTabId(id)) {
      const path = filePath(id)
      return { id, label: path.slice(path.lastIndexOf('/') + 1), icon: fileIconFor(path) }
    }
    return { id, label: 'Specs', icon: 'menu_book' }
  }
  const openFile = (path: string) => openTab(PROJECT_ID, fileTabId(path))

  const render = (id: TabId): React.ReactNode => {
    if (id === ID.running) {
      return (
        <RunningTab
          items={items}
          colorIndexOf={(name) => agents.find((a) => a.name === name)?.color_index}
          onOpen={(item) => (item.kind === 'job' ? go({ kind: 'tab', tab: 'jobs' }) : toast({ title: item.kind === 'build' ? 'Opens the spec at its builds' : 'Opens the loop', description: item.title }))}
          onAttend={(item) => toast({ title: item.attention?.kind === 'question' ? 'Opens the question to answer' : 'Shows what is stuck', description: item.title })}
        />
      )
    }
    if (id === ID.changes) {
      return <MockChanges agent={agent} onOpenFile={openFile} />
    }
    if (id === ID.files) {
      return (
        <FilesTab
          agent={agent}
          location={location}
          onLocationChange={setLocation}
          paths={location === 'worktree' ? WORKTREE_FILES : ROOT_FILES}
          changed={location === 'worktree' ? CHANGE_MARKS : {}}
          currentPath={null}
          onOpen={openFile}
        />
      )
    }
    if (isFileTabId(id)) {
      const path = filePath(id)
      const mark = location === 'worktree' ? CHANGE_MARKS[path] : undefined
      return (
        <div className="flex h-full min-h-0 flex-col overflow-auto" style={{ background: 'var(--bg)' }}>
          <FilePreview
            path={path}
            content={contentFor(path)}
            headerActions={
              <>
                <span className="aw-file-where" title={location === 'worktree' ? `As it is in ${agent}’s worktree` : 'As it is in the project root'}>
                  {location === 'worktree' ? `${agent}’s worktree` : 'Project root'}
                  {mark ? ` · ${mark === 'A' ? 'added' : mark === 'D' ? 'deleted' : 'modified'}` : ''}
                </span>
                <Button variant="ghost" size="sm" onClick={() => toast({ title: 'Mentions the file in the prompt', description: path })}>
                  <Icon name="add" size={14} />
                  Mention
                </Button>
                <Button variant="ghost" size="icon-sm" aria-label="Close file" onClick={() => closeTab(PROJECT_ID, id)}>
                  <Icon name="close" size={16} />
                </Button>
              </>
            }
          />
        </div>
      )
    }
    if (id === ID.terminal) {
      const active = term.shells.find((sh) => sh.id === term.activeId) ?? null
      return (
        <TerminalTab
          agent={agent}
          unavailable={tab === 'terminal-remote' ? 'remote' : tab === 'terminal-docker' ? 'docker' : null}
          shells={term.shells}
          activeId={term.activeId}
          onSelect={term.setActiveId}
          onClose={term.close}
          onRestart={term.restart}
          options={SHELL_OPTIONS}
          lastPick={term.lastPick}
          onOpen={term.open}
          onSendToAgent={(sid) => {
            const sh = term.shells.find((x) => x.id === sid)
            if (!sh) return
            const screen = shellLines(sh, term.runs[sid] ?? 0).map(([t]) => t).join('\n')
            setComposerDraft(PROJECT_ID, agent, null, `From ${sh.option.label} in ${sh.directory}:\n\n\`\`\`\n${screen}\n\`\`\`\n`)
            toast({ title: `The screen is in your message to ${agent}`, description: 'Nothing is sent until you send it.' })
          }}
        >
          {active && <MockShell key={`${active.id}-${term.runs[active.id] ?? 0}`} lines={shellLines(active, term.runs[active.id] ?? 0)} />}
        </TerminalTab>
      )
    }
    if (id === ID.watch) {
      const peerAgent = agents.find((a) => a.name === peer)
      return (
        <WatchTab
          peers={peers.map((p) => {
            const state = agentAttention(p.name)
            return { name: p.name, colorIndex: p.color_index, tone: state === 'running' ? 'working' : state === 'waiting' ? 'waiting' : 'idle', state: state === 'running' ? 'working' : state === 'waiting' ? 'waiting for an answer' : 'idle' }
          })}
          peer={peer}
          onPeerChange={setPeer}
          conversations={peerConversations.map((c) => ({ id: c.id, title: conversationLabel(c), when: formatAgo(c.updated_at, now) }))}
          conversationId={watchedId}
          onConversationChange={setPeerConversation}
          onOpenConversation={() => go({ kind: 'conversation', agent: peer, conversationId: watchedId })}
        >
          {watchedChat && peerAgent ? (
            <AgentTimeline agent={peerAgent} entries={watchedChat.entries} roster={agents} runs={watchedChat.runs} isRunning={false} foldAllSignal={0} />
          ) : (
            <p className="aw-ptab-note" style={{ padding: 16 }}>
              The mock holds no recording of {peer}’s conversations: pick Builder or Architect.
            </p>
          )}
        </WatchTab>
      )
    }
    return (
      <p style={{ padding: 16, fontSize: 13, color: 'var(--text-3)' }}>
        Specs is unchanged by this roadmap. <a href="#" onClick={(e) => { e.preventDefault(); if (route.kind === 'conversation') go({ ...route, panel: 'spec' }) }}>Open the spec panel mock</a>.
      </p>
    )
  }

  return (
    <div className="h-full min-w-0 flex-1" style={{ minWidth: SPEC_DOC_MIN_WIDTH, borderLeft: '1px solid var(--border)' }} data-testid="side-panel">
      <PanelShell projectId={PROJECT_ID} availableTabs={ORDER.map((k) => describe(ID[k]))} describeTab={describe} renderTabContent={(t) => render(t.id)} />
    </div>
  )
}

type Line = [string, 'prompt' | 'out' | 'ok' | 'err' | 'dim']

// mock state: what the Hub would detect on this Windows machine (FR-4).
const SHELL_OPTIONS: ShellOption[] = [
  { id: 'pwsh', label: 'PowerShell 7', detail: 'C:\\Program Files\\PowerShell\\7\\pwsh.exe' },
  { id: 'powershell', label: 'Windows PowerShell', detail: 'Built into Windows' },
  { id: 'cmd', label: 'Command Prompt', detail: 'Built into Windows' },
  { id: 'gitbash', label: 'Git Bash', detail: 'C:\\Program Files\\Git\\bin\\bash.exe' },
  { id: 'wsl-ubuntu', label: 'Ubuntu-24.04', detail: 'WSL · opens at the folder’s /mnt/c path', wsl: true },
]
const optionFor = (id: string): ShellOption => SHELL_OPTIONS.find((o) => o.id === id) ?? SHELL_OPTIONS[0]

/** How each kind of shell names a Windows directory: WSL sees /mnt/c/..., Git Bash /c/... */
function dirFor(option: ShellOption, location: PanelLocation, agent: string): string {
  const win = location === 'worktree' ? `${WORKTREE_DIR}${agent}` : ROOT_DIR
  const posix = win.slice(2).replace(/\\/g, '/')
  if (option.wsl) return `/mnt/c${posix}`
  if (option.id === 'gitbash') return `/c${posix}`
  return win
}

/** The mock's open shells, held above the tab so they survive switching panel tabs (FR-8). */
function useMockShells(agent: string, full: boolean) {
  const make = React.useCallback(
    (id: string, optionId: string, location: PanelLocation, exitCode: number | null = null): OpenShell => {
      const option = optionFor(optionId)
      return { id, option, location, directory: dirFor(option, location, agent), exitCode }
    },
    [agent],
  )
  const initial = React.useMemo(() => {
    const base = [make('sh-1', 'pwsh', 'worktree'), make('sh-2', 'gitbash', 'root'), make('sh-3', 'wsl-ubuntu', 'worktree', 0)]
    return full ? [...base, make('sh-4', 'cmd', 'root')] : base
  }, [make, full])
  const [shells, setShells] = React.useState<OpenShell[]>(initial)
  const [activeId, setActiveId] = React.useState<string | null>('sh-1')
  const [runs, setRuns] = React.useState<Record<string, number>>({})
  const [lastPick, setLastPick] = React.useState<{ optionId: string; location: PanelLocation } | null>({ optionId: 'pwsh', location: 'worktree' })
  const next = React.useRef(10)
  React.useEffect(() => {
    setShells(initial)
    setActiveId('sh-1')
  }, [initial])
  return {
    shells,
    activeId,
    setActiveId,
    runs,
    lastPick,
    open: (optionId: string, location: PanelLocation) => {
      const id = `sh-${next.current++}`
      setShells((list) => [...list, make(id, optionId, location)])
      setRuns((r) => ({ ...r, [id]: 1 }))
      setActiveId(id)
      setLastPick({ optionId, location })
    },
    close: (id: string) => {
      const rest = shells.filter((x) => x.id !== id)
      setShells(rest)
      if (activeId === id) setActiveId(rest[rest.length - 1]?.id ?? null)
    },
    restart: (id: string) => {
      setShells((list) => list.map((x) => (x.id === id ? { ...x, exitCode: null } : x)))
      setRuns((r) => ({ ...r, [id]: (r[id] ?? 0) + 1 }))
    },
  }
}

/** A recording per shell; a new or restarted shell shows only its banner and prompt. */
function shellLines(sh: OpenShell, run: number): Line[] {
  const d = sh.directory
  const kind = sh.option.wsl ? 'wsl' : sh.option.id
  const prompt = kind === 'wsl' ? `huida@PC:${d}$ ` : kind === 'gitbash' ? '$ ' : kind === 'cmd' ? `${d}>` : `PS ${d}> `
  const banner: Line[] =
    kind === 'wsl'
      ? [['Welcome to Ubuntu 24.04.1 LTS (GNU/Linux 5.15 microsoft-standard-WSL2)', 'dim']]
      : kind === 'cmd'
        ? [['Microsoft Windows [Version 10.0.26200]', 'dim']]
        : kind === 'gitbash'
          ? [[`huida@PC MINGW64 ${d}`, 'ok']]
          : [[kind === 'pwsh' ? 'PowerShell 7.5.2' : 'Windows PowerShell', 'dim']]
  const p = (cmd = ''): Line => [prompt + cmd, 'prompt']
  if (run > 0) return [...banner, p()]
  if (sh.id === 'sh-1') return TERMINAL_LINES.map(([t, tone]): Line => [t.replace(/C:\\Users\\huida\\Projects\\Terra\\\.agentweave\\worktrees\\Builder/g, d), tone])
  if (sh.id === 'sh-2')
    return [...banner, p('npm run dev'), ['', 'out'], ['> terra@0.4.0 dev', 'dim'], ['> vite', 'dim'], ['', 'out'], ['  VITE v6.2.0  ready in 412 ms', 'ok'], ['', 'out'], ['  ➜  Local:   http://localhost:5173/', 'out'], ['  ➜  press h + enter to show help', 'dim']]
  if (sh.id === 'sh-3') return [...banner, p('make check'), ['ruff check . && pytest -q', 'dim'], ['........................................ [100%]', 'ok'], ['40 passed in 3.12s', 'ok'], p('exit'), ['logout', 'dim']]
  return [...banner, p()]
}

const TONE: Record<string, string> = { prompt: 'var(--text)', out: 'var(--text-2)', ok: 'var(--green)', err: 'var(--red)', dim: 'var(--text-3)' }

/** A recording standing in for the terminal emulator the app will mount. */
function MockShell({ lines }: { lines: Line[] }) {
  return (
    <pre style={{ margin: 0, font: 'inherit', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
      {lines.map(([text, tone], i) => (
        <div key={i} style={{ color: TONE[tone] }}>
          {text || ' '}
          {i === lines.length - 1 && tone === 'prompt' ? <span className="aw-term-caret" style={{ display: 'inline-block', width: 7, height: 14, marginLeft: 1, verticalAlign: 'text-bottom', background: 'var(--text-2)' }} /> : null}
        </div>
      ))}
    </pre>
  )
}

/** The real ChangesTab, fed the fixtures in the shape the Hub's route answers. */
function MockChanges({ agent, onOpenFile }: { agent: string; onOpenFile: (path: string) => void }) {
  const [scope, setScope] = React.useState<'turn' | 'branch'>('turn')
  const [selected, setSelected] = React.useState<string | null>(null)
  const info = (f: DiffFile) => {
    const [added, removed] = diffStat(f.patch)
    return { path: f.path, status: f.status, added, removed, binary: false }
  }
  const file = (scope === 'turn' ? TURN_CHANGES : BRANCH_CHANGES).find((f) => f.path === selected)
  return (
    <ChangesTab
      agent={agent}
      data={{ state: 'ok', agent, branch: `agentweave/${agent}`, base: BASE_BRANCH, turn: TURN_CHANGES.map(info), since_base: BRANCH_CHANGES.map(info), running: false, working_now: [] }}
      scope={scope}
      onScopeChange={(next) => {
        setScope(next)
        setSelected(null)
      }}
      selected={selected}
      onSelect={setSelected}
      patch={file ? { status: 'ready', patch: { path: file.path, patch: file.patch, binary: false, truncated: false, total_lines: file.patch.split('\n').length } } : null}
      onOpenFile={onOpenFile}
    />
  )
}
