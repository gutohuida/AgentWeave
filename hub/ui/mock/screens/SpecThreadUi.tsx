import * as React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ChatHistoryResponse } from '@/api/agentChat'
import type { ModelCatalogResponse } from '@/api/modelCatalog'
import { AgentTimeline } from '@/components/agents/AgentTimeline'
import { ConversationComposerDock } from '@/components/conversation/ConversationComposerDock'
import { ConversationSpecOffers } from '@/components/conversation/ConversationSpecOffers'
import { SpecCreatedNote } from '@/components/conversation/SpecCreatedNote'
import { SpecPageHeader, type SpecPageHeaderProps } from '@/components/spec/page/SpecPageHeader'
import type { DocState, ShownState, SpecDocumentView } from '@/components/spec/page/model'
import { toast } from '@/lib/toast'
import { agents, PROJECT_ID } from '../fixtures'
import architectChat from '../fixtures/chat_architect_9cdda4.json'
import modelCatalog from '../fixtures/model_catalog.json'
import type { ScreenProps } from '../routes'
import { useSpecMock } from '../specMock'
import '@/styles/spec-page.css'

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
queryClient.setQueryData(['model-catalog'], modelCatalog as unknown as ModelCatalogResponse)

const TITLE = 'Add --shout flag to greet.py'
const PATH = 'spec/changes/add-shout-flag-to-greet-py/spec.json'
const RUNNER = { cli: 'claude', model: 'claude-sonnet-5-5' }

// mock state: the four document states the header must tell apart. The first two are the same
// document still being written, at two steps of its journey.
const HEADER_STATES: Array<{ caption: string; state: DocState; shown: ShownState; step: string | null }> = [
  { caption: 'Being written, at Intake', state: 'writing', shown: 'writing', step: 'intake' },
  { caption: 'Being written, at Build', state: 'writing', shown: 'writing', step: 'build' },
  { caption: 'Approved', state: 'approved', shown: 'approved', step: null },
  { caption: 'Building', state: 'building', shown: 'building', step: null },
]

const noop = () => undefined

function Caption({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1.5 mt-0 text-[11px] font-medium uppercase tracking-wide" style={{ color: 'var(--text-3)' }}>
      {children}
    </p>
  )
}

