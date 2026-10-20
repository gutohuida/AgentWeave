import { useState } from 'react'
import { postureAtRest, useAgents } from '@/api/agents'
import { useRunners } from '@/api/runners'
import { overridesForRunner, runnerSetsModel } from '@/lib/runnerProvider'
import { useWorkspacePaths } from '@/api/workspace'
import {
  permissionModeValues,
  providerForRunner,
  resolveCatalogModel,
  useModelCatalog,
} from '@/api/modelCatalog'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { ApiError, deleteJson, postJson, readableRefusal } from '@/api/client'
import { ConversationComposerDock } from '@/components/conversation/ConversationComposerDock'
import {
  NewConversationIntro,
  type ConversationStarter,
} from '@/components/conversation/NewConversationIntro'
import { agentColorVars } from '@/lib/agentColors'
import { setComposerDraft } from '@/lib/composerDrafts'
import { useConfigStore } from '@/store/configStore'

/** Ways to start, offered under the intro. Picking one puts its message in the composer — not
 *  sent: the operator edits and sends. */
const STARTERS: ConversationStarter[] = [
  { label: 'Pick up the next task', message: 'Look at the open tasks assigned to you and start on the most important one.', icon: 'task_alt' },
  { label: 'Catch up on today', message: 'Summarize what changed in the project today and what is still open.', icon: 'event_note' },
  { label: 'Review the latest work', message: 'Review the most recent merged change against its requirements and report anything missing.', icon: 'fact_check' },
]

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
  /** Bumped when a starter writes the draft, so the composer remounts and reads it. Not keyed by
   *  agent: retargeting is a change of recipient, and a half-written message survives it. */
  const [composerKey, setComposerKey] = useState(0)
  const { data: catalog } = useModelCatalog()

  const agentRow = roster.find((candidate) => candidate.name === agent)
  const runnerRow = runners.find((runner) => runner.id === agentRow?.runner_id)
  // What the intro says it runs on, in the catalog's words: the runner's name, its model's label,
  // and the posture its next run gets.
  const runnerProvider = catalog?.providers.find(
    (provider) => provider.provider === providerForRunner(runnerRow?.cli),
  )
  const modelLabel = resolveCatalogModel(runnerProvider, runnerRow?.model)?.label ?? null
  const posture = postureAtRest(agentRow)
  const postureLabel =
    permissionModeValues(catalog).find((value) => Object.values(posture).includes(value.id))?.label ?? null

  /* Declaring an exploration before the first message is the one case where the intent
   * genuinely precedes the document: there is no conversation to attach one to and no title to
   * name it from. The document is created from that first message, so the armed state lasts
   * exactly as long as it takes to write one. */
  const [exploring, setExploring] = useState(false)

  const handleSubmit = async (message: string): Promise<void> => {
    if (!agent) return
    setError(null)
    const sentOverrides = overridesForRunner(pendingOverrides, runnerRow)

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

    /* A turn that never starts must not leave its document behind (F330): each refused retry used
     * to mint another empty `exploring` placeholder. Withdrawn through the Hub's own delete, which
     * removes the row, the file and its index entry; best effort, since the refusal is what the
     * operator needs to read, and an orphan is the lesser loss. */
    const withdraw = () => {
      if (!specDocument) return
      void deleteJson(`/api/v1/projects/${projectId}/project/documents/${specDocument}`).catch(() => undefined)
    }

    let response: Response
    try {
      response = await fetch(`/api/v1/projects/${projectId}/agent/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` },
        body: JSON.stringify({
          agent,
          message,
          spec_document: specDocument ?? undefined,
          overrides: Object.keys(sentOverrides).length > 0 ? sentOverrides : undefined,
        }),
      })
    } catch (failure) {
      withdraw()
      throw failure
    }
    if (!response.ok) {
      withdraw()
      // The Hub's own sentence, where it has one (F108). It refuses a request it will never
      // honour and says why; 'Could not start the conversation' throws that away and leaves the
      // operator with a dead composer and no remedy.
      const refusal = new ApiError(response.status, await response.text())
      setError(readableRefusal(refusal, 'Could not start the conversation'))
      throw refusal
    }
    const result = (await response.json()) as { conversation_id: string }
    // Two arguments when there is no document, not a third that happens to be undefined.
    if (specDocument) onStarted(agent, result.conversation_id, specDocument)
    else onStarted(agent, result.conversation_id)
  }

  const agentChooser = (
    <div className="flex flex-col items-center gap-2" style={{ marginTop: 24 }}>
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
              data-slot="new-conversation-agent"
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
    </div>
  )

  return (
    <div className="flex h-full flex-col overflow-hidden" style={{ background: 'var(--bg)' }}>
      <div className="conversation-header-surface aw-convbar" data-testid="conversation-header">
        <span className="aw-convbar-agent">New conversation</span>
        {/* The project the unsent message will act on, repeated at the decision point so it
            cannot look detached from it. */}
        <span
          className="aw-chip"
          data-testid="new-conversation-project-context"
          style={{ background: 'var(--surface-2)', borderColor: 'var(--border)', color: 'var(--text-2)' }}
        >
          <Icon name="folder_open" size={13} />
          Project: {projectName ?? projectId}
        </span>
        <div className="aw-convbar-end">
          {onBackToProject && (
            <Button variant="ghost" size="icon-xs" onClick={onBackToProject} aria-label="Back to project" title="Back to project">
              <Icon name="arrow_left" size={15} />
            </Button>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto" data-testid="new-conversation-surface">
        {agentRow ? (
          <NewConversationIntro
            agent={agentRow}
            runnerLabel={runnerRow?.name ?? null}
            modelLabel={modelLabel}
            postureLabel={postureLabel}
            starters={STARTERS}
            headlineTestId="new-conversation-headline"
            onPick={(message) => {
              if (!agent) return
              setComposerDraft(projectId, agent, null, message)
              setComposerKey((key) => key + 1)
            }}
          />
        ) : (
          <div className="aw-newconv">
            <span className="new-conversation-icon" aria-hidden="true">
              <Icon name="chat" size={20} />
            </span>
            {/* Unbound, the line is the question that has to be answered first, not decoration. */}
            <h2 className="aw-newconv-title" data-testid="new-conversation-headline">
              {agent ? `New conversation with ${agent}` : 'Who should work on this?'}
            </h2>
          </div>
        )}
        {agentChooser}
      </div>

      <ConversationComposerDock
        selected={[]}
        onToggleOption={() => undefined}
        composer={{
          key: composerKey,
          agent: agent ?? 'an agent',
          projectId,
          conversationId: null,
          isRunning: false,
          onSubmit: handleSubmit,
          placeholder: agent ? undefined : 'Choose an agent, then write your first message…',
          disabledReason: agent ? undefined : 'Choose an agent to start',
          workspacePaths,
          runner: runnerRow?.cli ?? null,
          effectiveModel: runnerRow?.model ?? null,
          modelIsRunners: runnerSetsModel(runnerRow),
          effectiveControls: posture,
          pendingOverrides,
          onPendingOverridesChange: setPendingOverrides,
          specDocumentLabel: null,
          specArmed: exploring,
          onOpenSpecPicker: () => setExploring(true),
          onStartExploration: () => setExploring(true),
          onStopExploring: () => setExploring(false),
        }}
      >
        {error && (
          <span role="alert" className="text-center text-[11px]" style={{ color: 'var(--red)' }}>
            {error}
          </span>
        )}
      </ConversationComposerDock>
    </div>
  )
}
