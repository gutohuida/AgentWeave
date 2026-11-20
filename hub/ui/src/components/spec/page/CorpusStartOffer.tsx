import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { readableApiError } from '@/api/client'
import { orderStarts, useStartCorpus, type CorpusStartKind, type CorpusState } from '@/api/corpusStart'
import { agentDestination, goTo } from '@/lib/navigation'
import { toast } from '@/lib/toast'
import '@/styles/corpus-start.css'

/**
 * The start offered to a project with no specs (`a-project-with-no-specs-is-offered-a-start`,
 * FR-2, FR-4, FR-5): both starts, the recommended one first and marked; taking one asks which open
 * agent does it, preselecting the Hub's choice; confirming creates the document and opens the
 * agent's new conversation. With no open agent there is no start to take, only a way to add one.
 */

const STARTS: Record<CorpusStartKind, { title: string; detail: string; icon: string }> = {
  'existing-code': {
    title: 'Write down what the existing code does',
    detail:
      'A profile reads the code and writes a system map: its areas and the capabilities it proposes, with one capability draft each. You review every draft; only approving and folding one makes it a capability.',
    icon: 'file_code',
  },
  greenfield: {
    title: 'Plan a new project',
    detail:
      'A profile interviews you about the problem, its users, the scope and the non-goals, then writes a roadmap of slices.',
    icon: 'route',
  },
}

export function CorpusStartOffer({
  projectId,
  state,
  onAddAgent,
}: {
  projectId: string
  state: CorpusState
  onAddAgent?: () => void
}) {
  const [taking, setTaking] = useState<CorpusStartKind | null>(null)
  const [agent, setAgent] = useState<string>(state.preselected_agent ?? '')
  const startCorpus = useStartCorpus()
  const hasAgent = state.agents.length > 0

  const take = (start: CorpusStartKind) => {
    setTaking(start)
    setAgent(state.preselected_agent ?? state.agents[0]?.name ?? '')
  }
  const confirm = () => {
    if (!taking || !agent) return
    /* Awaited, not `mutate`'s callbacks: the new document can reach the list (a live event) before
     * the start answers, which unmounts this offer, and an unmounted observer's callbacks never run. */
    startCorpus
      .mutateAsync({ start: taking, agent })
      .then((result) => goTo(agentDestination(projectId, result.agent, result.conversation_id, result.document.path)))
      .catch((error) => toast({ title: 'The start was refused', description: readableApiError(error, 'The Hub refused the start.'), tone: 'error' }))
  }

  return (
    <section className="aw-corpus-start" data-testid="corpus-start-offer" aria-labelledby="corpus-start-title">
      <header className="aw-corpus-start-head">
        <h2 id="corpus-start-title" className="aw-corpus-start-title">Start your specifications</h2>
        <p className="aw-corpus-start-lede">
          This project has no specification documents yet. A profile can write down what its code does, or interview you to plan it.
        </p>
      </header>
      {hasAgent ? null : (
        <p className="aw-corpus-start-noagent">
          This project has no profile to do it.{' '}
          <button type="button" data-slot="link" className="aw-link aw-link-inline" data-testid="corpus-start-add-agent" onClick={() => onAddAgent?.()}>
            Add a profile
          </button>{' '}
          and the starts become available here.
        </p>
      )}
      <ul className="aw-corpus-start-options">
        {orderStarts(state.starts, state.recommended).map((start) => {
          const recommended = start === state.recommended
          const open = taking === start
          return (
            <li
              key={start}
              className="aw-corpus-start-option"
              data-testid="corpus-start-option"
              data-start={start}
              data-recommended={recommended ? 'true' : 'false'}
              data-open={open ? 'true' : 'false'}
            >
              <span className="aw-corpus-start-icon" aria-hidden="true">
                <Icon name={STARTS[start].icon} size={16} />
              </span>
              <div className="aw-corpus-start-body">
                <p className="aw-corpus-start-option-title">
                  {STARTS[start].title}
                  {recommended ? <span className="aw-corpus-start-badge">Recommended</span> : null}
                </p>
                <p className="aw-corpus-start-option-detail">{STARTS[start].detail}</p>
                {open ? (
                  <div className="aw-corpus-start-pick">
                    <label className="aw-corpus-start-pick-label" htmlFor={`corpus-start-agent-${start}`}>
                      Which profile does it?
                    </label>
                    <select
                      id={`corpus-start-agent-${start}`}
                      className="aw-corpus-start-select"
                      data-testid="corpus-start-agent"
                      value={agent}
                      onChange={(e) => setAgent(e.target.value)}
                    >
                      {state.agents.map((a) => (
                        <option key={a.name} value={a.name} data-testid="corpus-start-agent-option" data-agent={a.name}>
                          {a.charter ? `${a.name} (${a.charter})` : a.name}
                        </option>
                      ))}
                    </select>
                    <Button variant="primary" size="sm" data-testid="corpus-start-confirm" disabled={!agent || startCorpus.isPending} onClick={confirm}>
                      {startCorpus.isPending ? 'Starting…' : `Start with ${agent}`}
                    </Button>
                    <Button variant="ghost" size="sm" disabled={startCorpus.isPending} onClick={() => setTaking(null)}>
                      Cancel
                    </Button>
                  </div>
                ) : null}
              </div>
              {hasAgent && !open ? (
                <span className="aw-corpus-start-actions">
                  <Button variant={recommended ? 'primary' : 'outline'} size="sm" data-testid="corpus-start-take" onClick={() => take(start)}>
                    Start…
                  </Button>
                </span>
              ) : null}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
