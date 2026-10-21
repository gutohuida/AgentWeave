import { useProjectConversations } from '@/api/agentChat'
import { readableApiError } from '@/api/client'
import { isNoManager, useManagerActivity, useManagerJobs, useUpdateManagerJob, type ManagerFiring } from '@/api/manager'
import { useModelCatalog } from '@/api/modelCatalog'
import { useRunners } from '@/api/runners'
import { useVaultMap } from '@/api/vault'
import { SettingsLoading, SettingsNotice, SettingsPage } from '@/components/ui/settings'
import { runnerModelPart } from '@/lib/runnerLabel'
import { toast } from '@/lib/toast'
import { useConfigStore } from '@/store/configStore'
import { ManagerSettings } from '../ManagerSettings'

const DESCRIPTION = 'Work the Hub does in the background with a model. Each job runs only while it is on, on the runner and model you choose for it.'

/** What a firing worked on, in words (F719): a conversation by its title, a vault entry by its name
 *  with its id kept (two entries may share a name), a document or report by its path. */
function firingSubject(
  firing: ManagerFiring,
  entryNames: Map<string, string>,
  conversationTitles: Map<string, string>,
): string | null {
  const subject = firing.subject
  if (!subject) return null
  const entry = (id: string) => {
    const name = entryNames.get(id)
    return name ? `"${name}" (${id})` : id
  }
  const parts: string[] = []
  if (subject.source) parts.push(`source ${entry(subject.source)}`)
  if (subject.document) parts.push(`document ${subject.document}`)
  if (subject.report) parts.push(`report ${subject.report}`)
  if (subject.entry) parts.push(`on ${entry(subject.entry)}`)
  if (subject.conversation_id) parts.push(conversationTitles.get(subject.conversation_id) ?? `conversation ${subject.conversation_id}`)
  return parts.length ? parts.join(' ') : null
}

/** Project settings → Manager, on the Hub. Each control saves on change, sending only what it
 *  changed. A Hub that predates the manager answers its routes 404, which reads as a state. */
export function ManagerSection() {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const jobs = useManagerJobs()
  const activity = useManagerActivity()
  const { data: runners = [], error: runnersError } = useRunners()
  const { data: catalog, error: catalogError } = useModelCatalog()
  const update = useUpdateManagerJob()
  const { data: vaultEntries, error: vaultError } = useVaultMap()
  const { data: conversations } = useProjectConversations(projectId ?? null)
  const entryNames = new Map((vaultEntries ?? []).map((entry) => [entry.id, entry.name]))
  const conversationTitles = new Map(
    (conversations?.conversations ?? []).filter((c) => c.title?.trim()).map((c) => [c.id, c.title!.trim()]),
  )

  if (isNoManager(jobs.error) || isNoManager(activity.error)) {
    return (
      <SettingsPage icon="memory" title="Manager" description={DESCRIPTION}>
        <p className="aw-empty-line">This Hub has no manager yet. It arrives when the Hub is restarted on a version that has one.</p>
      </SettingsPage>
    )
  }
  if (jobs.error) {
    return (
      <SettingsPage icon="memory" title="Manager" description={DESCRIPTION}>
        <SettingsNotice tone="error" title="The background jobs could not be read." action={{ label: 'Retry', onClick: () => void jobs.refetch() }}>
          <p>{readableApiError(jobs.error, "Could not read this project's background jobs.")}</p>
        </SettingsNotice>
      </SettingsPage>
    )
  }
  if (!jobs.data) {
    return (
      <SettingsPage icon="memory" title="Manager" description={DESCRIPTION}>
        <SettingsLoading label="Loading background jobs" rows={3} />
      </SettingsPage>
    )
  }

  // Without the runners a menu cannot show the stored runner; without the catalog the models are
  // missing. Either way the choices are withheld rather than shown wrong.
  const controlsUnavailable = runnersError
    ? readableApiError(runnersError, "Could not read this project's runners, so the jobs' choices cannot be shown.")
    : catalogError
      ? readableApiError(catalogError, "Could not read the model catalog, so the jobs' choices cannot be shown.")
      : null

  return (
    <ManagerSettings
      jobs={jobs.data}
      firings={activity.data}
      firingsError={activity.error ? readableApiError(activity.error, "Could not read the manager's activity.") : null}
      runners={runners}
      modelsFor={(runner) => catalog?.providers.find((p) => p.provider === runner?.cli)?.models ?? []}
      modelPart={(runner) => runnerModelPart(runner, catalog)}
      subjectLabel={(firing) => firingSubject(firing, entryNames, conversationTitles)}
      controlsUnavailable={controlsUnavailable}
      now={new Date()}
      notices={
        <>
          {update.error ? (
            <SettingsNotice tone="error" title="That change was not saved.">
              <p>{readableApiError(update.error, 'Could not save that change.')}</p>
            </SettingsNotice>
          ) : null}
          {vaultError ? (
            <SettingsNotice tone="info">
              <p>{readableApiError(vaultError, 'The vault could not be read')}, so vault entries in the history are named by id.</p>
            </SettingsNotice>
          ) : null}
        </>
      }
      onChange={(key, input, said) =>
        update.mutate(
          { key, input },
          {
            onSuccess: () => toast({ title: said, tone: 'success' }),
            onError: (error) => toast({ title: 'Not saved', description: readableApiError(error, 'Could not save that change.'), tone: 'error' }),
          },
        )
      }
    />
  )
}
