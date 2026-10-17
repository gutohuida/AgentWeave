import { useMemo, useState, type CSSProperties } from 'react'
import { Icon } from '@/components/common/Icon'
import { StatePill } from '@/components/common/StatePill'
import { Expander } from '@/components/common/Expander'
import { EvidenceProof, EvidenceReviews } from '@/components/evidence/EvidenceProof'
import { useEvidenceReviews, useProjectEvidence, type EvidencePiece } from '@/api/spec'
import { useTasks } from '@/api/tasks'
import { evidenceTone, statusTone } from '@/lib/storyTones'
import { hubDate } from '@/lib/hubTime'

/**
 * Every piece of evidence in the project, in one place (slice evidence-browser).
 *
 * Agents record evidence and the reviewing agent's verdict decides it (vis-D1, vis-D4); this is
 * where the operator inspects what was decided, after the fact. Filter by state, agent or search,
 * group by requirement or by task, and open any piece into its proof. `focus` (a task id or a
 * requirement identifier, from the URL) narrows it to what a link elsewhere meant.
 */

type StateFilter = 'all' | 'awaiting' | 'accepted' | 'rejected'
type Grouping = 'requirement' | 'task'

const STATE_LABEL: Record<StateFilter, string> = {
  all: 'All',
  awaiting: 'Waiting',
  accepted: 'Accepted',
  rejected: 'Rejected',
}

