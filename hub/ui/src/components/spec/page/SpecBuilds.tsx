import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { MenuSelect } from '@/components/ui/menu'
import { Segmented } from '@/components/ui/segmented'
import { Field } from '@/components/ui/settings'
import { formatAgo, formatDuration, formatMoney } from '@/lib/format'
import {
  anchors,
  DRIVER_ICON,
  DRIVER_LABEL,
  DRIVER_MEANING,
  LEVEL_LABEL,
  LEVEL_MEANING,
  TASK_STATUS_LABEL,
  TIME_PARTS,
  type BuildDriver,
  type BuildLevel,
  type BuildView,
  type CheckFinding,
  type StartBuildChoice,
  type TaskStatus,
} from './model'
import { Section } from './SpecDocumentBody'
import '@/styles/spec-page.css'

/** The document's builds, newest first, each with its numbers live (FR-7). */
export function SpecBuildsSection({
  builds,
  canBuild,
  changeOnly = false,
  now,
  flash,
  onStartBuild,
  onOpenRuns,
  onStop,
  onCopyLink,
}: {
  builds: BuildView[]
  /** Whether a build may be started: the document is approved. */
  canBuild: boolean
  /** Only a change document is built: any other kind is told so instead of "once approved". */
  changeOnly?: boolean
  now: Date
  flash: string | null
  onStartBuild: () => void
  onOpenRuns: (build: BuildView) => void
  onStop: (build: BuildView) => void
  onCopyLink: (anchor: string) => void
}) {
  const findings: CheckFinding[] = []
  return (
    <Section
      id="builds"
      title="Builds"
      count={builds.length ? String(builds.length) : undefined}
      findings={findings}
      flash={flash}
      onCopyLink={onCopyLink}
      actions={
        canBuild ? (
          <Button variant="outline" size="xs" onClick={onStartBuild}>
            <Icon name="play_arrow" size={13} />
            Start a build
          </Button>
        ) : null
      }
    >
      {builds.length ? (
        <ol className="aw-sp-builds">
          {builds.map((b) => (
            <BuildCard key={b.id} build={b} now={now} flash={flash === anchors.build(b.id)} onOpenRuns={() => onOpenRuns(b)} onStop={() => onStop(b)} />
          ))}
        </ol>
      ) : (
        <div className="aw-sp-empty aw-sp-empty-builds">
          <Icon name="hammer" size={18} />
          <span>{canBuild ? 'Not built yet. A build chooses who hands out the work, how it is checked, and who does it.' : changeOnly ? 'Only a change document is built.' : 'A build can start once the document is approved.'}</span>
        </div>
      )}
    </Section>
  )
}

const STATUS_ORDER: TaskStatus[] = ['approved', 'under_review', 'completed', 'in_progress', 'revision_needed', 'assigned', 'pending', 'rejected']

