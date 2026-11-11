import { useState } from 'react'
import { useAccounting, useUpdateTokenBudget } from '@/api/accounting'
import { useAgents } from '@/api/agents'
import { readableApiError } from '@/api/client'
import { useProjectSettings, useUpdateProjectSettings } from '@/api/projects'
import { useConfigStore } from '@/store/configStore'
import { SettingsLoading, SettingsNotice, SettingsPage } from '@/components/ui/settings'
import { toast } from '@/lib/toast'
import { AgentBudgetRow } from '../GeneralSettings'
import { BudgetsSettings } from '../BudgetsSettings'

/** Project settings → Budgets, on the Hub. The limit applies on change; each outcome (saved,
 *  removed, refused) is reported, never left looking like nothing happened. */
/** The agent budget is a project setting that sits here beside the token limit; it saves through
 *  the same route as the rest of the project's settings, on change. A save the Hub warned about
 *  (an agent budget below the agents already open, F728) or refused is said under the row. */
export function AgentBudget() {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: settings } = useProjectSettings(projectId ?? null)
  const update = useUpdateProjectSettings(projectId ?? '')
  const [warnings, setWarnings] = useState<string[]>([])
  const [refusal, setRefusal] = useState<string | null>(null)
  if (!settings) return null
  return (
    <>
      <AgentBudgetRow
        settings={settings}
        onChange={(patch, said) => {
          setRefusal(null)
          update.mutate(patch, {
            onSuccess: (saved) => {
              const savedWarnings = saved.warnings ?? []
              setWarnings(savedWarnings)
              toast({ title: said, tone: 'success', description: savedWarnings.length ? 'Saved, with a warning below.' : undefined })
            },
            onError: (error) => {
              const reason = readableApiError(error, 'The Hub did not return a reason.')
              setRefusal(reason)
              toast({ title: 'Not saved', description: reason, tone: 'error' })
            },
          })
        }}
      />
      {refusal ? (
        <SettingsNotice tone="error" title="That change was not saved." testId="settings-save-refusal">
          <p>{refusal}</p>
        </SettingsNotice>
      ) : null}
      {warnings.length ? (
        <SettingsNotice tone="warning" title="Saved, but worth knowing" testId="settings-save-warnings">
          <ul>
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </SettingsNotice>
      ) : null}
    </>
  )
}

export function BudgetsSection() {
  const { data, isLoading, error, refetch } = useAccounting()
  const { data: agents = [] } = useAgents()
  const update = useUpdateTokenBudget()

  // A failed read is said, with a Retry: never a skeleton that waits for an answer that is not
  // coming, and never rows that could be saved over settings that were never read.
  if (error && !data) {
    return (
      <SettingsPage icon="bar_chart" title="Budgets" description="What this project has used, and the limit that pauses agents working on their own.">
        <SettingsNotice tone="error" title="This project's usage could not be read." action={{ label: 'Retry', onClick: () => void refetch() }}>
          <p>{readableApiError(error, 'The Hub did not return a reason.')}</p>
        </SettingsNotice>
      </SettingsPage>
    )
  }
  if (isLoading || !data) {
    return (
      <SettingsPage icon="bar_chart" title="Budgets" description="What this project has used, and the limit that pauses agents working on their own.">
        <SettingsLoading label="Loading budgets" rows={3} />
      </SettingsPage>
    )
  }

  return (
    <BudgetsSettings
      accounting={data}
      agentBudget={<AgentBudget />}
      agentColor={(name) => agents.find((agent) => agent.name === name)?.color_index}
      saving={update.isPending}
      notices={
        update.isError ? (
          <SettingsNotice tone="error" title="The limit was not saved.">
            <p>{readableApiError(update.error, 'The budget could not be saved.')}</p>
          </SettingsNotice>
        ) : null
      }
      onSetLimit={(tokens, said) =>
        update.mutate(tokens, {
          onSuccess: () => toast({ title: said, tone: 'success' }),
          onError: (error) => toast({ title: 'Not saved', description: readableApiError(error, 'The budget could not be saved.'), tone: 'error' }),
        })
      }
    />
  )
}
