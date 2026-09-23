import { useAgents, useArchiveAgent } from '@/api/agents'
import { readableApiError } from '@/api/client'
import { Button } from '@/components/ui/button'

/**
 * What opening a conversation shows when its agent is not on the open roster (F193).
 *
 * It used to be two words, "Agent unavailable.", with no name, no reason and no remedy — while
 * the reason was knowable and the remedy one request away. Archiving an agent keeps its
 * conversations (the operator's decision, D10, 2026-09-23: shown, marked, with Unarchive), so the
 * common case is an archived agent, and this says so and offers to unarchive it. Unarchiving puts
 * the agent back on the roster, and the conversation then opens as it always did.
 */
export function ArchivedAgentNotice({ agentName }: { agentName: string }) {
  // `all`: an archived agent is absent from the default roster by definition.
  const { data: roster, error, isLoading } = useAgents('all')
  const unarchive = useArchiveAgent()
  const agent = roster?.find((candidate) => candidate.name === agentName)

  let body: React.ReactNode
  if (isLoading) {
    body = <p>Looking up {agentName}…</p>
  } else if (error && !roster) {
    body = <p>Could not read the roster, so it is not known why {agentName} is unavailable.</p>
  } else if (agent?.lifecycle === 'archived') {
    body = (
      <>
        <p>
          <strong style={{ color: 'var(--text)' }}>{agentName} is archived.</strong> Its
          conversations are kept. Unarchive it to read and continue this one.
        </p>
        <Button
          className="mt-3"
          variant="outline"
          size="sm"
          data-testid="archived-agent-unarchive"
          disabled={unarchive.isPending}
          onClick={() => unarchive.mutate({ agent: agentName, archived: false })}
        >
          {unarchive.isPending ? 'Unarchiving…' : `Unarchive ${agentName}`}
        </Button>
        {unarchive.error && (
          <p role="alert" className="mt-2" style={{ color: 'var(--amber)' }}>
            {readableApiError(unarchive.error, `Could not unarchive ${agentName}.`)}
          </p>
        )}
      </>
    )
  } else {
    body = <p>{agentName} is not on this project&apos;s roster.</p>
  }

  return (
    <div
      className="flex h-full flex-col items-center justify-center px-6 text-center text-sm"
      style={{ color: 'var(--text-3)' }}
      data-testid="archived-agent-notice"
    >
      {body}
    </div>
  )
}