function BuildCard({ build: b, now, flash, onOpenRuns, onStop }: { build: BuildView; now: Date; flash: boolean; onOpenRuns: () => void; onStop: () => void }) {
  const anchor = anchors.build(b.id)
  const totalTasks = STATUS_ORDER.reduce((n, s) => n + (b.tasks[s] ?? 0), 0)
  const totalTime = TIME_PARTS.reduce((n, p) => n + b.time[p.key], 0)
  // A role no run reported a cost for is unknown (null), never $0; the figure is unknown only when
  // runs ran and none of them reported one.
  const known = [b.cost.build, b.cost.review, b.cost.lead, b.cost.mend].filter((v): v is number => v !== null)
  const totalCost = known.reduce((n, v) => n + v, 0)
  const costFigure = !known.length && b.runs > 0 ? 'unknown' : formatMoney(totalCost)
  const approved = b.tasks.approved ?? 0
  const people: Array<{ name: string; role: string }> = [
    ...(b.lead ? [{ name: b.lead, role: 'Lead' }] : []),
    ...b.builders.map((name) => ({ name, role: 'Builds' })),
    ...b.reviewers.map((name) => ({ name, role: 'Reviews' })),
  ]
  return (
    <li className="aw-sp-build" id={anchor} data-anchor={anchor} data-running={b.running ? 'true' : 'false'} data-flash={flash ? 'true' : undefined}>
      <div className="aw-sp-build-head">
        <span className="aw-sp-build-num">Build {b.number}</span>
        {b.running ? (
          <span className="aw-sp-build-live">
            <span className="aw-sp-live" aria-hidden="true" />
            Running
          </span>
        ) : (
          <span className="aw-sp-build-done">
            <Icon name={b.ended === 'stopped' ? 'stop_circle' : 'check'} size={12} />
            {b.ended === 'stopped' ? 'Stopped' : 'Finished'}
          </span>
        )}
        <span className="aw-sp-build-driver" title={DRIVER_MEANING[b.driver]}>
          <Icon name={DRIVER_ICON[b.driver]} size={13} />
          {DRIVER_LABEL[b.driver]}
        </span>
        <span className="aw-sp-level" data-level={b.level} title={LEVEL_MEANING[b.level]}>
          {LEVEL_LABEL[b.level]}
        </span>
        <span className="aw-sp-build-when">
          {b.running ? `started ${formatAgo(b.startedAt, now)}` : `${b.ended === 'stopped' ? 'stopped' : 'finished'} ${formatAgo(b.finishedAt ?? b.startedAt, now)}`} · lands on {b.landsOn}
        </span>
        {b.running ? (
          <Button variant="ghost" size="xs" onClick={onStop} className="aw-sp-build-stop">
            <Icon name="stop_circle" size={13} />
            Stop build
          </Button>
        ) : null}
      </div>

      <div className="aw-sp-people">
        {people.map((p) => (
          <span key={`${p.role}-${p.name}`} className="aw-sp-person" data-role={p.role}>
            <span className="aw-sp-avatar" aria-hidden="true">
              {p.name.slice(0, 1)}
            </span>
            <span className="aw-sp-person-name">{p.name}</span>
            <span className="aw-sp-person-role">{p.role}</span>
          </span>
        ))}
      </div>

      <div className="aw-sp-build-grid">
        <Meter
          title="Tasks"
          figure={`${approved} of ${totalTasks} approved`}
          parts={STATUS_ORDER.filter((s) => b.tasks[s]).map((s) => ({ key: s, label: TASK_STATUS_LABEL[s], value: b.tasks[s], tone: `var(--sp-status-${s})`, figure: String(b.tasks[s]) }))}
          total={totalTasks}
          running={b.running}
        />
        <Meter
          title="Wall time"
          figure={formatDuration(totalTime)}
          parts={TIME_PARTS.map((p) => ({ key: p.key, label: p.label, value: b.time[p.key], tone: p.tone, figure: formatDuration(b.time[p.key]) }))}
          total={totalTime}
          running={b.running}
        />
        <Meter
          title="Cost"
          figure={`${costFigure}${b.budget ? ` of ${formatMoney(b.budget)}` : ''}${b.unpriced ? ` · ${b.unpriced} unpriced` : ''}`}
          parts={[
            { key: 'build', label: 'Building', value: b.cost.build ?? 0, tone: 'var(--blue)', figure: formatMoney(b.cost.build ?? 0) },
            { key: 'review', label: 'Reviewing', value: b.cost.review ?? 0, tone: 'var(--amber)', figure: formatMoney(b.cost.review ?? 0) },
            { key: 'lead', label: 'Leading', value: b.cost.lead ?? 0, tone: 'var(--purple)', figure: formatMoney(b.cost.lead ?? 0) },
            { key: 'mend', label: 'Mending', value: b.cost.mend ?? 0, tone: 'var(--red)', figure: formatMoney(b.cost.mend ?? 0) },
          ].filter((p) => p.value > 0)}
          total={b.budget ?? totalCost}
          running={b.running}
        />
      </div>

      <div className="aw-sp-build-foot">
        <button data-slot="link-button" type="button" className="aw-sp-textbutton" onClick={onOpenRuns}>
          <Icon name="terminal" size={12} />
          {b.runs} runs
          <Icon name="arrow_forward" size={11} />
        </button>
        {b.checks.runs ? (
          <span className="aw-sp-checks" data-testid="build-checks">
            {b.checks.runs} check run{b.checks.runs === 1 ? '' : 's'} · {b.checks.passed} passed · {b.checks.failed} failed · {formatDuration(b.checks.seconds)}
          </span>
        ) : null}
      </div>
    </li>
  )
}

