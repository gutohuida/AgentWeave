import { describe, expect, it } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import {
  agentDestination,
  buildRailProjects,
  projectDestination,
} from '@/lib/navigation'

const agent: AgentSummary = {
  name: 'claude',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  color_index: 3,
}

describe('phase 1 conversation navigation contract', () => {
  it('adapts the authenticated project into a collection-shaped rail tree', () => {
    expect(buildRailProjects({ id: 'proj-1', name: 'AgentWeave' }, [agent])).toEqual([
      { id: 'proj-1', name: 'AgentWeave', agents: [agent] },
    ])
  })

  it('keeps project-name activation separate from expansion state', () => {
    expect(projectDestination('proj-1')).toEqual({ kind: 'project', projectId: 'proj-1' })
  })

  it('opens an agent-scoped conversation without using a provider session id', () => {
    expect(agentDestination('proj-1', 'claude')).toEqual({
      kind: 'conversation',
      projectId: 'proj-1',
      agent: 'claude',
      conversationId: null,
    })
  })

  it('preserves a selected AgentWeave conversation and supports one-step back', () => {
    const destination = agentDestination('proj-1', 'claude', 'conv-123')
    expect(destination.conversationId).toBe('conv-123')
    expect(projectDestination(destination.projectId)).toEqual({
      kind: 'project',
      projectId: 'proj-1',
    })
  })
})
