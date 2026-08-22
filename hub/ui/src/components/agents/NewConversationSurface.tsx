import { useState } from 'react'
import { useAgents } from '@/api/agents'
import { useRunners } from '@/api/runners'
import { useWorkspacePaths } from '@/api/workspace'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { postJson } from '@/api/client'
import { agentColorVars } from '@/lib/agentColors'
import { useConfigStore } from '@/store/configStore'
import { Composer } from './Composer'

interface NewConversationSurfaceProps {
  projectId: string
  /** Visible project context for the unsent message. The persistent header also exposes the
   * switcher, but the composer repeats the scope at the decision point so a message cannot look
   * detached from the project it will mutate. */
  projectName?: string
  /** Who the first message goes to. Pre-selected when the operator started from an agent's row
   *  menu, null when they started from the recency view — but a *default*, never a binding: the
   *  roster below stays live either way. */
  agent: string | null
  /** Retarget the unsent message. Starting from an agent's row is a shortcut, not a commitment;
   *  arriving with an agent pre-selected and finding the other rows dead is worse than arriving
   *  with none (operator, 2026-08-08). */
  onChooseAgent: (agent: string) => void
  /** Called once the first message has created the conversation. */
  /** `document` is set when the operator declared an exploration before writing. */
  onStarted: (agent: string, conversationId: string, document?: string) => void
  onBackToProject?: () => void
}

/**
 * Where a conversation begins.
 *
 * Composer-primary, deliberately: the alternative is an empty transcript with a composer stuck to
 * the bottom of it, which reads as a conversation that has lost its messages. Nothing is written
 * to the Hub here — a conversation is created by its first message (design.md), so abandoning this
 * surface leaves no record and no untitled row in the tree.
 *
 * The chosen agent lives in the destination rather than in local state, for the same reason the
 * open conversation does: two sources of truth for "who is this for" is how a pre-selected agent
 * ends up outranking the one the operator just clicked.
 */
