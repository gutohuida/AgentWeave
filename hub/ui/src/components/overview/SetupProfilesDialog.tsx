import * as React from 'react'
import { useCharters } from '@/api/charters'
import { readableApiError } from '@/api/client'
import { useModelCatalog, type ProviderDescriptor } from '@/api/modelCatalog'
import { useCreateOfferedProfiles } from '@/api/projects'
import { useProviderLaunchability, type RunnerLaunchability } from '@/api/runners'
import { defaultModel, modelOptions, namePlaceholder, providerOptions } from '@/components/agents/pool/catalogOptions'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { MenuSelect } from '@/components/ui/menu'
import { Field } from '@/components/ui/settings'
import { toast } from '@/lib/toast'

/**
 * The setup offer (`profiles-threads-and-builds-everywhere` D6, FR-8): a builder and a checker,
 * named by the operator, each with a provider and one of its catalog models and, if wanted, a
 * charter. One profile can never check its own work, so a first build needs two; nothing is
 * created until Create both is pressed, and then both are created or neither is.
 *
 * The provider and model are chosen as Create profile chooses them
 * (`a-profile-s-pool-and-a-new-chat-can-use-any-model-of-any-provider`, FR-9): any catalog model,
 * whether or not a runner of the project uses it yet; the Hub reuses or makes the runner. No
 * charter is preselected and none is required. No provider is preselected either: what builds and
 * what checks is the operator's choice.
 */

const NAME_RE = /^[a-zA-Z0-9_-]{1,32}$/
const NO_CHARTER = ''

type Role = 'builder' | 'checker'

interface Draft {
  name: string
  charterId: string
  provider: string
  model: string
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
  providers,
  launchability,
  charterOptions,
  sameName,
}: {
  role: Role
  draft: Draft
  onChange: (next: Draft) => void
  providers: ProviderDescriptor[]
  /** Which providers can run here; undefined until known, or when the check failed, and then
   *  every provider is choosable and the Hub's refusal at creation names one that cannot run. */
  launchability: Record<string, RunnerLaunchability> | undefined
  charterOptions: { value: string; label: string }[]
  sameName: boolean
}) {
  const label = ROLE_LABEL[role]
  const provider = providers.find((p) => p.provider === draft.provider)
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
            placeholder={namePlaceholder(draft.provider, role)}
            aria-invalid={Boolean(nameError) || sameName}
            onChange={(event) => onChange({ ...draft, name: event.target.value })}
          />
        </Field>
        <Field label="Provider" htmlFor={`setup-profiles-${role}-provider`} hint="The coding CLI it runs on.">
          <MenuSelect
            id={`setup-profiles-${role}-provider`}
            testId={`setup-profiles-${role}-provider`}
            label={`${label} provider`}
            value={draft.provider}
            onChange={(next) => onChange({ ...draft, provider: next, model: defaultModel(providers.find((p) => p.provider === next)) })}
            maxWidth={9999}
            placeholder="Choose a provider…"
            options={providerOptions(providers, launchability)}
          />
        </Field>
        <Field label="Model" htmlFor={`setup-profiles-${role}-model`}>
          <MenuSelect
            id={`setup-profiles-${role}-model`}
            testId={`setup-profiles-${role}-model`}
            label={`${label} model`}
            value={draft.model}
            onChange={(model) => onChange({ ...draft, model })}
            maxWidth={9999}
            disabled={!provider}
            placeholder={provider ? 'Choose a model…' : 'Choose a provider first'}
            options={modelOptions(provider, { aliases: true })}
          />
        </Field>
        <Field label="Charter (optional)" htmlFor={`setup-profiles-${role}-charter`} hint="Instructions added to each of its runs.">
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
  const catalog = useModelCatalog()
  const launchability = useProviderLaunchability()
  const charters = useCharters()
  const create = useCreateOfferedProfiles(projectId)
  const [builder, setBuilder] = React.useState<Draft>({ name: 'Builder', charterId: NO_CHARTER, provider: '', model: '' })
  const [checker, setChecker] = React.useState<Draft>({ name: 'Checker', charterId: NO_CHARTER, provider: '', model: '' })

  const sameName = !!builder.name.trim() && builder.name.trim().toLowerCase() === checker.name.trim().toLowerCase()
  const ready =
    !nameProblem(builder.name) && !nameProblem(checker.name) && !sameName && !!builder.model && !!checker.model

  const submit = () => {
    if (!ready || create.isPending) return
    const entry = (draft: Draft) => ({
      name: draft.name.trim(),
      charter_id: draft.charterId === NO_CHARTER ? null : draft.charterId,
      provider: draft.provider,
      model: draft.model,
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
  if (catalog.isLoading || charters.isLoading) {
    body = (
      <p className="text-xs" role="status" style={{ color: 'var(--text-2)' }}>
        Reading the model catalog and the project’s charters…
      </p>
    )
  } else if (catalog.error || charters.error) {
    body = (
      <div role="alert" className="text-xs" data-testid="setup-profiles-read-error" style={{ color: 'var(--text)' }}>
        <p>{readableApiError(catalog.error ?? charters.error, 'Could not read the model catalog and the project’s charters.')}</p>
        <Button
          className="mt-2"
          variant="outline"
          size="sm"
          onClick={() => {
            void catalog.refetch()
            void charters.refetch()
          }}
        >
          Try again
        </Button>
      </div>
    )
  } else {
    const providers = catalog.data?.providers ?? []
    const runnable = launchability.data?.providers
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
          providers={providers}
          launchability={runnable}
          charterOptions={charterOptions}
          sameName={false}
        />
        <ProfileFields
          role="checker"
          draft={checker}
          onChange={setChecker}
          providers={providers}
          launchability={runnable}
          charterOptions={charterOptions}
          sameName={sameName}
        />
        {launchability.error ? (
          <p role="status" className="mt-3 text-xs" data-testid="setup-profiles-launchability-error" style={{ color: 'var(--text-2)' }}>
            Could not check which coding CLIs are installed, so every provider is listed.
          </p>
        ) : null}
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
