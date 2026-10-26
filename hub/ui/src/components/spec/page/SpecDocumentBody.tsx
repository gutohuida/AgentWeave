import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { MenuSelect, type SelectOption } from '@/components/ui/menu'
import { Segmented } from '@/components/ui/segmented'
import {
  anchors,
  buildLevels,
  countFilters,
  EVIDENCE_LABEL,
  EVIDENCE_TONE,
  filterRequirements,
  NO_DOCUMENT_FILTERS,
  orderTasks,
  TASK_STATUS_LABEL,
  type CheckFinding,
  type DocumentFilters,
  type EvidenceState,
  type SpecDocumentView,
  type SpecRequirementView,
  type SpecTaskView,
  type TaskStatus,
} from './model'
import { useEnter } from './hooks'
import '@/styles/spec-page.css'

export type BodyPart = 'document' | 'tasks' | 'builds'

export interface SpecDocumentBodyProps {
  doc: SpecDocumentView
  filters: DocumentFilters
  onFiltersChange: (next: DocumentFilters) => void
  /** What the last check found; shown beside what each finding concerns (FR-2). */
  findings: CheckFinding[]
  /** The builds section, drawn by the caller (it holds the live build state). */
  builds: React.ReactNode
  /** Which parts to show: all of them on the Spec tab, one per tab in the panel. */
  parts: BodyPart[]
  /** The anchor just jumped to: it flashes once. */
  flash: string | null
  compact?: boolean
  onJump: (anchor: string) => void
  onCopyLink: (anchor: string) => void
}

/** The document, drawn by the app from its structure rather than a frame of rendered HTML (FR-3),
 *  so requirements and tasks filter, order, highlight and link in place. */
