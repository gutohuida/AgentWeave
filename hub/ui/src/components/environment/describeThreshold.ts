/**
 * The threshold in both readings, where both are knowable.
 *
 * An operator setting one unit is reasoning about the other; making them work it out is how a
 * threshold ends up somewhere it will never fire. Mirrors `checkpoint_policy.describe_threshold`;
 * a test pins the two against the same examples.
 */
export function describeThreshold(
  mode: string | null,
  value: number | null,
  contextWindow: number | null,
): string {
  if (!mode || value === null) return ''
  if (mode === 'percent') {
    if (!contextWindow) return `${value}%`
    return `${value}% — ${Math.round((contextWindow * value) / 100 / 1000)}k of ${Math.round(contextWindow / 1000)}k`
  }
  const thousands = `${Math.round(value / 1000)}k`
  if (!contextWindow) return thousands
  return `${thousands} — ${Math.round((value / contextWindow) * 100)}% of ${Math.round(contextWindow / 1000)}k`
}

const RUNNER_NAMES: Record<string, string> = { claude: 'Claude', codex: 'Codex', copilot: 'Copilot' }

/** The point a runner's own compaction leaves for a final warning (`checkpoint_policy`'s C − 3). */
export function finalWarningPercent(compactionPercent: number): number {
  return compactionPercent - 3
}

/**
 * Where an agent's checkpoint actually fires, when that differs from what is configured
 * (`a-copilot-run-shows-its-credits` D10). `mode`/`value` are the agent's effective threshold: its
 * own override, else the project's. Null when there is nothing to say: a runner compacting at the
 * default 95 with a threshold at or below its final warning, or no bound runner at all.
 *
 * - A percent threshold past the final warning is lowered to it, for every runner (Q7 (b)).
 * - A token threshold is lowered only for a runner compacting below 95 (Q7 (b)): the policy
 *   cannot compare tokens with a percent, so the line states both.
 * - Otherwise a runner compacting below 95 still says where its checkpoint fires at the latest.
 */
export function runnerCeilingNote(
  compactionPercent: number | null | undefined,
  mode: string | null | undefined,
  value: number | null | undefined,
  runner?: string | null,
): string | null {
  if (typeof compactionPercent !== 'number') return null
  const ceiling = finalWarningPercent(compactionPercent)
  const who = (runner && RUNNER_NAMES[runner]) || 'Its runner'
  const configured = typeof value === 'number' ? value : null
  if (mode === 'percent' && configured !== null && configured > ceiling) {
    return `This agent's threshold of ${configured}% is lowered to ${ceiling}%: ${who} compacts at about ${compactionPercent}% of its window.`
  }
  if (compactionPercent >= 95) return null
  if (mode === 'tokens' && configured !== null) {
    return `This agent's checkpoint fires at ${configured} tokens or at ${ceiling}% of its window, whichever comes first.`
  }
  return `${who} compacts at about ${compactionPercent}% of its window. This agent's checkpoint fires by ${ceiling}% at the latest.`
}

/**
 * The project panel's lines (D10): one per compaction point whose final warning is below the
 * project's percent threshold, naming the agents it applies to. A token threshold or none gives
 * nothing here; each agent's own settings state that case.
 */
export function projectCeilingNotes(
  mode: string | null | undefined,
  value: number | null | undefined,
  agents: ReadonlyArray<{ name: string; checkpoint_compaction_percent?: number | null }>,
): string[] {
  if (mode !== 'percent' || typeof value !== 'number') return []
  const byPoint = new Map<number, string[]>()
  for (const agent of agents) {
    const point = agent.checkpoint_compaction_percent
    if (typeof point !== 'number' || value <= finalWarningPercent(point)) continue
    byPoint.set(point, [...(byPoint.get(point) ?? []), agent.name])
  }
  return [...byPoint.entries()]
    .sort(([a], [b]) => a - b)
    .map(
      ([point, names]) =>
        `Lowered to ${finalWarningPercent(point)}% for agents on a runner that compacts at about ${point}% (${names.join(', ')}).`,
    )
}
