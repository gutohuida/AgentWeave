import * as React from 'react'
import { createPortal } from 'react-dom'
import { useAgents } from '@/api/agents'
import { readableApiError } from '@/api/client'
import { useNameChecker, type Stall } from '@/api/stalls'
import { useTask } from '@/api/tasks'
import { Icon } from '@/components/common/Icon'
import { TaskDetailDrawer } from '@/components/tasks/TaskDetailDrawer'
import { Button } from '@/components/ui/button'
import { stallNotice } from '@/lib/stalls'
import '@/styles/stalls.css'

/** A stall's remedies as controls (`a-two-profile-build-cannot-deadlock-and-a-stall-says-so`, D5,
 *  FR-8). One component, drawn beside the notice on the build page header, the Overview's notice
 *  and the task's board card, so the same controls sit in the same place on every screen (P2).
 *  The remedies are the Hub's (`stall.remedies`, derived from the cause), so the notice's words and
 *  the controls cannot drift. Each acts in place: naming a checker is answered here, and the
 *  operator's review opens the task over the page rather than going to it. */

/** The Hub's own agent for stalled work (`hub/hub/stalls.py`, `MENDER`); it checks nothing. */
const MENDER = 'mender'

export interface StallRemediesProps {
  stall: Stall
  /** The task's readable reference ("AW-164"), for the controls' accessible names (P24). */
  taskRef?: string | null
  /** Tighter, for the board card. */
  compact?: boolean
}

/** Nothing when the stall offers no remedy: an older Hub's stall, or a cause with none. */
export function StallRemedies(props: StallRemediesProps) {
  if (!props.stall.task_id || !props.stall.remedies?.length) return null
  return <StallRemedyControls {...props} />
}

function StallRemedyControls({ stall, taskRef, compact }: StallRemediesProps) {
  const taskId = stall.task_id!
  const remedies = stall.remedies ?? []
  const { data: task, error: taskError } = useTask(taskId)
  const { data: agents = [], error: agentsError } = useAgents()
  const nameChecker = useNameChecker()
  const [picking, setPicking] = React.useState(false)
  const [reviewing, setReviewing] = React.useState(false)
  const [refusal, setRefusal] = React.useState<string | null>(null)
  const [done, setDone] = React.useState<string | null>(null)
  const ref = taskRef || task?.readable_id || 'this task'
  const builder = task?.builder ?? null
  // Anyone open but the mender, the task's builder (a builder never checks its own work) and the
  // checker the stall is about. One without a runner is listed and disabled, saying so.
  const candidates = agents.filter(
    (a) => a.name !== MENDER && a.name !== builder && a.name !== task?.checker && !a.folded_into,
  )
  const pickerId = `stall-checker-picker-${stall.id}`
  return (
    <div className="aw-stall-remedies" data-compact={compact ? 'true' : undefined} data-testid={`stall-remedies-${stall.id}`}>
      <div className="aw-stall-remedy-row" role="group" aria-label={`Remedies for ${ref}`}>
        {remedies.includes('name_checker') ? (
          <Button
            variant="outline"
            size="xs"
            aria-label={`Name a different checker for ${ref}`}
            aria-expanded={picking}
            aria-controls={picking ? pickerId : undefined}
            onClick={() => {
              setRefusal(null)
              setDone(null)
              setPicking((open) => !open)
            }}
          >
            <Icon name="person_add" size={13} />
            Name a different checker
          </Button>
        ) : null}
        {remedies.includes('review_yourself') ? (
          <Button
            variant="outline"
            size="xs"
            aria-label={`Review ${ref} yourself`}
            onClick={() => {
              setDone(null)
              if (task) {
                setRefusal(null)
                setReviewing(true)
              } else {
                setRefusal(
                  taskError
                    ? readableApiError(taskError, `Couldn’t read ${ref} from the Hub, so its review cannot open here.`)
                    : `${ref} is still being read. Try again in a moment.`,
                )
              }
            }}
          >
            <Icon name="fact_check" size={13} />
            Review it yourself
          </Button>
        ) : null}
      </div>
      {picking ? (
        <div id={pickerId} className="aw-stall-picker" role="group" aria-label={`Who checks ${ref} instead`}>
          <span className="aw-stall-picker-label">Who checks it instead?</span>
          {agentsError ? (
            <span className="aw-stall-picker-note" role="alert">
              Couldn’t read the profiles from the Hub, so nobody can be offered here.
            </span>
          ) : candidates.length ? (
            candidates.map((agent) => {
              const noRunner = !agent.runner_id
              return (
                <Button
                  key={agent.name}
                  variant="ghost"
                  size="xs"
                  disabled={noRunner || nameChecker.isPending}
                  title={noRunner ? `${agent.name} has no runner bound, so it cannot check anything` : undefined}
                  aria-label={`Make ${agent.name} the checker of ${ref}`}
                  onClick={() =>
                    nameChecker.mutate(
                      { taskId, agent: agent.name, taskRef: ref },
                      {
                        onSuccess: (answer) => {
                          // Said here while the stall still shows; the hook's toast says it after.
                          setPicking(false)
                          setDone(stallNotice(answer.next_turn ?? `${agent.name} checks it now.`, ref))
                        },
                        onError: (error) => setRefusal(readableApiError(error, 'The Hub did not name that checker.')),
                      },
                    )
                  }
                >
                  {agent.name}
                  {noRunner ? <span className="aw-stall-picker-note">no runner</span> : null}
                </Button>
              )
            })
          ) : (
            <span className="aw-stall-picker-note">No other profile can check it. Add one, or review it yourself.</span>
          )}
        </div>
      ) : null}
      {refusal ? (
        <p className="aw-stall-refusal" role="alert">
          <Icon name="alert_triangle" size={13} />
          {refusal}
        </p>
      ) : null}
      {done ? (
        <p className="aw-stall-done" role="status">
          <Icon name="check_circle" size={13} />
          {done}
        </p>
      ) : null}
      {/* The operator's review is the task's own: Land it, on the task, reviews and approves it.
          Opened over the page, in a portal so a card's layout cannot clip or move it. */}
      {reviewing && task
        ? createPortal(<TaskDetailDrawer task={task} initialView="details" onClose={() => setReviewing(false)} />, document.body)
        : null}
    </div>
  )
}