function HeaderVariant({ base, caption, state, shown, step, now }: { base: SpecDocumentView; caption: string; state: DocState; shown: ShownState; step: string | null; now: Date }) {
  const doc: SpecDocumentView = { ...base, title: TITLE, kind: 'change-spec', state, shown, step, phase: state === 'writing' ? 'exploring' : 'approved', roadmap: null }
  const props: SpecPageHeaderProps = {
    doc,
    check: { status: 'idle' },
    now,
    canBack: false,
    canForward: false,
    onBack: noop,
    onForward: noop,
    onAction: noop,
    onJumpToFindings: noop,
    onOpenDocument: noop,
    onCopyLink: noop,
    onCopyPath: noop,
  }
  return (
    <div>
      <Caption>{caption}</Caption>
      <div className="aw-sp" style={{ height: 'auto', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
        <div className="aw-sp-main">
          <SpecPageHeader {...props} />
        </div>
      </div>
    </div>
  )
}

// mock state: the agent's last message, written short; its run facts are the recorded run's.
const CHAT = architectChat as unknown as ChatHistoryResponse
const TEMPLATE = CHAT.entries.filter((e) => String(e.content).startsWith('I’ve written') || String(e.content).startsWith("I've written"))[0] ?? CHAT.entries[CHAT.entries.length - 3]!
const ENTRIES = [
  {
    ...TEMPLATE,
    id: 'out-mock-shout',
    content:
      'Done. I wrote the change up as a specification so we can settle it before anyone builds: `greet.py` gets a `--shout` flag that prints the greeting in capitals, and nothing else about its output changes.',
  },
]
const ARCHITECT = agents.find((a) => a.name === 'Architect') ?? agents[0]!

type Variant = 'today' | 'quiet' | 'composer'

function ConversationSlice({ variant }: { variant: Variant }) {
  // mock state: whether the offer is still standing, as the container would hold it.
  const [offered, setOffered] = React.useState(true)
  const [opened, setOpened] = React.useState(false)
  const open = () => {
    setOffered(false)
    setOpened(true)
    toast({ title: `${TITLE} is open in this thread`, tone: 'success' })
  }
  const dismiss = () => setOffered(false)
  const standing = offered && !opened
  const offer = { path: PATH, title: TITLE, step: 'tasks', created_by: 'Architect', created_at: null }
  return (
    <div className="flex flex-col overflow-hidden" style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
      <div style={{ maxWidth: 820, width: '100%', margin: '0 auto', padding: '16px 16px 0' }}>
        <AgentTimeline agent={ARCHITECT} entries={ENTRIES} roster={agents} runs={CHAT.runs} isRunning={false} />
        {variant === 'quiet' && standing ? (
          <div style={{ padding: '0 0 8px 26px' }}>
            <SpecCreatedNote title={TITLE} createdBy="Architect" onOpen={open} onDismiss={dismiss} />
          </div>
        ) : null}
      </div>
      <ConversationComposerDock
        selected={[]}
        onToggleOption={noop}
        composer={{
          key: variant,
          agent: ARCHITECT.name,
          projectId: PROJECT_ID,
          conversationId: 'conv-9cdda4865e0b',
          isRunning: false,
          onSubmit: async () => toast({ title: 'Sent to Architect', tone: 'success' }),
          runner: RUNNER.cli,
          effectiveModel: RUNNER.model,
          onOpenSpecPicker: noop,
          onStartExploration: noop,
          onStopExploring: noop,
          specDocumentLabel: opened ? TITLE : null,
          specSuggestion: variant === 'composer' && standing ? { title: TITLE, onOpen: open, onDismiss: dismiss } : null,
        }}
      >
        {variant === 'today' && standing ? (
          <ConversationSpecOffers offers={[offer]} onAnswer={(_, answer) => (answer === 'open' ? open() : dismiss())} />
        ) : null}
      </ConversationComposerDock>
    </div>
  )
}

/** How a thread shows the spec it works on (operator, 2026-11-22): the header's phase badge naming
 *  the step, and three ways to offer a document an agent created in the thread. */
export default function SpecThreadUi({ now }: ScreenProps) {
  const { surface } = useSpecMock('spec-thread-ui')
  return (
    <QueryClientProvider client={queryClient}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 36, maxWidth: 1100, width: '100%', margin: '0 auto', padding: 24, height: '100%', overflowY: 'auto' }}>
        <section style={{ display: 'flex', flexDirection: 'column', gap: 16, flex: 'none' }} aria-labelledby="stu-badge">
          <h2 id="stu-badge" className="m-0 text-[15px] font-semibold">The phase badge names the step while the spec is being written</h2>
          {HEADER_STATES.map((s) => (
            <HeaderVariant key={s.caption} base={surface.doc} now={now} {...s} />
          ))}
        </section>
        <section style={{ display: 'flex', flexDirection: 'column', gap: 16, flex: 'none' }} aria-labelledby="stu-offer">
          <h2 id="stu-offer" className="m-0 text-[15px] font-semibold">Offering a spec the agent created in this thread</h2>
          <div>
            <Caption>A. Today: a card above the composer</Caption>
            <ConversationSlice variant="today" />
          </div>
          <div>
            <Caption>B. Quiet: a line in the transcript, under the message that created it</Caption>
            <ConversationSlice variant="quiet" />
          </div>
          <div>
            <Caption>C. In the composer: Explore offers it</Caption>
            <ConversationSlice variant="composer" />
          </div>
        </section>
      </div>
    </QueryClientProvider>
  )
}
