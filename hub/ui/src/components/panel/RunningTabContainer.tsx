import * as React from 'react'
import { useAgents } from '@/api/agents'
import { RunningTab } from './RunningTab'
import type { BuildSummaryModel } from '@/components/builds/buildViewModel'
import type { RunningItem } from './runningModel'

export interface RunningTabContainerProps {
  items: RunningItem[]
  /** One of the reads behind the list failed, so the list may be missing work. */
  loadFailed?: boolean
  onOpen: (item: RunningItem) => void
  onAttend: (item: RunningItem) => void
  /** Each build's compact summary, by build id. */
  buildSummaries?: Record<string, BuildSummaryModel | undefined>
  buildHref?: (buildId: string, task?: string) => string
  onOpenBuild?: (buildId: string, task?: string) => void
}

export function RunningTabContainer({ items, loadFailed, onOpen, onAttend, buildSummaries, buildHref, onOpenBuild }: RunningTabContainerProps) {
  const { data: agents = [], error: agentsError } = useAgents()
  const colorIndexOf = React.useCallback((name: string) => agents.find((a) => a.name === name)?.color_index, [agents])
  return (
    <>
      {loadFailed && (
        <p role="alert" className="aw-run-summary" data-testid="running-load-failed">
          Some of this list could not be loaded, so it may be missing work.
        </p>
      )}
      <div data-agents-failed={agentsError ? 'true' : undefined}>
        <RunningTab
          items={items}
          colorIndexOf={colorIndexOf}
          onOpen={onOpen}
          onAttend={onAttend}
          buildSummaries={buildSummaries}
          buildHref={buildHref}
          onOpenBuild={onOpenBuild}
        />
      </div>
    </>
  )
}