export function NewConversationSurface({
  projectId,
  projectName,
  agent,
  onChooseAgent,
  onStarted,
  onBackToProject,
}: NewConversationSurfaceProps) {
  const { apiKey } = useConfigStore()
  const { data: roster = [] } = useAgents()
  const { data: runners = [] } = useRunners()
  const { data: workspacePaths = [] } = useWorkspacePaths()
  const [pendingOverrides, setPendingOverrides] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  const agentRow = roster.find((candidate) => candidate.name === agent)
  const runnerRow = runners.find((runner) => runner.id === agentRow?.runner_id)

  /* Declaring an exploration before the first message is the one case where the intent
   * genuinely precedes the document: there is no conversation to attach one to and no title to
   * name it from. The document is created from that first message, so the armed state lasts
   * exactly as long as it takes to write one. */
  const [exploring, setExploring] = useState(false)

  const handleSubmit = async (message: string): Promise<void> => {
    if (!agent) return
    setError(null)

    /* The document is created BEFORE the turn, not after it. Creating it afterwards left the
     * first message — the one that decides how the agent frames the whole exploration — with no
     * document attached, so the turn context carried no phase and no `submit_spec_document`, and
     * the agent reached for a workflow of its own. That was the entire symptom this control was
     * added to fix, and doing the two in the wrong order reproduced it exactly.
     *
     * No path is sent. The Hub mints a placeholder — a colour and an animal — because this is the
     * one moment at which nobody knows what the document is about, and the name this used to
     * derive from the operator's opening sentence outlived the guess that produced it. The agent
     * renames it once the interview settles the subject. */
    let specDocument: string | null = null
    if (exploring) {
      try {
        const created = await postJson<{ path: string }>(
          `/api/v1/projects/${projectId}/project/documents`,
          { title: message.trim().slice(0, 120) },
        )
        specDocument = created.path
      } catch {
        // A minted name cannot collide, so this is a real failure rather than the document
        // already being there. Send the turn anyway: losing the operator's first message —
        // the one that decides how the agent frames the whole exploration — is the worse loss.
        specDocument = null
      }
    }

    const response = await fetch(`/api/v1/projects/${projectId}/agent/trigger`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` },
      body: JSON.stringify({
        agent,
        message,
        spec_document: specDocument ?? undefined,
        overrides: Object.keys(pendingOverrides).length > 0 ? pendingOverrides : undefined,
      }),
    })
    if (!response.ok) {
      setError('Could not start the conversation')
      throw new Error(`Trigger failed with status ${response.status}`)
    }
    const result = (await response.json()) as { conversation_id: string }
    // Two arguments when there is no document, not a third that happens to be undefined.
    if (specDocument) onStarted(agent, result.conversation_id, specDocument)
    else onStarted(agent, result.conversation_id)
  }

  return (
    <div className="flex h-full flex-col overflow-hidden" style={{ background: 'var(--bg)' }}>
      <div
        className="conversation-header-surface flex shrink-0 items-center gap-2 px-4 py-2.5"
        data-testid="conversation-header"
      >
        {onBackToProject && (
          <Button variant="ghost" size="icon-sm" onClick={onBackToProject} aria-label="Back to project" title="Back to project">
            <Icon name="arrow_left" size={16} />
          </Button>
        )}
        <span className="text-[13px] font-medium" style={{ color: 'var(--text)' }}>
          New conversation
        </span>
      </div>

      <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-4">
        <div className="flex w-full max-w-[820px] flex-col gap-4" data-testid="new-conversation-surface">
          <div className="flex justify-center">
            <span
              className="aw-chip"
              data-testid="new-conversation-project-context"
              style={{ background: 'var(--surface-2)', borderColor: 'var(--border)', color: 'var(--text-2)' }}
            >
              <Icon name="folder_open" size={13} />
              Project: {projectName ?? projectId}
            </span>
          </div>
          <div className="new-conversation-icon" aria-hidden="true">
            <Icon name="chat" size={20} />
          </div>
          {/* The one line an operator reads every time they start work. It names the agent
              rather than the project, because the project is explicit immediately above and
              the agent is the thing this product has that a chat app does not. Unbound, the
              question changes to the one that actually has to be answered first — the line is
              the instruction, not decoration above one. */}
          <h1
            data-testid="new-conversation-headline"
            className="text-center font-semibold"
            style={{ fontSize: 28, lineHeight: 1.2, color: 'var(--text)' }}
          >
            {agent ? `What should ${agent} work on?` : 'Who should work on this?'}
          </h1>

          <p className="text-center text-[11.5px]" style={{ color: 'var(--text-3)' }}>
            Start with a recent agent, or choose another before you send.
          </p>

          <div className="flex flex-wrap justify-center gap-1.5">
            {roster.map((candidate) => {
              const selected = candidate.name === agent
              return (
                <button
                  key={candidate.name}
                  type="button"
                  className="new-conversation-agent row-item"
                  style={{ width: 'auto' }}
                  data-testid={`new-conversation-agent-${candidate.name}`}
                  data-active={selected ? 'true' : 'false'}
                  aria-pressed={selected}
                  onClick={() => onChooseAgent(candidate.name)}
                >
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ background: agentColorVars(candidate.color_index).accent }}
                  />
                  {candidate.name}
                </button>
              )
            })}
          </div>

          {error && (
            <span role="alert" className="text-center text-[11px]" style={{ color: 'var(--red)' }}>
              {error}
            </span>
          )}

          <div className="conversation-composer-surface">
            <Composer
              agent={agent ?? 'an agent'}
              projectId={projectId}
              conversationId={null}
              isRunning={false}
              onSubmit={handleSubmit}
              placeholder={agent ? `Message ${agent}…` : 'Choose an agent, then write your first message…'}
              disabledReason={agent ? undefined : 'Choose an agent to start'}
              workspacePaths={workspacePaths}
              runner={runnerRow?.cli ?? null}
              effectiveModel={runnerRow?.model ?? null}
              pendingOverrides={pendingOverrides}
              onPendingOverridesChange={setPendingOverrides}
              specDocumentLabel={null}
              specArmed={exploring}
              onOpenSpecPicker={() => setExploring(true)}
              onStartExploration={() => setExploring(true)}
              onStopExploring={() => setExploring(false)}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
