import type { SpecTaskView } from '../model'
import { buildLevels } from '../model'
import { ThreadTaskCard, threadState, useChain } from './shared'

/** The build order as stages instead of lines: every task in a stage can run alongside the others in
 *  it, and each card names what it waits on as chips coloured by that task's state. */
export function BuildStages({ tasks }: { tasks: SpecTaskView[] }) {
  const levels = buildLevels(tasks)
  const { lit, bind } = useChain(tasks)
  const depth = Math.max(0, ...tasks.map((t) => levels.get(t.key) ?? 0))
  const stages = Array.from({ length: depth + 1 }, (_, i) => tasks.filter((t) => (levels.get(t.key) ?? 0) === i))

  return (
    <ol className="aw-st-stages">
      {stages.map((stage, i) => {
        const done = stage.filter((t) => t.status === 'approved').length
        const state = done === stage.length ? 'done' : stage.some((t) => threadState(t.status) !== 'waiting') ? 'active' : 'waiting'
        return (
          <li key={i} className="aw-st-stage" data-state={state}>
            <div className="aw-st-stage-head">
              <span className="aw-st-stage-mark" data-state={state}>{i + 1}</span>
              <span className="aw-st-stage-title">{i === 0 ? 'Starts first' : `Stage ${i + 1}`}</span>
              <span className="aw-sp-muted">
                {stage.length > 1 ? `${stage.length} tasks in parallel` : '1 task'} · {done} of {stage.length} done
              </span>
            </div>
            <ul className="aw-st-stage-grid" data-single={stage.length === 1 ? 'true' : undefined}>
              {stage.map((t) => (
                <li key={t.key} className="aw-sp-task aw-st-card" data-lit={lit(t.key)} tabIndex={0} {...bind(t.key)}>
                  <ThreadTaskCard task={t} all={tasks} afterChips />
                </li>
              ))}
            </ul>
          </li>
        )
      })}
    </ol>
  )
}
