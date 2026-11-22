import { Icon } from '@/components/common/Icon'
import '@/styles/setup.css'
import { QUICKSTART_URL } from './setupItems'

/**
 * The first-run path, as one quiet line inside the set-up card (`SetupList`) while the project has
 * no work yet, and the quickstart link that stays once that card has gone. Presentational: the
 * container says which step the project is at.
 */

const FIRST_RUN_PATH = ['Add a profile', 'Ask for a change', 'Approve its spec', 'Build', 'Review and merge']

export function FirstRunPath({ current }: { /** The index of the step the project is at. */ current: number }) {
  return (
    <ol className="aw-firstrun-path" aria-label="How work gets done in a project" data-testid="first-run-path">
      {FIRST_RUN_PATH.map((step, index) => (
        <li
          key={step}
          data-state={index < current ? 'done' : index === current ? 'next' : 'later'}
          aria-current={index === current ? 'step' : undefined}
        >
          {step}
        </li>
      ))}
    </ol>
  )
}

export function QuickstartLink() {
  return (
    <p className="aw-quickstart" data-testid="quickstart-link">
      <a className="aw-link aw-link-inline" href={QUICKSTART_URL} target="_blank" rel="noreferrer">
        Read the quickstart <Icon name="arrow_forward" size={12} />
      </a>
    </p>
  )
}
