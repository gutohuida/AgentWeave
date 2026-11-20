/** Built-in steps by what an operator calls them; the key stays in the title for a reference. */
const BUILT_IN_TITLES: Record<string, string> = {
  intake: 'Intake',
  requirements: 'Requirements',
  'requirements-and-acceptance': 'Requirements and acceptance',
  acceptance: 'Acceptance criteria',
  approach: 'Approach',
  tasks: 'Tasks',
  build: 'Build',
}

/** What the operator calls a step key (`intake` is "Intake"). */
export function stepKeyLabel(key: string): string {
  return BUILT_IN_TITLES[key] ?? key.replace(/-/g, ' ').replace(/^./, (c) => c.toUpperCase())
}
