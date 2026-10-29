import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/common/Icon'
import { useDialogFocus } from '@/hooks/useDialogFocus'
import { describeCron } from '@/lib/cron'
import type {
  BuildChoices,
  BuildDriver,
  BuildLanding,
  BuildLevel,
  SpecRecommendedBuild,
} from '@/api/spec'

/** "No flow" as a select value (an option cannot carry `''`); sent to the Hub as `''`. */
const NO_FLOW = '__no_flow__'

const DRIVERS: Array<{ value: BuildDriver; label: string; detail: string }> = [
  { value: 'flow', label: 'Flow', detail: 'The Hub hands out the work as prerequisites clear.' },
  { value: 'lead', label: 'Lead', detail: 'A lead agent hands out the work and is briefed as it moves.' },
  { value: 'hand', label: 'By hand', detail: 'Nothing is started: the tasks wait on the board.' },
]

const LEVELS: Array<{ value: BuildLevel; label: string; detail: string }> = [
  { value: 'fast', label: 'Fast', detail: 'The builder or the lead approves; no checker.' },
  { value: 'reviewed', label: 'Reviewed', detail: 'Anyone but the builder approves; gaps are reported.' },
  { value: 'gated', label: 'Gated', detail: 'Approval waits for accepted evidence per requirement.' },
]