/** One stacked bar with its legend: the parts of a whole, and the whole. */
function Meter({
  title,
  figure,
  parts,
  total,
  running,
}: {
  title: string
  figure: string
  parts: Array<{ key: string; label: string; value: number; tone: string; figure: string }>
  total: number
  running: boolean
}) {
  return (
    <div className="aw-sp-meter">
      <div className="aw-sp-meter-head">
        <span className="aw-sp-meter-title">{title}</span>
        <span className="aw-sp-meter-figure">{figure}</span>
      </div>
      <div className="aw-sp-bar" data-running={running ? 'true' : 'false'} role="img" aria-label={`${title}: ${parts.map((p) => `${p.label} ${p.figure}`).join(', ')}`}>
        {parts.map((p) => (
          <span key={p.key} className="aw-sp-bar-part" style={{ width: `${total ? (p.value / total) * 100 : 0}%`, background: p.tone }} title={`${p.label}: ${p.figure}`} />
        ))}
      </div>
      <ul className="aw-sp-legend">
        {parts.map((p) => (
          <li key={p.key}>
            <span className="aw-sp-legend-dot" style={{ background: p.tone }} />
            <span className="aw-sp-legend-label">{p.label}</span>
            <span className="aw-sp-legend-figure">{p.figure}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Choose how a build runs: who hands out the work, how it is checked, who does it, what it may
 *  spend, when, and where it lands. */
export function StartBuildDialog({
  open,
  onOpenChange,
  agents,
  initial,
  approving,
  onStart,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  agents: string[]
  initial: StartBuildChoice
  /** Approve and build: the dialog says it approves first. */
  approving: boolean
  onStart: (choice: StartBuildChoice) => void
}) {
  const [choice, setChoice] = React.useState(initial)
  React.useEffect(() => {
    if (open) setChoice(initial)
  }, [open, initial])
  const set = (patch: Partial<StartBuildChoice>) => setChoice((c) => ({ ...c, ...patch }))
  const toggle = (list: string[], name: string) => (list.includes(name) ? list.filter((n) => n !== name) : [...list, name])
  const missing = !choice.builders.length ? 'Choose at least one builder.' : choice.driver === 'lead' && !choice.lead ? 'Choose the lead.' : null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title={approving ? 'Approve and build' : 'Start a build'}
        description={approving ? 'The plan is approved first, then this build starts on it.' : 'Each build runs on its own branch and is recorded with these choices.'}
        width={580}
        footer={
          <>
            {missing ? <span className="aw-sp-dialog-missing">{missing}</span> : null}
            <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" disabled={Boolean(missing)} onClick={() => onStart(choice)}>
              <Icon name="play_arrow" size={14} />
              {approving ? 'Approve and start' : 'Start the build'}
            </Button>
          </>
        }
      >
        <div className="aw-sp-dialog">
          <Field label="Who hands out the work">
            <Segmented<BuildDriver>
              label="Driver"
              value={choice.driver}
              onChange={(driver) => set({ driver })}
              options={(['flow', 'lead', 'hand'] as BuildDriver[]).map((d) => ({
                value: d,
                label: (
                  <>
                    <Icon name={DRIVER_ICON[d]} size={13} />
                    {DRIVER_LABEL[d]}
                  </>
                ),
              }))}
            />
            <p className="aw-sp-dialog-note">{DRIVER_MEANING[choice.driver]}</p>
          </Field>

          <Field label="Level">
            <Segmented<BuildLevel> label="Level" value={choice.level} onChange={(level) => set({ level })} options={(['fast', 'reviewed', 'gated'] as BuildLevel[]).map((l) => ({ value: l, label: LEVEL_LABEL[l] }))} />
            <p className="aw-sp-dialog-note">{LEVEL_MEANING[choice.level]}</p>
          </Field>

          <Field label="Builders">
            <AgentPicks agents={agents} picked={choice.builders} onToggle={(name) => set({ builders: toggle(choice.builders, name) })} />
          </Field>

          {choice.level !== 'fast' ? (
            <Field label="Reviewers">
              <AgentPicks agents={agents} picked={choice.reviewers} onToggle={(name) => set({ reviewers: toggle(choice.reviewers, name) })} />
              <p className="aw-sp-dialog-note">Any of them may take a review; a builder never reviews its own task.</p>
            </Field>
          ) : null}

          {choice.driver === 'lead' ? (
            <Field label="Lead">
              <MenuSelect<string> label="Lead" value={choice.lead ?? ''} onChange={(lead) => set({ lead: lead || null })} options={[{ value: '', label: 'Choose…' }, ...agents.map((a) => ({ value: a, label: a }))]} />
            </Field>
          ) : null}

          <div className="aw-sp-dialog-row">
            <Field label="Budget cap">
              <Input
                inputMode="decimal"
                placeholder="No cap"
                value={choice.budget ?? ''}
                onChange={(e) => {
                  const n = Number(e.target.value.replace(/[^0-9.]/g, ''))
                  set({ budget: e.target.value && Number.isFinite(n) ? n : null })
                }}
              />
            </Field>
            <Field label="When">
              <MenuSelect<StartBuildChoice['window']>
                label="When"
                value={choice.window}
                onChange={(window) => set({ window })}
                options={[
                  { value: 'now', label: 'Now, until it is done' },
                  { value: 'tonight', label: 'Tonight only', detail: 'Pauses at 07:00.' },
                  { value: 'weekdays', label: 'Weekdays, working hours' },
                ]}
              />
            </Field>
          </div>

          <Field label="Lands on">
            <div className="aw-sp-dialog-lands">
              <Segmented<StartBuildChoice['landsOn']>
                label="Lands on"
                value={choice.landsOn}
                onChange={(landsOn) => set({ landsOn })}
                options={[
                  { value: 'main', label: 'Main' },
                  { value: 'branch', label: 'A branch' },
                ]}
              />
              {choice.landsOn === 'branch' ? <Input aria-label="Branch" value={choice.branch} onChange={(e) => set({ branch: e.target.value })} /> : null}
            </div>
          </Field>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function AgentPicks({ agents, picked, onToggle }: { agents: string[]; picked: string[]; onToggle: (name: string) => void }) {
  return (
    <div className="aw-sp-picks" role="group">
      {agents.map((name) => (
        <button data-slot="pick" type="button" key={name} className="aw-sp-pick" aria-pressed={picked.includes(name)} onClick={() => onToggle(name)}>
          <span className="aw-sp-avatar" aria-hidden="true">
            {name.slice(0, 1)}
          </span>
          {name}
          <Icon name="check" size={12} className="aw-sp-pick-check" />
        </button>
      ))}
    </div>
  )
}
