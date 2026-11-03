import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { MenuSelect, type SelectOption } from '@/components/ui/menu'
import { Segmented } from '@/components/ui/segmented'
import { agentColorVars } from '@/lib/agentColors'
import { describeCron } from '@/lib/cron'
import type { BuildChoices, BuildDriver, BuildLanding, BuildLevel, SpecRecommendedBuild } from '@/api/spec'
import '@/styles/build-plan.css'

/** One agent the build can name: its name, and a muted second line (its model) where known. */
export interface BuildPlanAgent {
  name: string
  detail?: string
  /** The agent's colour, as everywhere else it is named (`agentColorVars`). */
  colorIndex?: number | null
}

/** One declared task of the document, as the table lists it. */
export interface BuildPlanTask {
  key: string
  title: string
}

const DRIVER: Record<BuildDriver, { label: string; icon: string; meaning: string }> = {
  flow: { label: 'Flow', icon: 'sync', meaning: 'The Hub hands out each task as its prerequisites clear.' },
  lead: { label: 'Lead', icon: 'compass', meaning: 'A lead agent hands out the work and is briefed as it moves.' },
  hand: { label: 'By hand', icon: 'hand', meaning: 'Nothing starts: the tasks wait on the board for you.' },
}

const LEVEL: Record<BuildLevel, { label: string; meaning: string }> = {
  fast: { label: 'Fast', meaning: 'The builder or the lead approves; no checker.' },
  reviewed: { label: 'Reviewed', meaning: 'Someone other than the builder checks and approves.' },
  gated: { label: 'Gated', meaning: 'Approval waits for accepted evidence for every requirement.' },
}

type WindowChoice = 'none' | '2h' | '4h' | 'tonight' | 'morning'

/** When the build stops handing out work, as the Hub's `window_end`. No native date input: these
 *  are the ends an operator actually picks. */
function windowEnd(choice: WindowChoice, now: Date): string | undefined {
  const at = new Date(now)
  if (choice === '2h') at.setHours(at.getHours() + 2)
  else if (choice === '4h') at.setHours(at.getHours() + 4)
  else if (choice === 'tonight') at.setHours(23, 0, 0, 0)
  else if (choice === 'morning') {
    at.setDate(at.getDate() + 1)
    at.setHours(7, 0, 0, 0)
  } else return undefined
  return at.toISOString()
}

/**
 * Build, or Approve and build, around the one plan the document carries (`building-a-spec-ties-
 * together-from-plan-to-board`, slice `build-dialog-overhaul`): how the build runs, its default
 * people, and a table of every task's builder and checker, each opened on the document's
 * recommendation beside its reason. A choice that differs from the recommendation says so and can
 * be put back. Presentational: `onConfirm` receives exactly what is shown, in the Hub's
 * `BuildChoices` shape (`delivery_agent` only when the flow's agent was changed, `''` for none).
 */
