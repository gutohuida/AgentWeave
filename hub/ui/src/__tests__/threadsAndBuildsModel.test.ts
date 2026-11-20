import { describe, expect, it } from 'vitest'
import type { AgentConversation } from '@/api/agentChat'
import {
  buildAccessibleName,
  buildStatusWord,
  filterThreads,
  holdOrder,
  orderBuilds,
  orderThreads,
  type SidebarBuild,
} from '@/components/layout/threadsAndBuildsModel'

const t = (id: string, agent: string, title: string, attention: AgentConversation['attention'] = 'idle') =>
  ({ id, agent, title, attention }) as AgentConversation

const b = (id: string, needs: SidebarBuild['needs_operator'], state: SidebarBuild['state'] = 'running'): SidebarBuild => ({
  id,
  document_title: `Doc ${id}`,
  state,
  tasks_total: 6,
  tasks_done: 4,
  needs_operator: needs,
})

describe('threads and builds model', () => {
  it('raises waiting threads and keeps the route order otherwise, in either route order', () => {
    const route = [t('a', 'Architect', 'A'), t('b', 'QA', 'B', 'waiting'), t('c', 'Developer', 'C', 'running')]
    expect(orderThreads(route).map((x) => x.id)).toEqual(['b', 'a', 'c'])
    expect(orderThreads([...route].reverse()).map((x) => x.id)).toEqual(['b', 'c', 'a'])
  })

  it('lists builds needing the operator before running ones', () => {
    const route = [b('run', null), b('stop', { kind: 'stopped', text: '' }, 'stopped')]
    expect(orderBuilds(route).map((x) => x.id)).toEqual(['stop', 'run'])
  })

  it('names a build with stable words and a status word', () => {
    expect(buildAccessibleName(b('x', { kind: 'stopped', text: '' }, 'stopped'))).toBe(
      'Build: Doc x, 4 of 6 tasks done, stopped, needs you',
    )
    expect(buildAccessibleName(b('y', null))).toBe('Build: Doc y, 4 of 6 tasks done, running')
    expect(buildStatusWord(b('y', null))).toBe('4/6')
    expect(buildStatusWord(b('q', { kind: 'question', text: '' }))).toBe('Question')
  })

  it('filters on title or profile', () => {
    const list = [t('a', 'Architect', 'Vault import'), t('b', 'QA', 'Landing')]
    expect(filterThreads(list, 'qa').map((x) => x.id)).toEqual(['b'])
    expect(filterThreads(list, 'VAULT').map((x) => x.id)).toEqual(['a'])
    expect(filterThreads(list, '  ')).toHaveLength(2)
  })

  it('holds rows in place under the pointer: kept rows stay, gone rows drop, new rows join last', () => {
    const next = [{ id: 'n' }, { id: 'c' }, { id: 'a' }]
    expect(holdOrder(['a', 'b', 'c'], next).map((x) => x.id)).toEqual(['a', 'c', 'n'])
  })
})
