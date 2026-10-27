import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/common/Icon'
import { useDialogFocus } from '@/hooks/useDialogFocus'
import { describeCron } from '@/lib/cron'
import type { SpecRecommendedBuild } from '@/api/spec'

/** "No flow" as a select value (an option cannot carry `''`); sent to the Hub as `''`. */
const NO_FLOW = '__no_flow__'

/**
 * Build, or Approve and build (`exploring-ends-at-an-approved-plan`, FR-6, FR-7, FR-10). Opens with
 * the build the document recommends filled in, each choice beside the reason its author gave; the
 * operator decides. In this slice the one choice the operator can change is the flow's agent (or no
 * flow at all): the rest of the build is what the document recommends. A later slice adds the
 * build's driver, level and people.
 *
 * `onConfirm` receives the agent to send as `delivery_agent`: undefined when the operator kept the
 * recommendation, an agent's name when they chose another, `''` for no flow.
 */
export function BuildDialog({
  title,
  approve,
  recommended,
  openAgents,
  isPending,
  error,
  onCancel,
  onConfirm,
}: {
  title: string
  /** Approve and build (true) or Build an approved document (false). */
  approve: boolean
  recommended: SpecRecommendedBuild | undefined
  openAgents: string[]
  isPending: boolean
  error: string | null
  onCancel: () => void
  onConfirm: (deliveryAgent: string | undefined) => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  useDialogFocus(true, panelRef, onCancel)
  const flow = recommended?.mode === 'flow'
  const recommendedAgent = recommended?.agent ?? ''
  const usable = recommendedAgent && openAgents.includes(recommendedAgent) ? recommendedAgent : ''
  const [agent, setAgent] = useState(usable)
  const reasons = recommended?.reasons ?? {}

  function confirm() {
    if (!flow) return onConfirm(undefined)
    const chosen = agent === NO_FLOW ? '' : agent
    onConfirm(chosen === recommendedAgent ? undefined : chosen)
  }

  const label = 'mb-1 block text-[11px] font-medium'
  const field: React.CSSProperties = { padding: '8px 12px', width: '100%', fontSize: 13 }
  const why = (key: keyof SpecRecommendedBuild['reasons'], testId: string) =>
    reasons[key] ? (
      <p className="mt-1 text-xs" data-testid={testId} style={{ color: 'var(--text-3)' }}>
        {reasons[key]}
      </p>
    ) : null
  const verb = approve ? 'Approve and build' : 'Build'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'var(--scrim)' }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="build-dialog-title"
      data-testid="build-dialog"
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        className="lifted-surface max-h-[90vh] w-full max-w-md overflow-y-auto p-5"
        style={{ background: 'var(--surface)' }}
      >
        <h2 id="build-dialog-title" className="text-sm font-semibold">
          {verb} “{title}”
        </h2>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>
          {approve
            ? 'Approves the version you read and starts building it, as the document recommends.'
            : 'Starts building it as the document recommends. Its tasks are already on the board.'}
        </p>

        <div className="mt-4 space-y-3 text-xs">
          {!recommended ? (
            <p data-testid="build-no-recommendation">
              The document recommends no build: its tasks stay on the board, started by hand.
            </p>
          ) : !flow ? (
            <div>
              <p data-testid="build-mode">No flow: the tasks stay on the board, started by hand.</p>
              {why('mode', 'build-reason-mode')}
            </div>
          ) : (
            <>
              <div>
                <p data-testid="build-mode">A flow works the tasks as their prerequisites clear.</p>
                {why('mode', 'build-reason-mode')}
              </div>
              <div>
                <label className={label} style={{ color: 'var(--text-3)' }} htmlFor="build-agent">
                  Agent
                </label>
                <div className="control-select-wrap">
                  <select
                    id="build-agent"
                    data-testid="build-agent"
                    data-dialog-initial-focus
                    className="control-field"
                    style={field}
                    value={agent}
                    onChange={(event) => setAgent(event.target.value)}
                    disabled={isPending}
                  >
                    <option value="">Select an agent…</option>
                    {openAgents.map((name) => (
                      <option key={name} value={name}>
                        @{name}
                      </option>
                    ))}
                    <option value={NO_FLOW}>No flow</option>
                  </select>
                  <Icon name="expand_more" size={15} className="control-select-icon" />
                </div>
                {recommendedAgent && !usable ? (
                  <p className="mt-1" style={{ color: 'var(--amber)' }} data-testid="build-agent-stale">
                    The document recommends @{recommendedAgent}, which is not an open agent here.
                  </p>
                ) : null}
                {why('agent', 'build-reason-agent')}
              </div>
              <div>
                <span className={label} style={{ color: 'var(--text-3)' }}>
                  Reviewer
                </span>
                <p data-testid="build-reviewer">
                  {recommended.reviewer ? `@${recommended.reviewer}` : 'Any free agent'}
                </p>
                {why('reviewer', 'build-reason-reviewer')}
              </div>
              {recommended.tester !== null ? (
                <div>
                  <span className={label} style={{ color: 'var(--text-3)' }}>
                    Tester
                  </span>
                  <p data-testid="build-tester">
                    {recommended.tester === false ? 'No testing, review only' : `@${recommended.tester}`}
                  </p>
                  {why('tester', 'build-reason-tester')}
                </div>
              ) : null}
              <div>
                <span className={label} style={{ color: 'var(--text-3)' }}>
                  Stops
                </span>
                <p data-testid="build-stop">
                  {[
                    recommended.stop_when_queue_empties ? 'when its queue empties' : null,
                    recommended.stop_at ? `at ${recommended.stop_at}` : null,
                  ]
                    .filter(Boolean)
                    .join(', or ') || 'never: the Hub will not start a flow with no stop'}
                </p>
                {why('stop', 'build-reason-stop')}
              </div>
              <div>
                <span className={label} style={{ color: 'var(--text-3)' }}>
                  Fires
                </span>
                <p data-testid="build-cron">
                  <code>{recommended.cron}</code>
                  {describeCron(recommended.cron) ? ` (${describeCron(recommended.cron)})` : ''}
                </p>
                {why('cron', 'build-reason-cron')}
              </div>
            </>
          )}

          {error && (
            <p role="alert" style={{ color: 'var(--amber)' }} data-testid="build-error">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" size="sm" onClick={onCancel} disabled={isPending}>
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              data-testid="build-confirm"
              disabled={isPending || (flow && agent === '')}
              title={flow && agent === '' ? 'Choose the agent that works the flow, or No flow' : undefined}
              onClick={confirm}
            >
              {isPending ? `${verb}…` : verb}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
