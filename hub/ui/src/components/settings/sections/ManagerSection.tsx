import * as React from 'react'
import { useProjectConversations } from '@/api/agentChat'
import { readableApiError } from '@/api/client'
import { isNoManager, useManagerJobs, useManagerRun, useManagerRunLog, useUpdateManagerJob } from '@/api/manager'
import { useModelCatalog } from '@/api/modelCatalog'
import { useRunners } from '@/api/runners'
import { useVaultMap } from '@/api/vault'
import { SettingsLoading, SettingsNotice, SettingsPage } from '@/components/ui/settings'
import { runnerModelPart } from '@/lib/runnerLabel'
import { toast } from '@/lib/toast'
import { useConfigStore } from '@/store/configStore'
import { ManagerSettings } from '../ManagerSettings'

const DESCRIPTION = 'Work the Hub does in the background with a model. Each job runs only while it is on, on the runner and model you choose for it.'

/** What a run worked on, in words (F719): a conversation by its title, a vault entry by its name
 *  with its id kept (two entries may share a name), a document or report by its path, a mender's
 *  stall by the reason it was woken. */
function runSubject(
  run: { subject?: Record<string, unknown> | null },
  entryNames: Map<string, string>,
  conversationTitles: Map<string, string>,
): string | null {
  const subject = run.subject
  if (!subject) return null
  const text = (key: string) => (typeof subject[key] === 'string' && subject[key] ? (subject[key] as string) : null)
  const entry = (id: string) => {
    const name = entryNames.get(id)
    return name ? `"${name}" (${id})` : id
  }
  const parts: string[] = []
  const source = text('source')
  const document = text('document')
  const report = text('report')
  const on = text('entry')
  const conversation = text('conversation_id')
  const reason = text('reason')
  if (source) parts.push(`source ${entry(source)}`)
  if (document) parts.push(`document ${document}`)
  if (report) parts.push(`report ${report}`)
  if (on) parts.push(`on ${entry(on)}`)
  if (conversation) parts.push(conversationTitles.get(conversation) ?? `thread ${conversation}`)
  if (reason) parts.push(reason)
  return parts.length ? parts.join(' ') : null
}

/** Project settings → Manager, on the Hub. Each control saves on change, sending only what it
 *  changed. A Hub that predates the manager answers its routes 404, which reads as a state. */
export function ManagerSection({
  run = null,
  onOpenRun,
  onOpenConversation,
}: {
  /** The run the location names (`run=<run_id>`): its detail opens. */
  run?: string | null
  /** A row's link, or the detail's Close (null): moves the location. */
  onOpenRun?: (runId: string | null) => void
  /** A mender row's link to the thread it ran in. */
  onOpenConversation?: (conversationId: string) => void
}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const jobs = useManagerJobs()
  const [job, setJob] = React.useState<string | null>(null)
  const runLog = useManagerRunLog(job)
  const opened = useManagerRun(run)
  const { data: runners = [], error: runnersError } = useRunners()
  const { data: catalog, error: catalogError } = useModelCatalog()
  const update = useUpdateManagerJob()
  const { data: vaultEntries, error: vaultError } = useVaultMap()
  const { data: conversations } = useProjectConversations(projectId ?? null)
  const entryNames = new Map((vaultEntries ?? []).map((entry) => [entry.id, entry.name]))
  const conversationTitles = new Map(
    (conversations?.conversations ?? []).filter((c) => c.title?.trim()).map((c) => [c.id, c.title!.trim()]),
  )

  if (isNoManager(jobs.error) || isNoManager(runLog.error)) {
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
      log={
        runLog.data
          ? {
              runs: runLog.data.pages.flatMap((page) => page.runs),
              totals: runLog.data.pages[0]?.totals ?? {},
              hasMore: !!runLog.hasNextPage,
              job,
              onJob: setJob,
              onShowOlder: () => void runLog.fetchNextPage(),
              loadingOlder: runLog.isFetchingNextPage,
            }
          : undefined
      }
      logError={runLog.error ? readableApiError(runLog.error, "Could not read the manager's run log.") : null}
      detail={
        run
          ? {
              runId: run,
              run: opened.data,
              error: opened.error ? `Could not read run ${run}: ${readableApiError(opened.error, 'the Hub did not answer.')}` : null,
              onClose: () => onOpenRun?.(null),
            }
          : null
      }
      onOpenRun={(runId) => onOpenRun?.(runId)}
      onOpenConversation={onOpenConversation}
      runners={runners}
      modelsFor={(runner) => catalog?.providers.find((p) => p.provider === runner?.cli)?.models ?? []}
      modelPart={(runner) => runnerModelPart(runner, catalog)}
      subjectLabel={(item) => runSubject(item, entryNames, conversationTitles)}
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
              <p>{readableApiError(vaultError, 'The vault could not be read')}, so vault entries in the run log are named by id.</p>
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
