import { describe, expect, it } from 'vitest'
import { parseDestination, serializeDestination } from '@/lib/navigation'
import { SETTINGS_INDEX, searchSettings, settingDestination } from '@/lib/settingsIndex'

const labels = (query: string) => searchSettings(query).map((m) => `${m.entry.scope}/${m.entry.section}/${m.entry.label}`)

describe('searching settings', () => {
  it('lists nothing for fewer than two characters', () => {
    expect(searchSettings('')).toEqual([])
    expect(searchSettings(' a ')).toEqual([])
  })

  it('finds the project and agent Checkpoints settings, label matches first', () => {
    const hits = searchSettings('checkpoint')
    expect(labels('checkpoint')).toContain('project/checkpoints/Checkpoints')
    expect(labels('checkpoint')).toContain('agent/checkpoints/Checkpoints')
    const firstOther = hits.findIndex((m) => !m.inLabel)
    if (firstOther >= 0) expect(hits.slice(firstOther).every((m) => !m.inLabel)).toBe(true)
  })

  it('matches the start of words of the label, description, section and scope', () => {
    expect(labels('vol')).toEqual(['app/notifications/Volume'])
    expect(labels('CI cutoff')).toEqual(['project/landing/CI asking stops after'])
    expect(labels('checkpoint mode').filter((l) => l.startsWith('agent/'))).toEqual(['agent/checkpoints/Checkpoints'])
  })

  it('lists App before Project before agent settings within a group', () => {
    const order = ['app', 'project', 'agent']
    const scopes = searchSettings('permissions').filter((m) => m.inLabel).map((m) => order.indexOf(m.entry.scope))
    expect(scopes).toEqual([...scopes].sort())
  })

  it('finds nothing for words no setting has', () => {
    expect(searchSettings('zzqx')).toEqual([])
  })

  it('has one entry per scope, section and label', () => {
    const keys = SETTINGS_INDEX.map((e) => `${e.scope}/${e.section}/${e.label}`)
    expect(new Set(keys).size).toBe(keys.length)
  })
})

describe('a location that names a setting', () => {
  it('round-trips through the address for each scope', () => {
    const project = settingDestination(SETTINGS_INDEX.find((e) => e.label === 'CI asking stops after')!, 'p1')!
    expect(serializeDestination(project)).toContain('setting=CI+asking+stops+after')
    expect(parseDestination(serializeDestination(project))).toEqual(project)

    const agent = settingDestination(SETTINGS_INDEX.find((e) => e.scope === 'agent' && e.label === 'Checkpoints')!, 'p1', 'bravo')!
    expect(parseDestination(serializeDestination(agent))).toEqual(agent)

    const app = settingDestination(SETTINGS_INDEX.find((e) => e.label === 'Volume')!, null)!
    expect(parseDestination(serializeDestination(app))).toEqual(app)
  })

  it('needs a project for project settings and an agent for an agent setting', () => {
    expect(settingDestination(SETTINGS_INDEX.find((e) => e.scope === 'project')!, null)).toBeNull()
    expect(settingDestination(SETTINGS_INDEX.find((e) => e.scope === 'agent')!, 'p1')).toBeNull()
  })
})
