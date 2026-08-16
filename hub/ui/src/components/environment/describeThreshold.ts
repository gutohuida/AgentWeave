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
