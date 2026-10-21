import { useAccounting, useUpdateTokenBudget } from '@/api/accounting'
import { useAgents } from '@/api/agents'
import { readableApiError } from '@/api/client'
import { SettingsLoading, SettingsNotice, SettingsPage } from '@/components/ui/settings'
import { toast } from '@/lib/toast'
import { BudgetsSettings } from '../BudgetsSettings'

/** Project settings → Budgets, on the Hub. The limit applies on change; each outcome (saved,
 *  removed, refused) is reported, never left looking like nothing happened. */
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