function relative(value: string): string {
  const seconds = Math.round((Date.now() - hubDate(value).getTime()) / 1000)
  if (seconds < 45) return 'just now'
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`
  return hubDate(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function PieceRow({
  piece,
  index,
  taskTitle,
  onOpenTask,
  showRequirement,
}: {
  piece: EvidencePiece
  index: number
  taskTitle: string | null
  onOpenTask: (taskId: string) => void
  /** False when the group already names the requirement, so the row does not repeat it. */
  showRequirement: boolean
}) {
  const [open, setOpen] = useState(false)
  const history = useEvidenceReviews(piece.id, open)
  const reviews = (history.data?.reviews ?? []).map((review) => ({
    decision: review.decision,
    actor_kind: review.actor_kind,
    actor: review.actor,
    reason: review.reason,
    at: review.created_at,
  }))
  const latest = piece.latest_review
  return (
    <li
      className="aw-evidence-row"
      style={{ '--i': index } as CSSProperties}
      data-testid={`evidence-row-${piece.id}`}
      data-open={open ? 'true' : 'false'}
    >
      <button
        type="button"
        className="aw-evidence-head"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        data-testid={`evidence-row-toggle-${piece.id}`}
      >
        <Icon name="chevron_right" size={13} aria-hidden="true" />
        {showRequirement ? (
          <span className="aw-evidence-req">{piece.requirement?.identifier ?? '—'}</span>
        ) : (
          <span aria-hidden="true" />
        )}
        <span className="aw-evidence-summary">{piece.summary || piece.locator || 'No summary'}</span>
        <span className="aw-evidence-tags">
          {piece.covers === 'partial' ? <StatePill tone="amber">partial</StatePill> : null}
          {piece.superseded_by ? <span className="aw-tl-meta">replaced</span> : null}
          <StatePill key={piece.review_state} tone={evidenceTone(piece.review_state)}>
            {piece.review_state === 'awaiting' ? 'waiting' : piece.review_state}
          </StatePill>
        </span>
      </button>
      <div className="aw-evidence-meta aw-tl-meta">
        {piece.actor_kind === 'operator' ? 'you' : piece.actor} · {relative(piece.produced_at)}
        {piece.task_id ? (
          <>
            {' · '}
            <button
              type="button"
              className="aw-inline-link"
              onClick={() => onOpenTask(piece.task_id as string)}
              data-testid={`evidence-row-task-${piece.id}`}
            >
              {taskTitle ?? piece.task_id}
            </button>
          </>
        ) : null}
        {!open && latest ? (
          <>
            {' · '}
            {latest.decision === 'accepted' ? 'accepted' : 'rejected'} by{' '}
            {latest.actor_kind === 'operator' ? 'you' : latest.actor}
          </>
        ) : null}
      </div>
      <Expander open={open}>
        <div className="aw-evidence-body">
          {history.isError ? (
            <p className="aw-tl-meta">This piece’s review history could not be read.</p>
          ) : null}
          <EvidenceReviews reviews={reviews} />
          <EvidenceProof piece={piece} open={open} />
        </div>
      </Expander>
    </li>
  )
}

export function EvidenceBrowser({
  focus,
  onFocus,
  onOpenTask,
}: {
  focus: string | null
  onFocus: (focus: string | null) => void
  onOpenTask: (taskId: string) => void
}) {
  const { data, isLoading, isError } = useProjectEvidence()
  const { data: taskPage, error: tasksError } = useTasks()
  const [state, setState] = useState<StateFilter>('all')
  const [grouping, setGrouping] = useState<Grouping>(focus?.startsWith('task-') ? 'task' : 'requirement')
  const [agent, setAgent] = useState('')
  const [query, setQuery] = useState('')

  const tasks = useMemo(
    () => new Map((taskPage?.tasks ?? []).map((task) => [task.id, task])),
    [taskPage],
  )
  const pieces = useMemo(() => data?.evidence ?? [], [data])
  const agents = useMemo(
    () => [...new Set(pieces.map((p) => (p.actor_kind === 'operator' ? 'you' : p.actor)))].sort(),
    [pieces],
  )
  const focused = useMemo(
    () =>
      focus
        ? pieces.filter((p) =>
            focus.startsWith('task-') ? p.task_id === focus : p.requirement?.identifier === focus,
          )
        : pieces,
    [pieces, focus],
  )
  const counts = useMemo(() => {
    const result: Record<StateFilter, number> = { all: focused.length, awaiting: 0, accepted: 0, rejected: 0 }
    for (const piece of focused) {
      if (piece.review_state in result) result[piece.review_state as StateFilter] += 1
    }
    return result
  }, [focused])
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return focused.filter((p) => {
      if (state !== 'all' && p.review_state !== state) return false
      if (agent && (p.actor_kind === 'operator' ? 'you' : p.actor) !== agent) return false
      if (!needle) return true
      return [p.summary, p.locator, p.requirement?.identifier, p.requirement?.statement, p.command]
        .filter(Boolean)
        .some((field) => (field as string).toLowerCase().includes(needle))
    })
  }, [focused, state, agent, query])
  // Newest first within each group, groups ordered by their newest piece: what changed last reads
  // first. The route returns oldest first; this view reverses it deliberately.
  const groups = useMemo(() => {
    const byKey = new Map<string, EvidencePiece[]>()
    for (const piece of [...visible].reverse()) {
      const key =
        grouping === 'task' ? piece.task_id ?? '—' : piece.requirement?.identifier ?? '—'
      const list = byKey.get(key) ?? []
      list.push(piece)
      byKey.set(key, list)
    }
    return [...byKey.entries()]
  }, [visible, grouping])

  const focusLabel = focus
    ? focus.startsWith('task-')
      ? tasks.get(focus)?.title ?? focus
      : focus
    : null
  let rowIndex = 0

  return (
    <div className="aw-evidence-page" data-testid="evidence-browser">
      <header className="aw-evidence-header">
        <div className="grid gap-1">
          <h1 className="text-[18px] font-semibold" style={{ color: 'var(--text)' }}>
            Evidence
          </h1>
          <p className="text-[12.5px]" style={{ color: 'var(--text-2)' }}>
            What agents recorded to show each requirement is met, and how the reviewing agent
            decided it.
          </p>
        </div>
        {focusLabel ? (
          <button
            type="button"
            className="aw-focus-chip"
            onClick={() => onFocus(null)}
            data-testid="evidence-focus"
            title="Show all evidence"
          >
            <span>{focusLabel}</span>
            <Icon name="close" size={12} aria-hidden="true" />
          </button>
        ) : null}
      </header>

      <div className="aw-evidence-toolbar">
        <div className="aw-filter-chips" role="group" aria-label="Filter by state">
          {(Object.keys(STATE_LABEL) as StateFilter[]).map((key) => (
            <button
              key={key}
              type="button"
              aria-pressed={state === key}
              onClick={() => setState(key)}
              className={`aw-filter-chip tone-${key === 'all' ? 'neutral' : evidenceTone(key)}`}
              data-testid={`evidence-filter-${key}`}
            >
              {STATE_LABEL[key]} <span className="aw-filter-count">{counts[key]}</span>
            </button>
          ))}
        </div>
        <div className="aw-evidence-controls">
          <label className="aw-search">
            <Icon name="search" size={13} aria-hidden="true" />
            <input
              id="evidence-search"
              type="search"
              placeholder="Search summaries, commands, requirements"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              data-testid="evidence-search"
            />
          </label>
          <select
            id="evidence-agent"
            aria-label="Filter by agent"
            value={agent}
            onChange={(event) => setAgent(event.target.value)}
            className="aw-select"
            data-testid="evidence-agent"
          >
            <option value="">Every agent</option>
            {agents.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <div className="aw-segmented aw-segmented-small" role="group" aria-label="Group by">
            <span
              className="aw-segmented-thumb"
              aria-hidden="true"
              style={{
                width: 'calc(50% - 2px)',
                transform: `translateX(${grouping === 'task' ? 100 : 0}%)`,
              }}
            />
            <button type="button" aria-pressed={grouping === 'requirement'} onClick={() => setGrouping('requirement')}>
              Requirement
            </button>
            <button type="button" aria-pressed={grouping === 'task'} onClick={() => setGrouping('task')} data-testid="evidence-group-task">
              Task
            </button>
          </div>
        </div>
      </div>

      {tasksError ? (
        <p className="aw-tl-meta">Task names could not be read, so tasks are shown by id.</p>
      ) : null}
      {isLoading ? (
        <div className="grid gap-3" aria-label="Loading evidence">
          {[80, 65, 72, 50].map((width, index) => (
            <div key={index} className="aw-skeleton" style={{ width: `${width}%`, height: 14 }} />
          ))}
        </div>
      ) : isError ? (
        <p className="aw-callout tone-red">The Hub did not answer for this project’s evidence. Try again in a moment.</p>
      ) : groups.length === 0 ? (
        <div className="aw-evidence-empty" data-testid="evidence-empty">
          <Icon name="fact_check" size={22} aria-hidden="true" />
          <p>
            {pieces.length === 0
              ? 'No evidence yet. It appears here as agents record what demonstrates each requirement.'
              : 'Nothing matches these filters.'}
          </p>
        </div>
      ) : (
        <div className="grid gap-6">
          {groups.map(([key, list]) => {
            const task = grouping === 'task' ? tasks.get(key) : undefined
            const statement = grouping === 'requirement' ? list[0]?.requirement?.statement : null
            return (
              <section key={key} className="aw-evidence-group" data-testid={`evidence-group-${key}`}>
                <div className="aw-evidence-group-head">
                  {grouping === 'requirement' ? (
                    <>
                      <span className="aw-evidence-req">{key}</span>
                      {statement ? <span className="aw-evidence-statement">{statement}</span> : null}
                    </>
                  ) : (
                    <>
                      <button type="button" className="aw-inline-link aw-group-title" onClick={() => task && onOpenTask(task.id)}>
                        {task?.title ?? key}
                      </button>
                      {task ? <StatePill tone={statusTone(task.status)}>{task.status.replace(/_/g, ' ')}</StatePill> : null}
                    </>
                  )}
                  <span className="aw-tl-meta" style={{ marginLeft: 'auto' }}>
                    {list.length} {list.length === 1 ? 'piece' : 'pieces'}
                  </span>
                </div>
                <ol className="aw-evidence-list">
                  {list.map((piece) => (
                    <PieceRow
                      key={piece.id}
                      piece={piece}
                      index={rowIndex++}
                      taskTitle={piece.task_id ? tasks.get(piece.task_id)?.title ?? null : null}
                      onOpenTask={onOpenTask}
                      showRequirement={grouping === 'task'}
                    />
                  ))}
                </ol>
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}
