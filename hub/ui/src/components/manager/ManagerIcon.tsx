import { Icon } from '@/components/common/Icon'
import type { ManagerIconState } from './useManagerItem'
import '@/styles/manager.css'

const LABEL: Record<ManagerIconState, string> = {
  idle: 'The manager is not working on this',
  working: 'The manager is working on this',
  failed: 'The manager’s last run on this failed',
}

/**
 * The manager's robot on the item it works on (`background-manager-work-you-can-see`, FR-4):
 * idle, a quiet robot; working, a robot with a green light that blinks; failed, a red blink and
 * then a "dead" robot that stays until the failure is seen. The state is also in its accessible
 * name and `data-state`, never in colour alone.
 *
 * `detail` titles it (a failure's reason, or the run in progress). With `onOpen`, the icon is a
 * button: the placement's way to open the failure in place.
 */
export function ManagerIcon({
  state,
  job,
  detail,
  size = 15,
  onOpen,
}: {
  state: ManagerIconState
  job: string
  detail?: string | null
  size?: number
  onOpen?: () => void
}) {
  const label = detail ? `${LABEL[state]}: ${detail}` : LABEL[state]
  const body = (
    <>
      <Icon name={state === 'failed' ? 'smart_toy_off' : 'smart_toy'} size={size} />
      {state !== 'idle' ? <span className="aw-manager-icon-light" aria-hidden="true" /> : null}
    </>
  )
  const common = {
    'data-testid': 'manager-icon',
    'data-state': state,
    'data-job': job,
    className: 'aw-manager-icon',
    title: label,
  }
  return onOpen ? (
    <button type="button" {...common} aria-label={label} onClick={onOpen}>
      {body}
    </button>
  ) : (
    <span {...common} role="img" aria-label={label}>
      {body}
    </span>
  )
}
