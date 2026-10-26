import * as React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ChatHistoryResponse } from '@/api/agentChat'
import { conversationLabel } from '@/api/agentChat'
import type { ModelCatalogResponse } from '@/api/modelCatalog'
import type { Question } from '@/api/questions'
import { AgentTimeline } from '@/components/agents/AgentTimeline'
import { Icon } from '@/components/common/Icon'
import { ConversationBar } from '@/components/conversation/ConversationBar'
import { ConversationComposerDock } from '@/components/conversation/ConversationComposerDock'
import { NewConversationIntro, type ConversationStarter } from '@/components/conversation/NewConversationIntro'
import { StartBuildDialog } from '@/components/spec/page/SpecBuilds'
import { SpecSidePanel } from '@/components/spec/page/SpecWorkspace'
import { CONVERSATION_MIN_WIDTH, SPEC_DOC_MIN_WIDTH } from '@/components/spec/specPreferences'
import { toast } from '@/lib/toast'
import { setComposerDraft } from '@/lib/composerDrafts'
import { useDiagnosticsHidden } from '@/lib/diagnosticsPreference'
import { agentAttention, agents, conversations, PROJECT_ID } from '../fixtures'
import builderChat from '../fixtures/chat_builder_e3aba2.json'
import architectChat from '../fixtures/chat_architect_9cdda4.json'
import modelCatalog from '../fixtures/model_catalog.json'
import type { ScreenProps } from '../routes'
import { useSpecMock } from '../specMock'

const CHATS: Record<string, ChatHistoryResponse> = {
  'conv-e3aba2c5956a': builderChat as unknown as ChatHistoryResponse,
  'conv-9cdda4865e0b': architectChat as unknown as ChatHistoryResponse,
}

/** The composer's model and permission pills read the catalog through React Query; the mock seeds
 *  the cache with the replica's catalog (queries stay disabled: there is no Hub key). */
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
queryClient.setQueryData(['model-catalog'], modelCatalog as unknown as ModelCatalogResponse)

// mock state: the replica's agents lost their runners when it was made inert; the mock shows the
// runner they had, so the composer's model pills and the intro's "runs on" line have something to say.
const RUNNER = { cli: 'claude', label: 'Claude Code', model: 'claude-sonnet-5-5', modelLabel: 'Sonnet 5.5', posture: 'Workspace only' }

// mock state: Builder is marked working (fixtures.ts), so it is shown mid-turn and asking a question.
const BUILDER_QUESTION: Question = {
  id: 'q-mock-1',
  project_id: PROJECT_ID,
  from_agent: 'Builder',
  header: 'Export format',
  question:
    'The export can write one CSV per table, or a single workbook with a sheet per table. The workbook is easier to share; the CSVs are easier to diff. Which do you want?',
  options: [
    { label: 'One CSV per table', description: 'Plain files that diff cleanly; several files to send.' },
    { label: 'A single workbook', description: 'One file to share; binary, so it does not diff.' },
    { label: 'Ask QA1 to reproduce it first', description: 'Builder waits for QA1’s repro before choosing.' },
  ],
  blocking: true,
  answered: false,
  batch_size: 1,
  created_at: '2026-10-17T12:08:00Z',
  asker_waiting: true,
}

const STARTERS: ConversationStarter[] = [
  { label: 'Pick up the next task', message: 'Look at the open tasks assigned to you and start on the most important one.', icon: 'task_alt' },
  { label: 'Catch up on today', message: 'Summarize what changed in the project today and what is still open.', icon: 'event_note' },
  { label: 'Review the latest work', message: 'Review the most recent merged change against its requirements and report anything missing.', icon: 'fact_check' },
]

export default function Conversation(props: ScreenProps) {
  const withSpec = props.route.kind === 'conversation' && props.route.panel === 'spec'
  return (
    <QueryClientProvider client={queryClient}>
      {withSpec ? (
        <div className="flex h-full min-w-0 flex-row overflow-hidden">
          <div className="flex h-full min-w-0 flex-1 flex-col" style={{ minWidth: CONVERSATION_MIN_WIDTH }}>
            <ConversationMock {...props} />
          </div>
          <SpecPanelMock />
        </div>
      ) : (
        <ConversationMock {...props} />
      )}
    </QueryClientProvider>
  )
}

/** The conversation's spec panel, redesigned: the same components as the Spec tab in one column.
 *  At a window narrower than 1200px it sits at its narrowest width (the app's SPEC_DOC_MIN_WIDTH). */
