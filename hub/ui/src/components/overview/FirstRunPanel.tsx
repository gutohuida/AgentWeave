import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import '@/styles/setup.css'

/**
 * What to do first in a project with no work yet: the path, and its next step as a button. Shown at
 * the top of Overview while the project has no agent, or no task or specification; it goes once
 * there is work. Presentational: `OverviewScreen` says which agent can be asked.
 */

export const QUICKSTART_URL = 'https://gutohuida.github.io/AgentWeave/getting-started/quickstart/'

const PATH = ['Add an agent', 'Ask for a change', 'Approve its spec', 'Build', 'Review and merge']

export function FirstRunPanel({
  agent,
  onAddAgent,
  onAskForChange,
}: {
  /** The first agent that can be asked; null while the project has none. */
  agent: string | null
  onAddAgent?: () => void
  onAskForChange?: (agent: string) => void
}) {
  const current = agent ? 1 : 0
  return (
    <section className="aw-setup aw-firstrun" aria-label="Getting started" data-testid="first-run-panel">
      <header className="aw-setup-head">
        <h2 className="aw-setup-title">Welcome. Here is how work gets done in a project</h2>
      </header>
      <ol className="aw-firstrun-path">
        {PATH.map((step, index) => (
          <li key={step} data-state={index < current ? 'done' : index === current ? 'next' : 'later'}>
            {step}
          </li>
        ))}
      </ol>
      <div className="aw-firstrun-actions">
        {agent ? (
          <Button variant="primary" size="sm" onClick={() => onAskForChange?.(agent)}>
            Ask {agent} for a change
          </Button>
        ) : (
          <Button variant="primary" size="sm" onClick={onAddAgent}>
            Add an agent
          </Button>
        )}
        <a className="aw-link aw-link-inline" href={QUICKSTART_URL} target="_blank" rel="noreferrer">
          Read the quickstart <Icon name="arrow_forward" size={12} />
        </a>
      </div>
    </section>
  )
}