/**
 * Build, or Approve and build (`exploring-ends-at-an-approved-plan`, FR-6, FR-7, FR-10), with the
 * build's settings (`a-build-has-a-driver-a-level-and-its-people`, FR-1, FR-3): who drives it, at
 * which level, with which builders, checker and lead, within which cap and window, landing where,
 * and each task's builder and checker. Opens with the build the document recommends filled in, each choice
 * beside the reason its author gave; the operator decides.
 *
 * `onConfirm` receives exactly the settings shown. `delivery_agent` is sent only when the operator
 * chose another agent for the flow than the recommendation (`''` for no flow).
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
  onConfirm: (choices: BuildChoices) => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  useDialogFocus(true, panelRef, onCancel)
  const flowRecommended = recommended?.mode === 'flow'
  const recommendedAgent = recommended?.agent ?? ''
  const usable = recommendedAgent && openAgents.includes(recommendedAgent) ? recommendedAgent : ''
  const [agent, setAgent] = useState(usable)
  const [driver, setDriver] = useState<BuildDriver>(
    recommended?.driver ?? (flowRecommended ? 'flow' : 'hand'),
  )
  const [level, setLevel] = useState<BuildLevel>(recommended?.level ?? 'reviewed')
  const [builders, setBuilders] = useState<string[]>(recommended?.builders ?? [])
  const [builder, setBuilder] = useState<string>(recommended?.builder ?? '')
  const [checker, setChecker] = useState<string>(recommended?.checker ?? '')
  const [lead, setLead] = useState<string>(recommended?.lead ?? '')
  const [cap, setCap] = useState<string>(
    recommended?.budget_cap_usd != null ? String(recommended.budget_cap_usd) : '',
  )
  const [windowEnd, setWindowEnd] = useState('')
  const [landing, setLanding] = useState<BuildLanding>(recommended?.landing ?? 'main')
  const [taskBuilders, setTaskBuilders] = useState<Record<string, string>>(
    Object.fromEntries(
      Object.entries(recommended?.task_builders ?? {}).map(([key, name]) => [key, name ?? '']),
    ),
  )
  const [taskCheckers, setTaskCheckers] = useState<Record<string, string>>(
    Object.fromEntries(
      Object.entries(recommended?.task_checkers ?? {}).map(([key, name]) => [key, name ?? '']),
    ),
  )
  const reasons = recommended?.reasons ?? {}

  const flowAgentShown = driver === 'flow' && flowRecommended
  const capValue = cap.trim() === '' ? undefined : Number(cap)
  const capInvalid = capValue !== undefined && !(Number.isFinite(capValue) && capValue > 0)
  const leadMissing = driver === 'lead' && !lead
  const agentMissing = flowAgentShown && agent === '' && builders.length === 0

  function confirm() {
    const noFlow = flowAgentShown && agent === NO_FLOW
    const choices: BuildChoices = {
      driver: noFlow ? 'hand' : driver,
      level,
      builders,
      builder,
      checker,
      landing,
      task_builders: taskBuilders,
      task_checkers: taskCheckers,
    }
    if (driver === 'lead') choices.lead = lead
    if (capValue !== undefined) choices.budget_cap_usd = capValue
    // Wall-clock time the operator typed into a `datetime-local` input, not a Hub timestamp.
    if (windowEnd) choices.window_end = new Date(windowEnd).toISOString()
    if (flowAgentShown) {
      const chosen = noFlow ? '' : agent
      if (chosen !== recommendedAgent && !(chosen === '' && !noFlow)) choices.delivery_agent = chosen
    }
    onConfirm(choices)
  }

  function toggle(list: string[], name: string, set: (next: string[]) => void) {
    set(list.includes(name) ? list.filter((entry) => entry !== name) : [...list, name])
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
  const taskKeys = Array.from(new Set([...Object.keys(taskBuilders), ...Object.keys(taskCheckers)]))

  /** A person the document names who is no open agent stays selected and says so, so what is shown
   *  is what is sent. */
  const personOptions = (current: string, blank: string) => [
    <option key="" value="">
      {blank}
    </option>,
    ...(current && !openAgents.includes(current)
      ? [
          <option key={current} value={current}>
            @{current} (not an open agent)
          </option>,
        ]
      : []),
    ...openAgents.map((name) => (
      <option key={name} value={name}>
        @{name}
      </option>
    )),
  ]
  const personSelect = (
    testId: string,
    value: string,
    onChange: (value: string) => void,
    blank: string,
    style: React.CSSProperties = field,
  ) => (
    <select
      data-testid={testId}
      className="control-field"
      style={style}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      disabled={isPending}
    >
      {personOptions(value, blank)}
    </select>
  )

  const select = (
    id: string,
    value: string,
    onChange: (value: string) => void,
    options: Array<{ value: string; label: string }>,
  ) => (
    <div className="control-select-wrap">
      <select
        id={id}
        data-testid={id}
        className="control-field"
        style={field}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={isPending}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <Icon name="expand_more" size={15} className="control-select-icon" />
    </div>
  )

  const people = (testId: string, chosen: string[], set: (next: string[]) => void) => (
    <div className="flex flex-wrap gap-x-3 gap-y-1" data-testid={testId}>
      {openAgents.length === 0 ? (
        <span style={{ color: 'var(--text-3)' }}>No open agents</span>
      ) : (
        openAgents.map((name) => (
          <label key={name} className="flex items-center gap-1">
            <input
              type="checkbox"
              data-testid={`${testId}-${name}`}
              checked={chosen.includes(name)}
              onChange={() => toggle(chosen, name, set)}
              disabled={isPending}
            />
            @{name}
          </label>
        ))
      )}
    </div>
  )

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
            ? 'Approves the version you read and starts building it with the settings below.'
            : 'Starts building it with the settings below. Its tasks are already on the board.'}
        </p>

        <div className="mt-4 space-y-3 text-xs">
          {!recommended ? (
            <p data-testid="build-no-recommendation">
              The document recommends no build: choose how it is built below.
            </p>
          ) : (
            <div>
              <p data-testid="build-mode">
                {flowRecommended
                  ? 'The document recommends a flow that works the tasks as their prerequisites clear.'
                  : 'The document recommends no flow: the tasks stay on the board, started by hand.'}
              </p>
              {why('mode', 'build-reason-mode')}
            </div>
          )}

          <div>
            <label className={label} style={{ color: 'var(--text-3)' }} htmlFor="build-driver">
              Driver
            </label>
            {select(
              'build-driver',
              driver,
              (value) => setDriver(value as BuildDriver),
              DRIVERS.map((entry) => ({ value: entry.value, label: entry.label })),
            )}
            <p className="mt-1" style={{ color: 'var(--text-3)' }}>
              {DRIVERS.find((entry) => entry.value === driver)?.detail}
            </p>
            {why('driver', 'build-reason-driver')}
          </div>

          {flowAgentShown ? (
            <div>
              <label className={label} style={{ color: 'var(--text-3)' }} htmlFor="build-agent">
                Flow agent
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
                  <option value="">{builders.length ? 'The first builder' : 'Select an agent…'}</option>
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
          ) : null}

          {driver === 'lead' ? (
            <div>
              <label className={label} style={{ color: 'var(--text-3)' }} htmlFor="build-lead">
                Lead
              </label>
              {select('build-lead', lead, setLead, [
                { value: '', label: 'Select the lead…' },
                ...openAgents.map((name) => ({ value: name, label: `@${name}` })),
              ])}
              {why('lead', 'build-reason-lead')}
            </div>
          ) : null}

          <div>
            <label className={label} style={{ color: 'var(--text-3)' }} htmlFor="build-level">
              Level
            </label>
            {select(
              'build-level',
              level,
              (value) => setLevel(value as BuildLevel),
              LEVELS.map((entry) => ({ value: entry.value, label: entry.label })),
            )}
            <p className="mt-1" style={{ color: 'var(--text-3)' }}>
              {LEVELS.find((entry) => entry.value === level)?.detail} Checks hold at every level.
            </p>
            {why('level', 'build-reason-level')}
          </div>

          <div>
            <span className={label} style={{ color: 'var(--text-3)' }}>
              Builders {builders.length ? '' : '(none chosen: any free agent)'}
            </span>
            {people('build-builders', builders, setBuilders)}
            {why('builders', 'build-reason-builders')}
          </div>

          <div>
            <span className={label} style={{ color: 'var(--text-3)' }}>
              Default builder
            </span>
            {personSelect('build-builder', builder, setBuilder, 'The first builder')}
          </div>

          <div>
            <span className={label} style={{ color: 'var(--text-3)' }}>
              Default checker
            </span>
            {personSelect('build-checker', checker, setChecker, 'Any free agent but the builder')}
            {why(reasons.checker ? 'checker' : 'reviewer', 'build-reason-checker')}
          </div>

          {taskKeys.length ? (
            <div>
              <span className={label} style={{ color: 'var(--text-3)' }}>
                Each task's builder and checker
              </span>
              <div className="space-y-1" data-testid="build-task-people">
                {taskKeys.map((key) => (
                  <div key={key} className="flex items-center gap-2">
                    <code className="w-24 shrink-0 truncate">{key}</code>
                    {personSelect(
                      `build-task-builder-${key}`,
                      taskBuilders[key] ?? '',
                      (value) => setTaskBuilders({ ...taskBuilders, [key]: value }),
                      'Default builder',
                      { ...field, padding: '4px 8px' },
                    )}
                    {personSelect(
                      `build-task-checker-${key}`,
                      taskCheckers[key] ?? '',
                      (value) => setTaskCheckers({ ...taskCheckers, [key]: value }),
                      'Default checker',
                      { ...field, padding: '4px 8px' },
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={label} style={{ color: 'var(--text-3)' }} htmlFor="build-cap">
                Budget cap (US$)
              </label>
              <input
                id="build-cap"
                data-testid="build-cap"
                className="control-field"
                style={field}
                inputMode="decimal"
                placeholder="No cap"
                value={cap}
                disabled={isPending}
                onChange={(event) => setCap(event.target.value)}
              />
              {why('cap', 'build-reason-cap')}
            </div>
            <div>
              <label className={label} style={{ color: 'var(--text-3)' }} htmlFor="build-window-end">
                Window ends
              </label>
              <input
                id="build-window-end"
                data-testid="build-window-end"
                type="datetime-local"
                className="control-field"
                style={field}
                value={windowEnd}
                disabled={isPending}
                onChange={(event) => setWindowEnd(event.target.value)}
              />
            </div>
          </div>

          <div>
            <label className={label} style={{ color: 'var(--text-3)' }} htmlFor="build-landing">
              Lands on
            </label>
            {select('build-landing', landing, (value) => setLanding(value as BuildLanding), [
              { value: 'main', label: 'The main branch' },
              { value: 'nowhere', label: 'Nowhere (approved, nothing merged)' },
            ])}
            {why('landing', 'build-reason-landing')}
          </div>

          {flowRecommended && driver === 'flow' && recommended ? (
            <div>
              <span className={label} style={{ color: 'var(--text-3)' }}>
                Flow
              </span>
              <p data-testid="build-stop">
                Stops{' '}
                {[
                  recommended.stop_when_queue_empties ? 'when its queue empties' : null,
                  recommended.stop_at ? `at ${recommended.stop_at}` : null,
                ]
                  .filter(Boolean)
                  .join(', or ') || 'never: the Hub will not start a flow with no stop'}
              </p>
              {why('stop', 'build-reason-stop')}
              <p data-testid="build-cron">
                Fires <code>{recommended.cron}</code>
                {describeCron(recommended.cron) ? ` (${describeCron(recommended.cron)})` : ''}
              </p>
              {why('cron', 'build-reason-cron')}
            </div>
          ) : null}

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
              disabled={isPending || agentMissing || leadMissing || capInvalid}
              title={
                agentMissing
                  ? 'Choose the agent that works the flow, builders, or No flow'
                  : leadMissing
                    ? 'Choose the lead'
                    : capInvalid
                      ? 'The cap is a positive number of dollars'
                      : undefined
              }
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
