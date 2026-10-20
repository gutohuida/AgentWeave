/** Fixture data, recorded from the Terra replica's API on 2026-10-20 (real shapes, real content).
 *  Typed with the app's own API types, so a screen built on these props takes the hooks' data
 *  unchanged once wired in. Add a fixture by dumping the route's JSON into fixtures/ and typing it
 *  here; never hand-edit the JSON. */
import type { AgentSummary } from '@/api/agents'
import type { AgentConversation } from '@/api/agentChat'
import type { Task } from '@/api/tasks'
import type { Job } from '@/api/jobs'
import type { ProjectSummary } from '@/api/projects'
import agentsJson from './fixtures/agents.json'
import conversationsJson from './fixtures/conversations.json'
import tasksJson from './fixtures/tasks.json'
import jobsJson from './fixtures/jobs.json'
import projectsJson from './fixtures/projects.json'

export const MOCK_NOW = new Date('2026-10-17T12:10:00Z')

export const PROJECT_ID = 'proj-cd006955cbe2'

export interface MockProject {
  id: string
  name: string
  working_directory: string
}

export const projects = projectsJson as unknown as MockProject[]
export const project = projects.find((p) => p.id === PROJECT_ID)!

/** To show every state the screens must handle, the mock marks Builder as working and QA1 as
 *  waiting on the operator (the replica's agents are all idle). Nothing else is altered. */
type Attention = AgentConversation['attention']
const ATTENTION_OVERRIDE: Record<string, Attention> = { Builder: 'running', QA1: 'waiting' }

export const agents: AgentSummary[] = (agentsJson as unknown as AgentSummary[]).map((a) =>
  ATTENTION_OVERRIDE[a.name] === 'running' ? { ...a, status: 'working' } : a,
)

export const conversations: AgentConversation[] = (
  (conversationsJson as unknown as { conversations: AgentConversation[] }).conversations
).map((c, i, all) => {
  const firstOfAgent = all.findIndex((o) => o.agent === c.agent) === i
  const override = firstOfAgent ? ATTENTION_OVERRIDE[c.agent] : undefined
  return override ? { ...c, attention: override } : c
})

export const tasks: Task[] = (tasksJson as unknown as { tasks: Task[] }).tasks
export const jobs: Job[] = jobsJson as unknown as Job[]

export function agentAttention(name: string): Attention {
  return ATTENTION_OVERRIDE[name] ?? 'idle'
}

/** What the real rail (`Sidebar`) reads, seeded into the mock's query cache (`mock/queryClient.ts`)
 *  under the same keys `useProjects` and `useProjectConversations` use. */
export function projectSummaries(): ProjectSummary[] {
  return (projectsJson as unknown as ProjectSummary[]).map((p) =>
    p.id === PROJECT_ID
      ? {
          ...p,
          agents: p.agents.map((a) => (ATTENTION_OVERRIDE[a.name] === 'running' ? { ...a, status: 'working' } : a)),
        }
      : p,
  )
}

export const projectConversations = {
  ...(conversationsJson as unknown as { archived_count: number; archived_by_agent?: Record<string, number> }),
  conversations,
}