function SpecPanelMock() {
  const { surface, startDialog } = useSpecMock('conversation/Architect/conv-9cdda4865e0b/spec')
  const [width, setWidth] = React.useState(() => (window.innerWidth >= 1200 ? 440 : SPEC_DOC_MIN_WIDTH))
  React.useEffect(() => {
    const onResize = () => setWidth(window.innerWidth >= 1200 ? 440 : SPEC_DOC_MIN_WIDTH)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return (
    <div className="h-full flex-none" style={{ width }} data-testid="spec-panel">
      <SpecSidePanel {...surface} />
      <StartBuildDialog {...startDialog} />
    </div>
  )
}

function ConversationMock({ route, go }: ScreenProps) {
  const agentName = route.kind === 'conversation' ? route.agent : 'Builder'
  const conversationId = route.kind === 'conversation' ? route.conversationId : null
  const agent = agents.find((a) => a.name === agentName) ?? agents[0]!
  const conversation = conversations.find((c) => c.id === conversationId) ?? null
  const chat = conversationId ? CHATS[conversationId] : undefined
  const isRunning = agentAttention(agent.name) === 'running' && conversation?.attention === 'running'

  const [diagnosticsHidden, setDiagnosticsHidden] = useDiagnosticsHidden()
  const [foldAll, setFoldAll] = React.useState(0)
  const [title, setTitle] = React.useState(conversation ? conversationLabel(conversation) : 'New conversation')
  const [selected, setSelected] = React.useState<string[]>([])
  const [composerKey, setComposerKey] = React.useState(0)
  const [elapsed, setElapsed] = React.useState(134)
  const [following, setFollowing] = React.useState(true)
  const scroller = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => setTitle(conversation ? conversationLabel(conversation) : 'New conversation'), [conversation])
  React.useEffect(() => {
    if (!isRunning) return
    const timer = window.setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => window.clearInterval(timer)
  }, [isRunning])
  React.useLayoutEffect(() => {
    const el = scroller.current
    if (el) el.scrollTop = el.scrollHeight
    setFollowing(true)
  }, [conversationId])

  const questions = isRunning && agent.name === 'Builder' ? [BUILDER_QUESTION] : []

  return (
    <div className="flex h-full flex-col overflow-hidden" style={{ background: 'var(--bg)' }} data-testid="conversation-panel">
      <ConversationBar
        agent={agent}
        conversation={conversation}
        title={title}
        onRename={(next) => {
          setTitle(next)
          toast({ title: 'Conversation renamed', description: next, tone: 'success' })
        }}
        isRunning={isRunning}
        elapsedSeconds={isRunning ? elapsed : null}
        onStop={() => toast({ title: `Stopping ${agent.name}'s turn` })}
        onCheckpoint={conversation ? () => toast({ title: 'Writing a checkpoint', description: 'The successor conversation opens when it is ready.' }) : undefined}
        checkpointDisabledReason={isRunning ? 'Unavailable while the agent is busy' : null}
        totalTokens={conversation?.context_usage?.context_tokens ?? null}
        diagnosticsHidden={diagnosticsHidden}
        onToggleDiagnostics={() => setDiagnosticsHidden(!diagnosticsHidden)}
        onFoldAll={() => setFoldAll((n) => n + 1)}
        onOpenCheckpoints={conversation ? () => undefined : undefined}
        onOpenTrace={chat ? () => undefined : undefined}
        onOpenAgentSettings={() => go({ kind: 'agent-settings', agent: agent.name, section: 'execution' })}
        onArchive={() => toast({ title: 'Conversation archived', action: { label: 'Undo', onClick: () => undefined } })}
      />

      <div className="flex min-h-0 flex-1 flex-col">
        <div
          ref={scroller}
          className="flex-1 overflow-y-auto py-[22px]"
          style={{ background: 'var(--bg)' }}
          data-testid="conversation-output"
          onScroll={(e) => {
            const el = e.currentTarget
            setFollowing(el.scrollHeight - el.scrollTop - el.clientHeight < 40)
          }}
        >
          {chat ? (
            <AgentTimeline
              agent={agent}
              entries={chat.entries}
              roster={agents}
              runs={chat.runs}
              isRunning={false}
              foldAllSignal={foldAll}
            />
          ) : (
            <NewConversationIntro
              agent={agent}
              runnerLabel={RUNNER.label}
              modelLabel={RUNNER.modelLabel}
              postureLabel={RUNNER.posture}
              starters={STARTERS}
              onPick={(message) => {
                setComposerDraft(PROJECT_ID, agent.name, null, message)
                setComposerKey((k) => k + 1)
              }}
            />
          )}
        </div>
        {!following && (
          <div className="flex shrink-0 justify-center pb-2">
            <button
              type="button"
              onClick={() => {
                const el = scroller.current
                el?.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
              }}
              aria-label="Jump to newest"
              title="Jump to newest"
              className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11.5px] font-medium"
              style={{
                background: 'var(--surface-3)',
                border: '1px solid var(--border-hi)',
                color: 'var(--text)',
                boxShadow: '0 2px 10px rgba(0,0,0,0.28)',
              }}
            >
              <Icon name="expand_more" size={13} />
              Jump to newest
            </button>
          </div>
        )}
      </div>

      <ConversationComposerDock
        questions={questions}
        selected={selected}
        onToggleOption={(label) => setSelected((s) => (s.includes(label) ? [] : [label]))}
        onDecline={() => toast({ title: 'Question dismissed' })}
        composer={{
          key: `${agent.name}::${conversationId ?? '__new__'}::${composerKey}`,
          agent: agent.name,
          projectId: PROJECT_ID,
          conversationId,
          isRunning: false,
          onSubmit: async () => {
            toast({ title: questions.length ? `Answer sent to ${agent.name}` : `Sent to ${agent.name}`, tone: 'success' })
          },
          runner: RUNNER.cli,
          effectiveModel: RUNNER.model,
        }}
      />
    </div>
  )
}
