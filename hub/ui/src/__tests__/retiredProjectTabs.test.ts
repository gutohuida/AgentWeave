import { describe, expect, it } from 'vitest'
import {
  GO_TO_NAMES,
  PROJECT_TABS,
  THREAD_CHECKPOINTS_LIST,
  TOP_BAR_TABS,
  agentSettingsDestination,
  environmentDestination,
  parseDestination,
  projectAddress,
  serializeDestination,
  threadCheckpointsDestination,
  threadDestination,
  topBarTabFor,
  type WorkspaceDestination,
} from '@/lib/navigation'

// leaner-navigation FR-2 (retired-addresses-redirect): every address naming a removed tab resolves,
// in the navigation layer, to that tab's new home — never to a blank or unknown page.
const P = 'proj-1'
const parse = (query: string) => parseDestination(`?project=${P}&${query}`)

describe('retired project tabs resolve to their new homes', () => {
  it.each<[string, WorkspaceDestination]>([
    ['tab=activity', environmentDestination(P, 'budgets')],
    ['tab=activity&view=ledger', environmentDestination(P, 'budgets')],
    ['tab=logs', environmentDestination(P, 'logs')],
    ['tab=activity&view=logs', environmentDestination(P, 'logs')],
    ['tab=traces', environmentDestination(P, 'traces')],
    ['tab=activity&view=traces', environmentDestination(P, 'traces')],
    ['tab=jobs', environmentDestination(P, 'jobs')],
    ['tab=jobs&focus=job-7', environmentDestination(P, 'jobs', null, 'job-7')],
    ['tab=traces&focus=run-1,run-2', environmentDestination(P, 'traces', null, 'run-1,run-2')],
  ])('%s', (query, expected) => {
    expect(parse(query)).toEqual(expected)
  })

  it('checkpoints with a checkpoint asks for its thread to be looked up, the checkpoint kept', () => {
    expect(parse('tab=checkpoints&checkpoint=ckpt-9')).toEqual({
      kind: 'checkpoint-lookup', projectId: P, checkpoint: 'ckpt-9', conversation: null,
    })
    // The checkpoint wins over any narrowing the old list carried.
    expect(parse('tab=checkpoints&checkpoint=ckpt-9&ckptAgent=QA&ckptConversation=conv-2')).toEqual({
      kind: 'checkpoint-lookup', projectId: P, checkpoint: 'ckpt-9', conversation: null,
    })
  })

  it('checkpoints with a conversation asks for that thread, to open its Checkpoints panel tab', () => {
    expect(parse('tab=checkpoints&ckptConversation=conv-2&ckptAgent=QA')).toEqual({
      kind: 'checkpoint-lookup', projectId: P, checkpoint: null, conversation: 'conv-2',
    })
  })

  it("checkpoints with only an agent opens that profile's checkpoint list", () => {
    expect(parse('tab=checkpoints&ckptAgent=QA')).toEqual(agentSettingsDestination(P, 'QA', 'checkpoints'))
    expect(parse('tab=checkpoints&ckptAgent=QA&ckptTrigger=operator')).toEqual(
      agentSettingsDestination(P, 'QA', 'checkpoints'),
    )
  })

  it('checkpoints with nothing named opens the project Checkpoints settings, not a blank list', () => {
    expect(parse('tab=checkpoints')).toEqual(environmentDestination(P, 'checkpoints'))
    expect(parse('tab=checkpoints&checkpoint=..%2Fx%0A')).toEqual(environmentDestination(P, 'checkpoints'))
  })

  it('thread opens the chapters view, and a knot focuses that knot', () => {
    expect(parse('tab=thread')).toEqual(threadDestination(P))
    expect(parse('tab=thread&knot=k-12')).toEqual({ kind: 'project', projectId: P, tab: 'thread', knot: 'k-12' })
  })

  it('a lookup and the thread it resolves to both survive a reload of their own address', () => {
    for (const destination of [
      { kind: 'checkpoint-lookup', projectId: P, checkpoint: 'ckpt-9', conversation: null } as const,
      { kind: 'checkpoint-lookup', projectId: P, checkpoint: null, conversation: 'conv-2' } as const,
      threadCheckpointsDestination(P, 'QA', 'conv-2', 'ckpt-9'),
      threadCheckpointsDestination(P, 'QA', 'conv-2'),
      environmentDestination(P, 'jobs', null, 'job-7'),
    ]) {
      expect(parseDestination(serializeDestination(destination))).toEqual(destination)
    }
    expect(threadCheckpointsDestination(P, 'QA', 'conv-2').checkpoint).toBe(THREAD_CHECKPOINTS_LIST)
  })

  it('none of them is a project tab any more, and no address lands on a page nothing draws', () => {
    for (const retired of ['activity', 'jobs', 'checkpoints', 'logs', 'traces']) {
      expect(PROJECT_TABS as readonly string[]).not.toContain(retired)
      const resolved = parse(`tab=${retired}`)
      expect(resolved && resolved.kind === 'project' && 'tab' in resolved ? resolved.tab : 'other').not.toBe(retired)
    }
  })
})

describe("the command palette's Go to names go through the same resolver", () => {
  it.each<[string, WorkspaceDestination]>([
    ['activity', environmentDestination(P, 'budgets')],
    ['logs', environmentDestination(P, 'logs')],
    ['traces', environmentDestination(P, 'traces')],
    ['jobs', environmentDestination(P, 'jobs')],
    ['thread', threadDestination(P)],
  ])('%s', (name, expected) => {
    expect(GO_TO_NAMES as readonly string[]).toContain(name)
    expect(projectAddress(P, name)).toEqual(expected)
    // The same answer as the URL form of the name.
    expect(projectAddress(P, name)).toEqual(parse(`tab=${name}`))
  })

  it('offers every top-bar tab too', () => {
    for (const tab of TOP_BAR_TABS) expect(projectAddress(P, tab)).toEqual(parse(`tab=${tab}`))
  })
})

describe('the top bar (FR-1)', () => {
  it('draws exactly Overview, Tasks, Profiles, Spec, Vault, Dashboards', () => {
    expect(TOP_BAR_TABS).toEqual(['overview', 'tasks', 'profiles', 'spec', 'vault', 'dashboards'])
  })

  it('highlights Overview while the Chapters view is open', () => {
    expect(topBarTabFor('thread')).toBe('overview')
    expect(topBarTabFor('vault')).toBe('vault')
  })
})
