import { describe, expect, it } from 'vitest'
import { countLine, groupProfiles, listOrder, modelLine, statusSentence, type ProfileListItem } from '@/components/profiles/profilesModel'

const item = (name: string, over: Partial<ProfileListItem> = {}): ProfileListItem => ({
  name,
  colorIndex: 0,
  charterName: 'Developer',
  provider: 'claude',
  providerLabel: 'Claude Code',
  model: 'Sonnet 5.5',
  moreModels: 0,
  status: { kind: 'idle' },
  spendUsd: 1,
  lastActiveAt: null,
  archived: false,
  ...over,
})

describe('groupProfiles', () => {
  const all = [
    item('Zed'),
    item('Amy', { status: { kind: 'working', detail: 'Fix it' } }),
    item('Bob', { status: { kind: 'reviewing', detail: 'Fix it' } }),
    item('Cy', { archived: true, status: { kind: 'working', detail: 'x' } }),
    item('Dee'),
  ]
  it('puts profiles at work first and the rest A to Z; archived apart, never active', () => {
    const g = groupProfiles(all)
    expect(g.active.map((i) => i.name)).toEqual(['Amy', 'Bob'])
    expect(g.rest.map((i) => i.name)).toEqual(['Dee', 'Zed'])
    expect(g.archived.map((i) => i.name)).toEqual(['Cy'])
  })
  it('filters on name, charter, model and status word', () => {
    expect(groupProfiles(all, 'rev').active.map((i) => i.name)).toEqual(['Bob'])
    expect(groupProfiles(all, 'zzz')).toEqual({ active: [], rest: [], archived: [] })
  })
  it('lists archived rows only while their group is open', () => {
    expect(listOrder(groupProfiles(all), false).map((i) => i.name)).toEqual(['Amy', 'Bob', 'Dee', 'Zed'])
    expect(listOrder(groupProfiles(all), true).map((i) => i.name).pop()).toBe('Cy')
  })
})

describe('words', () => {
  it('reads the model line, the status and the count', () => {
    expect(modelLine({ model: 'Sonnet 5.5', moreModels: 2 })).toBe('Sonnet 5.5 +2 models')
    expect(modelLine({ model: 'Sonnet 5.5', moreModels: 1 })).toBe('Sonnet 5.5 +1 model')
    expect(modelLine({ model: null, moreModels: 0 })).toBe('No model')
    expect(statusSentence({ kind: 'held', detail: 'rate limit' })).toBe('Held, rate limit')
    expect(statusSentence({ kind: 'working', detail: 'Fix it' })).toBe('Working on Fix it')
    expect(countLine(2, 8)).toBe('2 of 8 profiles')
    expect(countLine(1, 1)).toBe('1 profile')
  })
})
