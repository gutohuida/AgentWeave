import * as React from 'react'
import { useCharters } from '@/api/charters'
import { readableApiError } from '@/api/client'
import { useCreateOfferedProfiles } from '@/api/projects'
import { useRunners } from '@/api/runners'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { MenuSelect } from '@/components/ui/menu'
import { Field } from '@/components/ui/settings'
import { environmentDestination, goTo } from '@/lib/navigation'
import { toast } from '@/lib/toast'

/**
 * The setup offer (`profiles-threads-and-builds-everywhere` D6, FR-8): a builder and a checker,
 * named by the operator, each with a runner of the project's and, if wanted, a charter. One
 * profile can never check its own work, so a first build needs two; nothing is created until
 * Create both is pressed, and then both are created or neither is.
 *
 * No charter is preselected and none is required. No runner is preselected either: which runner
 * builds and which checks is the operator's choice, not the first row's.
 */

const NAME_RE = /^[a-zA-Z0-9_-]{1,32}$/
const NO_CHARTER = ''

type Role = 'builder' | 'checker'

interface Draft {
  name: string
  charterId: string
  runnerId: string
}

const ROLE_LABEL: Record<Role, string> = { builder: 'Builder', checker: 'Checker' }
const ROLE_HINT: Record<Role, string> = {
  builder: 'Does the work of each task.',
  checker: 'Reviews what the builder finished, and approves it or sends it back.',
}

function nameProblem(name: string): string | null {
  if (!name.trim()) return 'Give it a name.'
  if (!NAME_RE.test(name.trim())) return 'Use 1–32 letters, numbers, hyphens or underscores.'
  return null
}

function ProfileFields({
  role,
  draft,
  onChange,
  runnerOptions,
  charterOptions,
  sameName,
}: {
  role: Role
  draft: Draft
  onChange: (next: Draft) => void
  runnerOptions: { value: string; label: string }[]
  charterOptions: { value: string; label: string }[]
  sameName: boolean
}) {
  const label = ROLE_LABEL[role]
  const nameError = draft.name ? nameProblem(draft.name) : null
  return (
    <fieldset className="mt-3 first:mt-0" data-testid={`setup-profiles-${role}`}>
      <legend className="text-xs font-semibold" style={{ color: 'var(--text)' }}>
        {label}
      </legend>
      <p className="text-xs" style={{ color: 'var(--text-2)' }}>
        {ROLE_HINT[role]}
      </p>
      <div className="mt-2 grid gap-2">
        <Field
          label="Name"
          htmlFor={`setup-profiles-${role}-name`}
          error={nameError ?? (sameName && role === 'checker' ? 'The builder already has this name.' : null)}
        >
          <Input
            id={`setup-profiles-${role}-name`}
            value={draft.name}
            aria-invalid={Boolean(nameError) || sameName}
            onChange={(event) => onChange({ ...draft, name: event.target.value })}
          />
        </Field>
        <Field label="Runner" htmlFor={`setup-profiles-${role}-runner`} hint="What it runs on: a coding CLI and a model.">
          <MenuSelect
            id={`setup-profiles-${role}-runner`}
            testId={`setup-profiles-${role}-runner`}
            label={`${label} runner`}
            value={draft.runnerId}
            onChange={(runnerId) => onChange({ ...draft, runnerId })}
            maxWidth={9999}
            placeholder="Choose a runner…"
            options={runnerOptions}
          />
        </Field>
        <Field label="Charter (optional)" htmlFor={`setup-profiles-${role}-charter`} hint="Instructions added to every turn it takes.">
          <MenuSelect
            id={`setup-profiles-${role}-charter`}
            testId={`setup-profiles-${role}-charter`}
            label={`${label} charter`}
            value={draft.charterId}
            onChange={(charterId) => onChange({ ...draft, charterId })}
            maxWidth={9999}
            options={[{ value: NO_CHARTER, label: 'No charter' }, ...charterOptions]}
          />
        </Field>
      </div>
    </fieldset>
  )
}

