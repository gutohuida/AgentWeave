import { formatDistanceToNow } from 'date-fns'
import { conversationLabel, useAgentChatHistory, useProjectConversations } from '@/api/agentChat'
import { useAgents } from '@/api/agents'
import { useQuestions } from '@/api/questions'
import { AgentTimeline } from '@/components/agents/AgentTimeline'
import { Button } from '@/components/ui/button'
import { hubDate } from '@/lib/hubTime'
import { selectWatchChoice, useWatchChoiceStore } from '@/store/watchChoiceStore'
import { WatchTab } from './WatchTab'
import { resolveWatch, watchState } from './watchModel'

export interface WatchTabContainerProps {
  projectId: string
  /** The conversation the main view shows, so it is not drawn a second time (FR-9). */
  mainConversationId: string | null
  /** Makes this agent's conversation the main view. */
  onOpenConversation: (agent: string, conversationId: string) => void
}

/** The watched conversation, drawn by the app's own timeline with none of its controls. */
function WatchedTimeline({ agentName, conversationId }: { agentName: string; conversationId: string }) {
  const { data: agents = [], error: agentsError } = useAgents()
  const { data: chatData, error: chatError } = useAgentChatHistory(agentName, conversationId)
  const agent = agents.find((a) => a.name === agentName)
  if (agentsError || chatError) {
    return (
      <p className="aw-ptab-note" data-testid="watch-load-error">
        Could not load this thread: {((chatError ?? agentsError) as Error).message}
      </p>
    )
  }
  if (!agent || !chatData) return <p className="aw-ptab-note">Loading thread</p>
  return (
    <AgentTimeline
      agent={agent}
      entries={chatData.entries}
      roster={agents}
      runs={chatData.runs}
      isRunning={false}
      foldAllSignal={0}
    />
  )
}

/** The Watch tab fed from the app's own data: nothing here reaches a Hub route that did not exist. */
export function WatchTabContainer({ projectId, mainConversationId, onOpenConversation }: WatchTabContainerProps) {
  const { data: agents = [], isLoading: agentsLoading, error: agentsError } = useAgents()
  const { data: conversationList, error: conversationsError } = useProjectConversations(projectId)
  const { data: questions = [], error: questionsError } = useQuestions(false)
  const loadError = agentsError ?? conversationsError ?? questionsError
  const choice = useWatchChoiceStore((state) => selectWatchChoice(state, projectId))
  const chooseAgent = useWatchChoiceStore((state) => state.chooseAgent)
  const pickConversation = useWatchChoiceStore((state) => state.pickConversation)

  const { agent, conversations, conversation } = resolveWatch(choice, agents, conversationList?.conversations ?? [])
  const peers = agents.map((a) => {
    const state = watchState(a, questions)
    const tone = state === 'working' ? 'working' : state === 'idle' ? 'idle' : 'waiting'
    return { name: a.name, colorIndex: a.color_index, state, tone } as const
  })
  const inMainView = !!conversation && conversation.id === mainConversationId

  return (
    <WatchTab
      peers={peers}
      peer={agent?.name ?? ''}
      onPeerChange={(name) => chooseAgent(projectId, name)}
      conversations={conversations.map((c) => ({
        id: c.id,
        title: conversationLabel(c),
        when: formatDistanceToNow(hubDate(c.updated_at), { addSuffix: true }),
      }))}
      conversationId={conversation?.id ?? null}
      onConversationChange={(id) => pickConversation(projectId, id)}
      onOpenConversation={() => agent && conversation && onOpenConversation(agent.name, conversation.id)}
    >
      {loadError ? (
        <p className="aw-ptab-note" data-testid="watch-load-error">
          Could not load the Watch tab: {(loadError as Error).message}
        </p>
      ) : !agent ? (
        agentsLoading ? null : (
          <p className="aw-ptab-note" data-testid="watch-choose-agent">
            Choose a profile to watch.
          </p>
        )
      ) : !conversation ? (
        <p className="aw-ptab-note" data-testid="watch-no-conversation">
          {agent.name} has no thread yet.
        </p>
      ) : inMainView ? (
        <div className="aw-ptab-note" data-testid="watch-in-this-conversation">
          <p>You are in this thread.</p>
          {conversations.length > 1 ? <p>Watch another of {agent.name}’s conversations:</p> : null}
          {conversations
            .filter((c) => c.id !== conversation.id)
            .map((c) => (
              <div key={c.id}>
                <Button size="xs" variant="outline" onClick={() => pickConversation(projectId, c.id)}>
                  {conversationLabel(c)}
                </Button>
              </div>
            ))}
        </div>
      ) : (
        <WatchedTimeline agentName={agent.name} conversationId={conversation.id} />
      )}
    </WatchTab>
  )
}
