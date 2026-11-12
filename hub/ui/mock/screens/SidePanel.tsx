import * as React from 'react'
import type { ChatHistoryResponse } from '@/api/agentChat'
import { conversationLabel } from '@/api/agentChat'
import { AgentTimeline } from '@/components/agents/AgentTimeline'
import { Icon } from '@/components/common/Icon'
import { ChangesTab } from '@/components/panel/ChangesTab'
import { FilesTab } from '@/components/panel/FilesTab'
import type { PanelLocation } from '@/components/panel/LocationSwitch'
import { RunningTab } from '@/components/panel/RunningTab'
import { runningItems } from '@/components/panel/runningModel'
import { TerminalTab } from '@/components/panel/TerminalTab'
import { WatchTab } from '@/components/panel/WatchTab'
import { FilePreview } from '@/components/spec/FilePreview'
import { PanelShell, type PanelTabDescriptor } from '@/components/spec/PanelShell'
import { fileIconFor } from '@/components/spec/fileIcons'
import { SPEC_DOC_MIN_WIDTH } from '@/components/spec/specPreferences'
import { Button } from '@/components/ui/button'
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

export type SidePanelTab = 'running' | 'changes' | 'files' | 'terminal' | 'terminal-remote' | 'watch'

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
    store.activateTab(PROJECT_ID, ID[tab === 'terminal-remote' ? 'terminal' : tab])
  }, [tab])

  const items = React.useMemo(() => runningItems({ builds: RUNNING_BUILDS, loops: RUNNING_LOOPS, jobs: RUNNING_JOBS, now }), [now])
  const live = items.filter((i) => i.phase === 'needs-you' || i.phase === 'working').length
  const [location, setLocation] = React.useState<PanelLocation>('worktree')
  const [termLocation, setTermLocation] = React.useState<PanelLocation>('worktree')
  const [shellRun, setShellRun] = React.useState(0)
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
      return <ChangesTab agent={agent} branch={`agentweave/${agent}`} base={BASE_BRANCH} turn={TURN_CHANGES} wholeBranch={BRANCH_CHANGES} onOpenFile={openFile} />
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
      const dir = termLocation === 'worktree' ? `${WORKTREE_DIR}${agent}` : ROOT_DIR
      return (
        <TerminalTab
          agent={agent}
          location={termLocation}
          onLocationChange={(next) => {
            setTermLocation(next)
            setShellRun((n) => n + 1)
          }}
          directory={dir}
          shell="PowerShell"
          available={tab !== 'terminal-remote'}
          onRestart={() => setShellRun((n) => n + 1)}
        >
          <MockShell key={shellRun} fresh={shellRun > 0} dir={dir} />
        </TerminalTab>
      )
    }
    if (id === ID.watch) {
      const peerAgent = agents.find((a) => a.name === peer)
      return (
        <WatchTab
          peers={peers.map((p) => {
            const state = agentAttention(p.name)
            return { name: p.name, colorIndex: p.color_index, working: state === 'running', state: state === 'running' ? 'working' : state === 'waiting' ? 'waiting for an answer' : 'idle' }
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

const TONE: Record<string, string> = { prompt: 'var(--text)', out: 'var(--text-2)', ok: 'var(--green)', err: 'var(--red)', dim: 'var(--text-3)' }

/** A recording standing in for the terminal emulator the app will mount. A restart, or a change of
 *  directory, shows a fresh shell. */
function MockShell({ fresh, dir }: { fresh: boolean; dir: string }) {
  const lines: typeof TERMINAL_LINES = fresh ? [['PowerShell 7.5.2', 'dim'], [`PS ${dir}> `, 'prompt']] : TERMINAL_LINES
  return (
    <pre style={{ margin: 0, font: 'inherit', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
      {lines.map(([text, tone], i) => (
        <div key={i} style={{ color: TONE[tone] }}>
          {text.replace(/C:\\Users\\huida\\Projects\\Terra\\\.agentweave\\worktrees\\Builder/g, dir) || ' '}
          {i === lines.length - 1 ? <span className="aw-term-caret" style={{ display: 'inline-block', width: 7, height: 14, marginLeft: 1, verticalAlign: 'text-bottom', background: 'var(--text-2)' }} /> : null}
        </div>
      ))}
    </pre>
  )
}
