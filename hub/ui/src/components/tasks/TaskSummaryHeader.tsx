import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import type { Task, TaskStory } from '@/api/tasks'
import { agentColorVars } from '@/lib/agentColors'
import { formatDateTime, formatMoney } from '@/lib/format'
import { builderAndReviewer, formatStageAge } from '@/lib/taskStage'
import { TONE_COLOR, stageVisual, waitsWording } from '@/lib/taskStageVisual'
import { StageThread } from './StageThread'
import '@/styles/task-redesign.css'

/** The top of the task drawer, redesigned (`task-card-and-story-redesign`): where the task stands,
 *  as a glyph, a word and the labelled thread; who built and who reviews it; then four numbers
 *  (cost, runs, evidence accepted, checks). The description, branch, commits, requirements and
 *  criteria follow it in the drawer's body, as today (FR-4). */
export function TaskSummaryHeader({
  task,
  summary,
  specTag,
  failedChecks,
  colorOf,
  now,
}: {
  task: Task
  summary?: TaskStory['summary'] | null
  specTag?: string
  failedChecks?: number
  colorOf?: (agent: string) => number | null | undefined
  now?: Date
}) {
  const visual = stageVisual(task.stage)
  const clock = now ?? new Date()
  const people = builderAndReviewer(task)
  const builder = people.builder ?? task.builder ?? task.assignee ?? null
  const evidence = summary?.evidence
  const evidenceTotal = evidence ? evidence.accepted + evidence.rejected + evidence.awaiting + (evidence.held ?? 0) : 0
  return (
    <section className="aw-tsum" style={{ '--stage-tone': TONE_COLOR[visual.tone] } as React.CSSProperties} data-tone={visual.tone}>
      <div className="aw-tsum-stage">
        <span key={task.stage ?? 'none'} className="aw-tsum-glyph" data-moving={visual.moving ? 'true' : 'false'}>
          <Icon name={visual.glyph} size={18} />
        </span>
        <div className="aw-tsum-stage-text">
          <span className="aw-tsum-word">{visual.word}</span>
          <span className="aw-tsum-since">
            {task.stage_since ? (
              <span title={formatDateTime(task.stage_since, clock)}>for {formatStageAge(task.stage_since, clock)}</span>
            ) : null}
            {task.stage_waits_on ? <span> · {waitsWording(task.stage, task.stage_waits_on)}</span> : null}
          </span>
        </div>
        {specTag ? <span className="aw-tcard-tag aw-tsum-tag">{specTag}</span> : null}
      </div>

      <StageThread stage={task.stage} />

      <div className="aw-tsum-people">
        <Person role="Built by" name={builder} index={builder ? colorOf?.(builder) : null} />
        <Person role="Reviewed by" name={people.reviewer ?? task.checker ?? null} index={people.reviewer ? colorOf?.(people.reviewer) : task.checker ? colorOf?.(task.checker) : null} pending={!people.reviewer && Boolean(task.checker)} />
      </div>

      <dl className="aw-tsum-stats">
        <div>
          <dt>Cost</dt>
          <dd>{summary?.cost_usd != null ? formatMoney(summary.cost_usd) : '—'}</dd>
        </div>
        <div>
          <dt>Runs</dt>
          <dd>{summary ? summary.runs : '—'}</dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd data-state={evidence && evidence.rejected > 0 ? 'failed' : evidence && evidenceTotal > 0 && evidence.accepted === evidenceTotal ? 'done' : 'idle'}>
            {evidence && evidenceTotal > 0 ? `${evidence.accepted}/${evidenceTotal} accepted` : 'none yet'}
          </dd>
        </div>
        <div>
          <dt>Checks</dt>
          <dd data-state={failedChecks ? 'failed' : 'idle'}>
            {failedChecks ? (
              <>
                <Icon name="x" size={11} /> {failedChecks} failed
              </>
            ) : (
              'no failures'
            )}
          </dd>
        </div>
      </dl>
    </section>
  )
}

function Person({ role, name, index, pending }: { role: string; name: string | null; index: number | null | undefined; pending?: boolean }) {
  const color = agentColorVars(index)
  return (
    <div className="aw-tsum-person">
      <span className="aw-tsum-role">{role}</span>
      {name ? (
        <span className="aw-tsum-name" style={{ color: color.accent }}>
          <span className="aw-tcard-agent-dot" style={{ background: color.accent }} />
          {name}
          {pending ? <span className="aw-tsum-pending">next</span> : null}
        </span>
      ) : (
        <span className="aw-tsum-nobody">nobody yet</span>
      )}
    </div>
  )
}
