import { SettingsPage } from '@/components/ui/settings'
import { RunList } from '@/components/traces/RunList'

/**
 * A profile's runs (profiles-threads-and-builds-everywhere FR-6): every run of the profile, the
 * runs under names folded into it included, newest first, each opening its trace and conversation.
 * Threads and builds leave the sidebar; this is where a profile's past work is found again.
 */
export function AgentRunsPage({ agent }: { agent: string }) {
  return (
    <SettingsPage
      icon="timeline"
      title="Runs"
      description={`Everything ${agent} has run, newest first: its threads, task builds, reviews, mender turns, jobs and messages, and the runs of any name folded into it. Choose one to see its trace.`}
    >
      <RunList
        filters={{ profile: agent }}
        label={`Runs of ${agent}`}
        emptyText={`${agent} has not run yet. Its runs are listed here once it starts one.`}
      />
    </SettingsPage>
  )
}
