import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { MenuSelect } from '@/components/ui/menu'
import { Segmented } from '@/components/ui/segmented'
import { agentColorVars } from '@/lib/agentColors'
import { formatMoney } from '@/lib/format'
import {
  groupItems,
  matchesFilter,
  PHASE_LABEL,
  summaryLine,
  type RunningFilter,
  type RunningItem,
  type RunningKind,
  type RunningKindFilter,
} from './runningModel'
import '@/styles/running-panel.css'

const KIND_ICON: Record<RunningKind, string> = { build: 'hammer', loop: 'sync', job: 'schedule' }
const KIND_LABEL: Record<RunningKind, string> = { build: 'Build', loop: 'Loop', job: 'Job' }

const KIND_OPTIONS = [
  { value: 'any', label: 'Everything' },
  { value: 'build', label: 'Builds', icon: 'hammer' },
  { value: 'loop', label: 'Loops', icon: 'sync' },
  { value: 'job', label: 'Jobs', icon: 'schedule' },
] as const

/** How many workers a row lists before it says "and N more". */
const WORKERS_SHOWN = 2

export interface RunningTabProps {
  items: RunningItem[]
  colorIndexOf: (agent: string) => number | null | undefined
  /** A build opens its document at its builds, a loop its record, a job the Jobs page. */
  onOpen: (item: RunningItem) => void
  /** A `needs-you` row's action: the question to answer, or the stall to look at. */
  onAttend: (item: RunningItem) => void
}

/** The side panel's Running tab: every build, loop and scheduled job, what needs the operator first. */
export function RunningTab({ items, colorIndexOf, onOpen, onAttend }: RunningTabProps) {
  const [filter, setFilter] = React.useState<RunningFilter>('now')
  const [kind, setKind] = React.useState<RunningKindFilter>('any')
  const count = (f: RunningFilter) => items.filter((i) => matchesFilter(i, f, kind)).length
  const shown = items.filter((i) => matchesFilter(i, filter, kind))
  const groups = groupItems(shown)

  return (
    <div className="aw-run" data-testid="running-tab">
      <div className="aw-run-head">
        <p className="aw-run-summary">{summaryLine(items)}</p>
        <div className="aw-run-filters">
          <Segmented<RunningFilter>
            label="Show"
            size="xs"
            value={filter}
            onChange={setFilter}
            options={[
              { value: 'now', label: 'Now', count: count('now') || undefined },
              { value: 'finished', label: 'Finished', count: count('finished') || undefined },
              { value: 'all', label: 'All' },
            ]}
          />
          <MenuSelect<RunningKindFilter>
            label="Kind of work"
            value={kind}
            onChange={setKind}
            maxWidth={150}
            options={KIND_OPTIONS.map((o) => ({ ...o, icon: 'icon' in o ? <Icon name={o.icon} size={14} /> : undefined }))}
          />
        </div>
      </div>

      <div className="aw-run-scroll">
        {groups.length === 0 ? (
          <div className="aw-run-empty">
            <span className="aw-run-empty-icon">
              <Icon name={filter === 'finished' ? 'check_circle' : 'circle_dashed'} size={18} />
            </span>
            <p>{filter === 'finished' ? 'Nothing has finished yet.' : 'Nothing is running or scheduled.'}</p>
            <p className="aw-run-empty-hint">Builds start from an approved spec; loops and jobs from the Jobs page.</p>
          </div>
        ) : (
          groups.map((group) => (
            <section key={group.phase} className="aw-run-group" data-phase={group.phase} aria-label={PHASE_LABEL[group.phase]}>
              <h3 className="aw-run-group-title">
                {PHASE_LABEL[group.phase]}
                <span className="aw-run-group-count">{group.items.length}</span>
              </h3>
              <ul className="aw-run-list">
                {group.items.map((item) => (
                  <RunningRow key={item.id} item={item} colorIndexOf={colorIndexOf} onOpen={onOpen} onAttend={onAttend} />
                ))}
              </ul>
            </section>
          ))
        )}
      </div>
    </div>
  )
}

function RunningRow({ item, colorIndexOf, onOpen, onAttend }: { item: RunningItem } & Omit<RunningTabProps, 'items'>) {
  const extra = item.workers.length - WORKERS_SHOWN
  return (
    <li className="aw-run-item" data-phase={item.phase}>
      <button type="button" data-slot="running-row" className="aw-run-row" onClick={() => onOpen(item)} title={`Open ${item.title}`}>
        <span className="aw-run-icon" aria-hidden="true">
          <Icon name={KIND_ICON[item.kind]} size={15} />
        </span>
        <span className="aw-run-main">
          <span className="aw-run-line">
            <span className="aw-run-title">{item.title}</span>
            <span className="aw-run-when">{item.when}</span>
          </span>
          <span className="aw-run-meta">
            <span className="aw-run-kind">{KIND_LABEL[item.kind]}</span>
            {item.progress ? (
              <span className="aw-run-progress" aria-label={`${item.progress.done} of ${item.progress.total} tasks done`}>
                <span className="aw-run-bar">
                  <span style={{ width: `${(item.progress.done / item.progress.total) * 100}%` }} />
                </span>
                <span className="aw-run-progress-label">
                  {item.progress.done}/{item.progress.total} tasks
                </span>
              </span>
            ) : null}
            {item.spentUsd != null && item.spentUsd > 0 ? <span className="aw-run-spent">{formatMoney(item.spentUsd)}</span> : null}
          </span>
          {item.workers.length > 0 ? (
            <span className="aw-run-workers">
              {item.workers.slice(0, WORKERS_SHOWN).map((w) => (
                <span key={`${w.agent}-${w.task}`} className="aw-run-worker" style={{ '--agent-accent': agentColorVars(colorIndexOf(w.agent)).accent } as React.CSSProperties}>
                  <span className="aw-agent-dot" />
                  <span className="aw-run-worker-agent">{w.agent}</span>
                  <span className="aw-run-worker-doing">{w.doing}</span>
                  <span className="aw-run-worker-task">{w.task}</span>
                </span>
              ))}
              {extra > 0 ? <span className="aw-run-more">and {extra} more</span> : null}
            </span>
          ) : item.status ? (
            <span className="aw-run-status">{item.status}</span>
          ) : null}
        </span>
      </button>
      {item.attention ? (
        <div className="aw-run-attention">
          <Icon name={item.attention.kind === 'question' ? 'help_circle' : 'alert_triangle'} size={14} />
          <span className="aw-run-attention-text">{item.attention.text}</span>
          <Button size="xs" variant="outline" onClick={() => onAttend(item)}>
            {item.attention.kind === 'question' ? 'Answer' : 'Look'}
          </Button>
        </div>
      ) : null}
    </li>
  )
}
