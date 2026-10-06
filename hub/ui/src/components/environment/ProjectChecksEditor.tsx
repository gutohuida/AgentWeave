import type { ProjectCheck } from '@/api/projects'
import { Button } from '@/components/ui/button'

const field = 'control-field block px-2 py-1.5 text-xs'

/**
 * The project's checks, in order (`approval-runs-the-projects-checks`): what the Hub runs on the
 * work a task's approval would merge. Edits the list only; the settings form saves it.
 */
export function ProjectChecksEditor({
  checks,
  onChange,
}: {
  checks: ProjectCheck[]
  onChange: (checks: ProjectCheck[]) => void
}) {
  const update = (index: number, patch: Partial<ProjectCheck>) =>
    onChange(checks.map((check, at) => (at === index ? { ...check, ...patch } : check)))
  const move = (index: number, by: number) => {
    const next = [...checks]
    const [item] = next.splice(index, 1)
    next.splice(index + by, 0, item)
    onChange(next)
  }

  return (
    <div className="space-y-2 w-full" data-testid="project-checks-editor">
      {checks.map((check, index) => (
        <div key={index} className="flex items-center gap-1.5">
          <input
            aria-label={`Check ${index + 1} name`}
            value={check.name}
            placeholder="name"
            onChange={(event) => update(index, { name: event.target.value })}
            className={`${field} w-24`}
          />
          <input
            aria-label={`Check ${index + 1} command`}
            value={check.command}
            placeholder="py -3.11 -m pytest -q"
            onChange={(event) => update(index, { command: event.target.value })}
            className={`${field} flex-1 font-mono`}
          />
          <input
            aria-label={`Check ${index + 1} timeout in seconds`}
            type="number"
            min={10}
            max={3600}
            value={check.timeout_seconds}
            onChange={(event) => update(index, { timeout_seconds: Number(event.target.value) })}
            className={`${field} w-20`}
          />
          <Button type="button" variant="ghost" size="sm" aria-label={`Move check ${index + 1} up`} disabled={index === 0} onClick={() => move(index, -1)}>↑</Button>
          <Button type="button" variant="ghost" size="sm" aria-label={`Move check ${index + 1} down`} disabled={index === checks.length - 1} onClick={() => move(index, 1)}>↓</Button>
          <Button type="button" variant="ghost" size="sm" aria-label={`Remove check ${index + 1}`} onClick={() => onChange(checks.filter((_, at) => at !== index))}>✕</Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onChange([...checks, { name: '', command: '', timeout_seconds: 900 }])}
      >
        Add check
      </Button>
    </div>
  )
}