export function BuildPlanDialog({
  open,
  onOpenChange,
  title,
  approve,
  recommended,
  tasks,
  agents,
  now,
  isPending = false,
  error = null,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  /** Approve and build (true) or Build an approved document (false). */
  approve: boolean
  recommended: SpecRecommendedBuild | undefined
  tasks: BuildPlanTask[]
  /** The project's open agents. */
  agents: BuildPlanAgent[]
  now: Date
  isPending?: boolean
  error?: string | null
  onConfirm: (choices: BuildChoices) => void
}) {
  const names = agents.map((a) => a.name)
  const isOpen = (name: string | null | undefined): name is string => Boolean(name && names.includes(name))
  const flowRecommended = recommended?.mode === 'flow'
  const reasons = recommended?.reasons ?? {}
  const taskReasons = recommended?.task_reasons ?? {}
  const recBuilder = (key: string) => recommended?.task_builders?.[key] ?? ''
  const recChecker = (key: string) => recommended?.task_checkers?.[key] ?? ''

  const initial = React.useMemo(
    () => ({
      driver: recommended?.driver ?? (flowRecommended ? 'flow' : 'hand'),
      level: recommended?.level ?? 'reviewed',
      agent: isOpen(recommended?.agent) ? recommended!.agent! : '',
      builder: isOpen(recommended?.builder) ? recommended!.builder! : '',
      checker: isOpen(recommended?.checker) ? recommended!.checker! : '',
      lead: isOpen(recommended?.lead) ? recommended!.lead! : '',
      cap: recommended?.budget_cap_usd != null ? String(recommended.budget_cap_usd) : '',
      window: 'none' as WindowChoice,
      landing: recommended?.landing ?? 'main',
      taskBuilders: Object.fromEntries(tasks.map((t) => [t.key, isOpen(recBuilder(t.key)) ? recBuilder(t.key) : ''])),
      taskCheckers: Object.fromEntries(tasks.map((t) => [t.key, isOpen(recChecker(t.key)) ? recChecker(t.key) : ''])),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [recommended, tasks, agents],
  )
  const [plan, setPlan] = React.useState(initial)
  React.useEffect(() => {
    if (open) setPlan(initial)
  }, [open, initial])
  const set = (patch: Partial<typeof plan>) => setPlan((p) => ({ ...p, ...patch }))

  const capValue = plan.cap.trim() === '' ? undefined : Number(plan.cap)
  const capInvalid = capValue !== undefined && !(Number.isFinite(capValue) && capValue > 0)
  const builderOf = (key: string) => plan.taskBuilders[key] || plan.builder
  const checkerOf = (key: string) => plan.taskCheckers[key] || plan.checker
  const ownWork = plan.level === 'fast' ? [] : tasks.filter((t) => builderOf(t.key) && builderOf(t.key) === checkerOf(t.key))
  const missing =
    plan.driver === 'lead' && !plan.lead
      ? 'Choose the lead.'
      : capInvalid
        ? 'The cap is a positive number of dollars.'
        : ownWork.length
          ? `${ownWork.length === 1 ? 'One task has' : `${ownWork.length} tasks have`} the same agent building and checking.`
          : null
  const changed = tasks.filter(
    (t) => plan.taskBuilders[t.key] !== initial.taskBuilders[t.key] || plan.taskCheckers[t.key] !== initial.taskCheckers[t.key],
  ).length

  function confirm() {
    const choices: BuildChoices = {
      driver: plan.driver,
      level: plan.level,
      builders: Array.from(new Set(tasks.map((t) => builderOf(t.key)).filter(Boolean))),
      builder: plan.builder,
      checker: plan.checker,
      landing: plan.landing,
      task_builders: plan.taskBuilders,
      task_checkers: plan.taskCheckers,
    }
    if (plan.driver === 'lead') choices.lead = plan.lead
    if (capValue !== undefined) choices.budget_cap_usd = capValue
    const end = windowEnd(plan.window, now)
    if (end) choices.window_end = end
    if (plan.driver === 'flow' && flowRecommended && plan.agent !== initial.agent) choices.delivery_agent = plan.agent
    onConfirm(choices)
  }

  const agentOptions = (blank: string, current: string, recommendedName: string): SelectOption<string>[] => [
    { value: '', label: blank },
    ...(current && !names.includes(current) ? [{ value: current, label: current, detail: 'Not an open agent', disabled: true }] : []),
    ...agents.map((a) => ({
      value: a.name,
      label: a.name,
      icon: <span className="aw-bp-dot" style={{ background: agentColorVars(a.colorIndex).accent }} aria-hidden="true" />,
      detail: [a.detail, a.name === recommendedName ? 'Recommended' : null].filter(Boolean).join(' · ') || undefined,
    })),
  ]
  const verb = approve ? 'Approve and build' : 'Build'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title={`${verb} “${title}”`}
        description={
          approve
            ? 'Approves the version you read, then starts building it as planned below.'
            : 'Starts building it as planned below. Its tasks are already on the board.'
        }
        width={760}
        footer={
          <>
            {error ? (
              <span className="aw-bp-missing" role="alert">
                {error}
              </span>
            ) : missing ? (
              <span className="aw-bp-missing">{missing}</span>
            ) : changed ? (
              <span className="aw-bp-changed">
                {changed === 1 ? 'One task differs' : `${changed} tasks differ`} from the recommendation.
              </span>
            ) : (
              <span className="aw-bp-changed">As the document recommends.</span>
            )}
            <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} disabled={isPending}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" disabled={isPending || Boolean(missing)} onClick={confirm} data-testid="build-confirm">
              <Icon name="play_arrow" size={14} />
              {isPending ? `${verb}…` : verb}
            </Button>
          </>
        }
      >
        <div className="aw-bp">
          {!recommended ? (
            <p className="aw-bp-lede">The document recommends no build: choose how it is built.</p>
          ) : null}

          <section className="aw-bp-section" aria-labelledby="aw-bp-run">
            <h3 id="aw-bp-run" className="aw-bp-heading">
              How it runs
            </h3>
            <div className="aw-bp-grid">
              <Setting label="Who hands out the work" why={reasons.driver ?? reasons.mode}>
                <Segmented<BuildDriver>
                  label="Driver"
                  value={plan.driver}
                  onChange={(driver) => set({ driver })}
                  options={(['flow', 'lead', 'hand'] as BuildDriver[]).map((d) => ({
                    value: d,
                    label: (
                      <>
                        <Icon name={DRIVER[d].icon} size={13} />
                        {DRIVER[d].label}
                      </>
                    ),
                  }))}
                />
                <p className="aw-bp-note">{DRIVER[plan.driver].meaning}</p>
              </Setting>
              <Setting label="Level" why={reasons.level}>
                <Segmented<BuildLevel>
                  label="Level"
                  value={plan.level}
                  onChange={(level) => set({ level })}
                  options={(['fast', 'reviewed', 'gated'] as BuildLevel[]).map((l) => ({ value: l, label: LEVEL[l].label }))}
                />
                <p className="aw-bp-note">{LEVEL[plan.level].meaning} Checks hold at every level.</p>
              </Setting>
              {plan.driver === 'lead' ? (
                <Setting label="Lead" why={reasons.lead}>
                  <MenuSelect<string> label="Lead" value={plan.lead} onChange={(lead) => set({ lead })} options={agentOptions('Choose the lead…', plan.lead, recommended?.lead ?? '')} />
                </Setting>
              ) : null}
              {plan.driver === 'flow' && flowRecommended ? (
                <Setting label="Flow" why={reasons.stop ?? reasons.cron}>
                  <p className="aw-bp-fact">
                    {[
                      recommended?.stop_when_queue_empties ? 'Stops when its queue empties' : null,
                      recommended?.stop_at ? `stops at ${recommended.stop_at}` : null,
                    ]
                      .filter(Boolean)
                      .join(', or ') || 'Never stops on its own'}
                    {recommended?.cron && describeCron(recommended.cron) ? `; looks for work ${describeCron(recommended.cron)!.toLowerCase()}` : ''}.
                  </p>
                </Setting>
              ) : null}
              <Setting label="Lands on" why={reasons.landing}>
                <Segmented<BuildLanding>
                  label="Lands on"
                  value={plan.landing}
                  onChange={(landing) => set({ landing })}
                  options={[
                    { value: 'main', label: 'The main branch' },
                    { value: 'nowhere', label: 'Nowhere' },
                  ]}
                />
                <p className="aw-bp-note">
                  {plan.landing === 'main' ? 'Approved work merges once its checks pass.' : 'Work is approved and recorded; nothing merges.'}
                </p>
              </Setting>
              <div className="aw-bp-pair">
                <Setting label="Budget cap" why={reasons.cap}>
                  <Input inputMode="decimal" placeholder="No cap" aria-label="Budget cap in US dollars" value={plan.cap} onChange={(e) => set({ cap: e.target.value })} />
                </Setting>
                <Setting label="Stops handing out work">
                  <MenuSelect<WindowChoice>
                    label="Stops handing out work"
                    value={plan.window}
                    onChange={(window) => set({ window })}
                    options={[
                      { value: 'none', label: 'When the work is done' },
                      { value: '2h', label: 'In two hours' },
                      { value: '4h', label: 'In four hours' },
                      { value: 'tonight', label: 'Tonight at 23:00' },
                      { value: 'morning', label: 'Tomorrow at 07:00' },
                    ]}
                  />
                </Setting>
              </div>
            </div>
          </section>

          <section className="aw-bp-section" aria-labelledby="aw-bp-people">
            <h3 id="aw-bp-people" className="aw-bp-heading">
              Who builds and checks
            </h3>
            <div className="aw-bp-defaults">
              <Setting label="Default builder" why={reasons.builders ?? reasons.agent}>
                <MenuSelect<string> label="Default builder" value={plan.builder} onChange={(builder) => set({ builder, agent: builder })} options={agentOptions('Any free agent', plan.builder, recommended?.builder ?? '')} />
              </Setting>
              {plan.level !== 'fast' ? (
                <Setting label="Default checker" why={reasons.checker ?? reasons.reviewer}>
                  <MenuSelect<string> label="Default checker" value={plan.checker} onChange={(checker) => set({ checker })} options={agentOptions('Anyone but the builder', plan.checker, recommended?.checker ?? '')} />
                </Setting>
              ) : null}
            </div>

            <div className="aw-bp-table" role="table" aria-label="Each task's builder and checker">
              <div className="aw-bp-row aw-bp-row-head" role="row" data-checks={plan.level !== 'fast' ? undefined : 'false'}>
                <span role="columnheader">Task</span>
                <span role="columnheader">Builder</span>
                {plan.level !== 'fast' ? <span role="columnheader">Checker</span> : null}
              </div>
              {tasks.map((task, index) => (
                <TaskRow
                  key={task.key}
                  number={index + 1}
                  task={task}
                  checks={plan.level !== 'fast'}
                  builder={plan.taskBuilders[task.key] ?? ''}
                  checker={plan.taskCheckers[task.key] ?? ''}
                  defaultBuilder={plan.builder}
                  defaultChecker={plan.checker}
                  recommendedBuilder={recBuilder(task.key)}
                  recommendedChecker={recChecker(task.key)}
                  reason={taskReasons[task.key] ?? {}}
                  isOpen={isOpen}
                  agentOptions={agentOptions}
                  onBuilder={(name) => set({ taskBuilders: { ...plan.taskBuilders, [task.key]: name } })}
                  onChecker={(name) => set({ taskCheckers: { ...plan.taskCheckers, [task.key]: name } })}
                />
              ))}
            </div>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function Setting({ label, why, children }: { label: string; why?: string; children: React.ReactNode }) {
  return (
    <div className="aw-bp-setting">
      <span className="aw-bp-label">{label}</span>
      {children}
      {why ? <p className="aw-bp-why">{why}</p> : null}
    </div>
  )
}

function TaskRow({
  number,
  task,
  checks,
  builder,
  checker,
  defaultBuilder,
  defaultChecker,
  recommendedBuilder,
  recommendedChecker,
  reason,
  isOpen,
  agentOptions,
  onBuilder,
  onChecker,
}: {
  number: number
  task: BuildPlanTask
  checks: boolean
  builder: string
  checker: string
  defaultBuilder: string
  defaultChecker: string
  recommendedBuilder: string
  recommendedChecker: string
  reason: { builder?: string; checker?: string }
  isOpen: (name: string | null | undefined) => name is string
  agentOptions: (blank: string, current: string, recommended: string) => SelectOption<string>[]
  onBuilder: (name: string) => void
  onChecker: (name: string) => void
}) {
  const effectiveBuilder = builder || defaultBuilder
  const same = checks && effectiveBuilder !== '' && effectiveBuilder === (checker || defaultChecker)
  const pick = (
    role: 'builder' | 'checker',
    value: string,
    fallback: string,
    rec: string,
    why: string | undefined,
    onChange: (name: string) => void,
  ) => {
    const differs = value !== (isOpen(rec) ? rec : '')
    return (
      <div className="aw-bp-cell" role="cell">
        <MenuSelect<string>
          label={`${task.title}: ${role}`}
          value={value}
          onChange={onChange}
          maxWidth={220}
          options={agentOptions(fallback ? `Default (${fallback})` : role === 'builder' ? 'Any free agent' : 'Anyone but the builder', value, rec)}
        />
        {rec && !isOpen(rec) ? (
          <p className="aw-bp-warn">Recommended {rec} is not an open agent here.</p>
        ) : differs && rec ? (
          <p className="aw-bp-differs">
            Recommended {rec}
            <button data-slot="link" type="button" className="aw-bp-reset" onClick={() => onChange(rec)}>
              Put back
            </button>
          </p>
        ) : why ? (
          <p className="aw-bp-why">{why}</p>
        ) : (
          <p className="aw-bp-why aw-bp-none">{rec ? 'No reason given.' : 'No recommendation.'}</p>
        )}
      </div>
    )
  }
  return (
    <div className="aw-bp-row" role="row" data-same={same ? 'true' : undefined} data-checks={checks ? undefined : 'false'}>
      <div className="aw-bp-task" role="cell" title={task.key}>
        <span className="aw-bp-num">{number}</span>
        <span className="aw-bp-title">{task.title}</span>
        {same ? <span className="aw-bp-warn">Checks its own work</span> : null}
      </div>
      {pick('builder', builder, defaultBuilder, recommendedBuilder, reason.builder, onBuilder)}
      {checks ? pick('checker', checker, defaultChecker, recommendedChecker, reason.checker, onChecker) : null}
    </div>
  )
}
