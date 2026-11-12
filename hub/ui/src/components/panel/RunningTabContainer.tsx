import * as React from 'react'
import { useAgents } from '@/api/agents'
import { RunningTab } from './RunningTab'
import type { RunningItem } from './runningModel'

export interface RunningTabContainerProps {
  items: RunningItem[]
  onOpen: (item: RunningItem) => void
  onAttend: (item: RunningItem) => void
}

export function RunningTabContainer({ items, onOpen, onAttend }: RunningTabContainerProps) {
  const { data: agents = [] } = useAgents()
  const colorIndexOf = React.useCallback((name: string) => agents.find((a) => a.name === name)?.color_index, [agents])
  return <RunningTab items={items} colorIndexOf={colorIndexOf} onOpen={onOpen} onAttend={onAttend} />
}