function useOfferBody({ projectId, onDone }: { projectId: string; onDone: () => void }) {
  const runners = useRunners()
  const charters = useCharters()
  const create = useCreateOfferedProfiles(projectId)
  const [builder, setBuilder] = React.useState<Draft>({ name: 'Builder', charterId: NO_CHARTER, runnerId: '' })
  const [checker, setChecker] = React.useState<Draft>({ name: 'Checker', charterId: NO_CHARTER, runnerId: '' })

  const sameName = !!builder.name.trim() && builder.name.trim().toLowerCase() === checker.name.trim().toLowerCase()
  const ready =
    !nameProblem(builder.name) && !nameProblem(checker.name) && !sameName && !!builder.runnerId && !!checker.runnerId

  const submit = () => {
    if (!ready || create.isPending) return
    const entry = (draft: Draft) => ({
      name: draft.name.trim(),
      charter_id: draft.charterId === NO_CHARTER ? null : draft.charterId,
      runner_id: draft.runnerId,
    })
    create.mutate(
      { builder: entry(builder), checker: entry(checker) },
      {
        onSuccess: (created) => {
          toast({ title: `${created.builder.name} and ${created.checker.name} are ready`, tone: 'success' })
          onDone()
        },
      },
    )
  }

  let body: React.ReactNode
  if (runners.isLoading || charters.isLoading) {
    body = (
      <p className="text-xs" role="status" style={{ color: 'var(--text-2)' }}>
        Reading the project’s runners and charters…
      </p>
    )
  } else if (runners.error || charters.error) {
    body = (
      <div role="alert" className="text-xs" data-testid="setup-profiles-read-error" style={{ color: 'var(--text)' }}>
        <p>{readableApiError(runners.error ?? charters.error, 'Could not read the project’s runners and charters.')}</p>
        <Button
          className="mt-2"
          variant="outline"
          size="sm"
          onClick={() => {
            void runners.refetch()
            void charters.refetch()
          }}
        >
          Try again
        </Button>
      </div>
    )
  } else if (!(runners.data ?? []).length) {
    body = (
      <div className="text-xs" data-testid="setup-profiles-no-runners" style={{ color: 'var(--text)' }}>
        <p>This project has no runners yet. Each profile needs one to run its turns.</p>
        <Button
          className="mt-2"
          variant="outline"
          size="sm"
          onClick={() => {
            onDone()
            goTo(environmentDestination(projectId, 'general'))
          }}
        >
          Add a runner in Project settings
        </Button>
      </div>
    )
  } else {
    const runnerOptions = (runners.data ?? []).map((runner) => ({ value: runner.id, label: runner.name }))
    const charterOptions = (charters.data ?? []).map((charter) => ({ value: charter.id, label: charter.name }))
    body = (
      <form
        id="setup-profiles-form"
        onSubmit={(event) => {
          event.preventDefault()
          submit()
        }}
      >
        <ProfileFields
          role="builder"
          draft={builder}
          onChange={setBuilder}
          runnerOptions={runnerOptions}
          charterOptions={charterOptions}
          sameName={false}
        />
        <ProfileFields
          role="checker"
          draft={checker}
          onChange={setChecker}
          runnerOptions={runnerOptions}
          charterOptions={charterOptions}
          sameName={sameName}
        />
        {create.error ? (
          <p role="alert" className="mt-3 text-xs" data-testid="setup-profiles-error" style={{ color: 'var(--red)' }}>
            {readableApiError(create.error, 'The profiles could not be created.')}
          </p>
        ) : null}
      </form>
    )
  }

  return { body, ready, pending: create.isPending }
}

export function SetupProfilesDialog({
  projectId,
  open,
  onOpenChange,
}: {
  projectId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open ? <OpenDialog projectId={projectId} onDone={() => onOpenChange(false)} /> : null}
    </Dialog>
  )
}

/** Mounted only while open, so each opening starts from the same defaults. */
function OpenDialog({ projectId, onDone }: { projectId: string; onDone: () => void }) {
  const { body, ready, pending } = useOfferBody({ projectId, onDone })
  return (
    <DialogContent
      title="Add a builder and a checker"
      description="A build needs two profiles: one builds each task, and the other checks it. A profile never checks its own work."
      width={520}
      footer={
        <>
          <DialogClose asChild>
            <Button variant="ghost" size="sm">
              Cancel
            </Button>
          </DialogClose>
          <Button variant="primary" size="sm" type="submit" form="setup-profiles-form" disabled={!ready || pending}>
            {pending ? 'Creating…' : 'Create both'}
          </Button>
        </>
      }
    >
      {body}
    </DialogContent>
  )
}