export function SpecDocumentBody(props: SpecDocumentBodyProps) {
  const { doc, filters, findings, parts } = props
  const requirements = filterRequirements(doc.requirements, filters)
  const tasks = orderTasks(doc.tasks, filters)
  const findingsFor = (kind: CheckFinding['target']['kind'], id: string) => findings.filter((f) => f.target.kind === kind && f.target.id === id)
  const agents = Array.from(new Set(doc.tasks.map((t) => t.agent).filter((a): a is string => Boolean(a)))).sort()
  const show = (part: BodyPart) => parts.includes(part)

  return (
    <div className="aw-sp-body" data-compact={props.compact ? 'true' : 'false'}>
      {show('document') || show('tasks') ? (
        <DocumentFilterBar
          doc={doc}
          filters={filters}
          agents={agents}
          showRequirementFilters={show('document')}
          showTaskFilters={show('tasks')}
          onChange={props.onFiltersChange}
        />
      ) : null}

      {show('document') ? (
        <>
          <Section id="summary" title="Summary" onCopyLink={props.onCopyLink} flash={props.flash} findings={findingsFor('section', 'summary')}>
            <p className="aw-sp-lede">{doc.summary}</p>
          </Section>
          <Section id="problem" title="Problem" onCopyLink={props.onCopyLink} flash={props.flash} findings={findingsFor('section', 'problem')}>
            <p className="aw-sp-prose">{doc.problem}</p>
          </Section>
          <Section id="scope" title="Scope" onCopyLink={props.onCopyLink} flash={props.flash} findings={findingsFor('section', 'scope')}>
            <div className="aw-sp-scope">
              <ScopeList title="In scope" icon="check" items={doc.inScope} />
              <ScopeList title="Not in this change" icon="remove_circle" items={doc.nonGoals} />
            </div>
          </Section>
          <Section
            id="requirements"
            title="Requirements"
            count={filters.evidence !== 'any' || filters.task !== 'any' ? `${requirements.length} of ${doc.requirements.length}` : String(doc.requirements.length)}
            onCopyLink={props.onCopyLink}
            flash={props.flash}
            findings={[]}
          >
            {requirements.length ? (
              <ol className="aw-sp-reqs">
                {requirements.map((r, i) => (
                  <RequirementCard
                    key={r.identifier}
                    requirement={r}
                    index={i}
                    tasks={doc.tasks}
                    findings={findingsFor('requirement', r.identifier)}
                    flash={props.flash === anchors.requirement(r.identifier)}
                    onJump={props.onJump}
                    onCopyLink={props.onCopyLink}
                  />
                ))}
              </ol>
            ) : (
              <EmptyFilter onClear={() => props.onFiltersChange({ ...filters, evidence: 'any', task: 'any' })} what="requirements" />
            )}
          </Section>
        </>
      ) : null}

      {show('tasks') ? (
        <Section
          id="tasks"
          title={doc.state === 'writing' || doc.state === 'ready' ? 'Tasks (the plan)' : 'Tasks'}
          count={filters.status !== 'any' || filters.agent !== 'any' ? `${tasks.length} of ${doc.tasks.length}` : String(doc.tasks.length)}
          onCopyLink={props.onCopyLink}
          flash={props.flash}
          findings={[]}
        >
          {tasks.length ? (
            <TaskList tasks={tasks} all={doc.tasks} order={filters.order} findingsFor={(key) => findingsFor('task', key)} flash={props.flash} onJump={props.onJump} onCopyLink={props.onCopyLink} />
          ) : (
            <EmptyFilter onClear={() => props.onFiltersChange({ ...filters, status: 'any', agent: 'any' })} what="tasks" />
          )}
        </Section>
      ) : null}

      {show('builds') ? props.builds : null}

      {show('document') && doc.openQuestions.length ? (
        <Section id="questions" title="Open questions" count={String(doc.openQuestions.filter((q) => !q.resolved).length || '')} onCopyLink={props.onCopyLink} flash={props.flash} findings={findingsFor('section', 'questions')}>
          <ul className="aw-sp-questions">
            {doc.openQuestions.map((q) => (
              <li key={q.question} data-resolved={q.resolved ? 'true' : 'false'}>
                <Icon name={q.resolved ? 'check_circle' : 'help_circle'} size={14} />
                <span>{q.question}</span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </div>
  )
}

/** A titled part of the document, with its anchor and a link that reopens it. */
export function Section({
  id,
  title,
  count,
  children,
  findings,
  flash,
  onCopyLink,
  actions,
}: {
  id: string
  title: string
  count?: string
  children: React.ReactNode
  findings: CheckFinding[]
  flash: string | null
  onCopyLink: (anchor: string) => void
  actions?: React.ReactNode
}) {
  const anchor = anchors.section(id)
  return (
    <section className="aw-sp-section aw-reveal-host" data-enter="" id={anchor} data-anchor={anchor} data-flash={flash === anchor ? 'true' : undefined}>
      <h2 className="aw-sp-section-title">
        {title}
        {count ? <span className="aw-sp-section-count">{count}</span> : null}
        <CopyLink onCopy={() => onCopyLink(anchor)} label={`Copy a link to ${title}`} />
        {actions ? <span className="aw-sp-section-actions">{actions}</span> : null}
      </h2>
      {findings.map((f) => (
        <Finding key={f.id} finding={f} />
      ))}
      {children}
    </section>
  )
}

function CopyLink({ onCopy, label }: { onCopy: () => void; label: string }) {
  return (
    <button data-slot="icon-button" type="button" className="aw-icon-button aw-reveal aw-sp-link" onClick={onCopy} aria-label={label} title={label}>
      <Icon name="link" size={13} />
    </button>
  )
}

function Finding({ finding }: { finding: CheckFinding }) {
  const ref = useEnter<HTMLDivElement>('pop')
  return (
    <div className="aw-sp-finding" data-severity={finding.severity} role="note" ref={ref}>
      <Icon name={finding.severity === 'blocking' ? 'error' : 'warning'} size={14} />
      <span>
        <strong>{finding.severity === 'blocking' ? 'Blocks approval' : 'Warning'}</strong> {finding.message}
      </span>
    </div>
  )
}

function ScopeList({ title, icon, items }: { title: string; icon: string; items: string[] }) {
  return (
    <div className="aw-sp-scope-col">
      <h3 className="aw-sp-scope-title">{title}</h3>
      <ul>
        {items.map((item) => (
          <li key={item}>
            <Icon name={icon} size={13} />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function EmptyFilter({ what, onClear }: { what: string; onClear: () => void }) {
  return (
    <div className="aw-sp-empty">
      No {what} match these filters.
      <button data-slot="link-button" type="button" className="aw-sp-textbutton" onClick={onClear}>
        Clear them
      </button>
    </div>
  )
}

export function EvidenceChip({ state }: { state: EvidenceState }) {
  return (
    <span className="aw-sp-evidence" data-state={state} style={{ '--tone': EVIDENCE_TONE[state] } as React.CSSProperties}>
      {EVIDENCE_LABEL[state]}
    </span>
  )
}

/** A task's status; a task of a plan not yet approved has none, and reads as planned. */
export function StatusChip({ status }: { status: TaskStatus | null | undefined }) {
  return (
    <span className="aw-sp-status" data-status={status ?? 'planned'}>
      {status ? TASK_STATUS_LABEL[status] : 'Planned'}
    </span>
  )
}

function RequirementCard({
  requirement: r,
  index,
  tasks,
  findings,
  flash,
  onJump,
  onCopyLink,
}: {
  requirement: SpecRequirementView
  index: number
  tasks: SpecTaskView[]
  findings: CheckFinding[]
  flash: boolean
  onJump: (anchor: string) => void
  onCopyLink: (anchor: string) => void
}) {
  const [open, setOpen] = React.useState(false)
  const anchor = anchors.requirement(r.identifier)
  const served = r.taskKeys.map((k) => tasks.find((t) => t.key === k)).filter((t): t is SpecTaskView => Boolean(t))
  return (
    <li
      className="aw-sp-req aw-reveal-host"
      id={anchor}
      data-anchor={anchor}
      data-flash={flash ? 'true' : undefined}
      data-finding={findings.some((f) => f.severity === 'blocking') ? 'blocking' : findings.length ? 'warning' : undefined}
      style={{ '--i': Math.min(index, 12) } as React.CSSProperties}
    >
      <div className="aw-sp-req-head">
        <span className="aw-sp-req-id" title={r.key}>
          {r.identifier}
        </span>
        <span className="aw-sp-modal" data-modal={r.modal}>
          {r.modal}
        </span>
        <EvidenceChip state={r.evidence} />
        <span className="aw-sp-req-tasks">
          {served.map((t) => (
            <button data-slot="task-chip" type="button" key={t.key} className="aw-sp-taskchip" onClick={() => onJump(anchors.task(t.key))} title={`Jump to the task: ${t.title}`}>
              <span className="aw-sp-taskchip-dot" data-status={t.status ?? 'pending'} />
              <span className="truncate">{t.title}</span>
            </button>
          ))}
        </span>
        <CopyLink onCopy={() => onCopyLink(anchor)} label={`Copy a link to ${r.identifier}`} />
      </div>
      <p className="aw-sp-req-statement">{r.statement}</p>
      {findings.map((f) => (
        <Finding key={f.id} finding={f} />
      ))}
      {r.rationale ? <p className="aw-sp-req-why">{r.rationale}</p> : null}
      {r.criteria.length ? (
        <>
          <button data-slot="disclosure" type="button" className="aw-sp-disclosure" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            <Icon name="chevron_right" size={13} className="aw-sp-disclosure-chevron" />
            {r.criteria.length} {r.criteria.length === 1 ? 'acceptance criterion' : 'acceptance criteria'}
          </button>
          <div className="aw-sp-collapse" data-open={open ? 'true' : 'false'}>
            <div className="aw-sp-collapse-inner">
              <ol className="aw-sp-criteria">
                {r.criteria.map((c) => (
                  <li key={c.key} className="aw-sp-criterion">
                    <span className="aw-sp-gwt">Given</span>
                    <span>{c.given}</span>
                    <span className="aw-sp-gwt">When</span>
                    <span>{c.when}</span>
                    <span className="aw-sp-gwt">Then</span>
                    <span>{c.then}</span>
                    {c.howToCheck ? (
                      <>
                        <span className="aw-sp-gwt">Checked by</span>
                        <span className="aw-sp-muted">{c.howToCheck}</span>
                      </>
                    ) : null}
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </>
      ) : null}
    </li>
  )
}

/** The tasks, in build order with each one's prerequisites drawn as threads in the gutter, or by
 *  status. */
function TaskList({
  tasks,
  all,
  order,
  findingsFor,
  flash,
  onJump,
  onCopyLink,
}: {
  tasks: SpecTaskView[]
  all: SpecTaskView[]
  order: DocumentFilters['order']
  findingsFor: (key: string) => CheckFinding[]
  flash: string | null
  onJump: (anchor: string) => void
  onCopyLink: (anchor: string) => void
}) {
  const levels = buildLevels(all)
  const list = React.useRef<HTMLOListElement>(null)
  const [nodes, setNodes] = React.useState<Record<string, number>>({})
  const [open, setOpen] = React.useState<string | null>(null)
  const graph = order === 'build'

  // Where each task's knot sits, measured, so the threads follow rows of any height.
  React.useLayoutEffect(() => {
    const el = list.current
    if (!el || !graph) return
    const measure = () => {
      const next: Record<string, number> = {}
      el.querySelectorAll<HTMLElement>('[data-task]').forEach((row) => {
        next[row.dataset.task!] = row.offsetTop + 19
      })
      setNodes(next)
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [graph, tasks, open])

  const maxLevel = Math.max(0, ...tasks.map((t) => levels.get(t.key) ?? 0))
  const x = (key: string) => 10 + (levels.get(key) ?? 0) * 14
  const gutter = graph ? 20 + maxLevel * 14 : 0

  return (
    <ol ref={list} className="aw-sp-tasks" data-graph={graph ? 'true' : 'false'} style={{ '--gutter': `${gutter}px` } as React.CSSProperties}>
      {graph ? (
        <svg className="aw-sp-threads" width={gutter} height="100%" aria-hidden="true">
          {tasks.flatMap((t) =>
            t.dependsOn
              .filter((d) => nodes[d] !== undefined && nodes[t.key] !== undefined)
              .map((d) => {
                const x1 = x(d)
                const y1 = nodes[d]!
                const x2 = x(t.key)
                const y2 = nodes[t.key]!
                const mid = (y1 + y2) / 2
                return (
                  <path
                    key={`${d}->${t.key}`}
                    d={x1 === x2 ? `M${x1} ${y1} L${x2} ${y2}` : `M${x1} ${y1} C${x1} ${mid} ${x2} ${mid} ${x2} ${y2}`}
                    className="aw-sp-thread"
                    data-done={all.find((a) => a.key === d)?.status === 'approved' ? 'true' : 'false'}
                  />
                )
              }),
          )}
          {tasks.map((t) =>
            nodes[t.key] !== undefined ? <circle key={t.key} cx={x(t.key)} cy={nodes[t.key]} r={4.5} className="aw-sp-knot" data-status={t.status ?? 'pending'} /> : null,
          )}
        </svg>
      ) : null}
      {tasks.map((t, i) => {
        const anchor = anchors.task(t.key)
        const findings = findingsFor(t.key)
        const after = t.dependsOn.map((d) => all.find((a) => a.key === d)?.title).filter(Boolean)
        return (
          <li
            key={t.key}
            className="aw-sp-task aw-reveal-host"
            id={anchor}
            data-anchor={anchor}
            data-task={t.key}
            data-flash={flash === anchor ? 'true' : undefined}
            data-finding={findings.length ? findings[0]!.severity : undefined}
            style={{ '--i': Math.min(i, 12) } as React.CSSProperties}
          >
            <div className="aw-sp-task-row">
              {!graph ? <span className="aw-sp-taskchip-dot" data-status={t.status ?? 'pending'} /> : null}
              <button data-slot="disclosure" type="button" className="aw-sp-task-title" aria-expanded={open === t.key} onClick={() => setOpen((o) => (o === t.key ? null : t.key))}>
                {t.title}
              </button>
              <StatusChip status={t.status} />
              <CopyLink onCopy={() => onCopyLink(anchor)} label={`Copy a link to ${t.title}`} />
            </div>
            <div className="aw-sp-task-meta">
              {t.agent ? (
                <span className="aw-sp-agent">
                  <span className="aw-sp-agent-dot" />
                  {t.agent}
                </span>
              ) : (
                <span className="aw-sp-muted">Not handed out</span>
              )}
              {after.length ? <span className="aw-sp-muted">after {after.join(', ')}</span> : null}
              <span className="aw-sp-task-reqs">
                {t.requirementIds.slice(0, 5).map((id) => (
                  <button data-slot="req-chip" type="button" key={id} className="aw-sp-reqchip" onClick={() => onJump(anchors.requirement(id))} title={`Jump to ${id}`}>
                    {id}
                  </button>
                ))}
                {t.requirementIds.length > 5 ? <span className="aw-sp-muted">+{t.requirementIds.length - 5}</span> : null}
              </span>
            </div>
            {findings.map((f) => (
              <Finding key={f.id} finding={f} />
            ))}
            <div className="aw-sp-collapse" data-open={open === t.key ? 'true' : 'false'}>
              <div className="aw-sp-collapse-inner">
                <p className="aw-sp-task-desc">{t.description}</p>
              </div>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

/** Filters within the document (FR-5): requirements by evidence state and task, tasks by status and
 *  agent, and the order the tasks are listed in. Sticks to the top as the document scrolls. */
function DocumentFilterBar({
  doc,
  filters,
  agents,
  showRequirementFilters,
  showTaskFilters,
  onChange,
}: {
  doc: SpecDocumentView
  filters: DocumentFilters
  agents: string[]
  showRequirementFilters: boolean
  showTaskFilters: boolean
  onChange: (next: DocumentFilters) => void
}) {
  const evidenceCounts = (state: EvidenceState) => doc.requirements.filter((r) => r.evidence === state).length
  const evidenceOptions: SelectOption<EvidenceState | 'any'>[] = [
    { value: 'any', label: 'Any evidence' },
    ...(['verified', 'awaiting', 'in_progress', 'rejected', 'not_started'] as EvidenceState[])
      .filter((s) => evidenceCounts(s) > 0)
      .map((s) => ({ value: s, label: `${EVIDENCE_LABEL[s]} · ${evidenceCounts(s)}` })),
  ]
  const taskOptions: SelectOption<string>[] = [{ value: 'any', label: 'Any task' }, ...doc.tasks.map((t) => ({ value: t.key, label: t.title }))]
  const statuses = Array.from(new Set(doc.tasks.map((t) => t.status ?? 'pending')))
  const statusOptions: SelectOption<TaskStatus | 'any'>[] = [{ value: 'any', label: 'Any status' }, ...statuses.map((s) => ({ value: s, label: TASK_STATUS_LABEL[s] }))]
  const agentOptions: SelectOption<string>[] = [{ value: 'any', label: 'Anyone' }, ...agents.map((a) => ({ value: a, label: a }))]
  const active = countFilters(filters)
  return (
    <div className="aw-sp-filterbar" role="toolbar" aria-label="Filter the document">
      <Icon name="filter_list" size={14} className="aw-sp-filterbar-icon" />
      {showRequirementFilters ? (
        <span className="aw-sp-filtergroup" aria-label="Requirements">
          <MenuSelect label="Requirements by evidence" value={filters.evidence} onChange={(evidence) => onChange({ ...filters, evidence })} options={evidenceOptions} maxWidth={190} />
          <MenuSelect label="Requirements by task" value={filters.task} onChange={(task) => onChange({ ...filters, task })} options={taskOptions} maxWidth={190} />
        </span>
      ) : null}
      {showTaskFilters ? (
        <span className="aw-sp-filtergroup" aria-label="Tasks">
          <MenuSelect label="Tasks by status" value={filters.status} onChange={(status) => onChange({ ...filters, status })} options={statusOptions} maxWidth={150} />
          <MenuSelect label="Tasks by agent" value={filters.agent} onChange={(agent) => onChange({ ...filters, agent })} options={agentOptions} maxWidth={150} />
          <Segmented
            label="Order tasks"
            size="xs"
            value={filters.order}
            onChange={(order) => onChange({ ...filters, order })}
            options={[
              { value: 'build', label: 'Build order' },
              { value: 'status', label: 'Status' },
            ]}
          />
        </span>
      ) : null}
      {active ? (
        <button data-slot="link-button" type="button" className="aw-sp-textbutton aw-sp-filter-clear" onClick={() => onChange({ ...NO_DOCUMENT_FILTERS, order: filters.order })}>
          <Icon name="close" size={12} />
          Clear {active === 1 ? 'filter' : `${active} filters`}
        </button>
      ) : null}
    </div>
  )
}
