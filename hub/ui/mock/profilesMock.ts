/** What the Profiles page's container would hold (operator's "A + C", 2026-11-21): the roster as
 *  list rows, what each profile is doing now, and the states the recording lacks. The recorded
 *  roster has four profiles, all idle; the other four, every status and every pool below are
 *  simulated (`// mock state`): no Hub reports a profile's status, spend or pool as one record yet. */
import * as React from 'react'
import type { AgentPoolEntry } from '@/api/agentPool'
import type { AgentSummary } from '@/api/agents'
import type { Charter } from '@/api/charters'
import type { ProfileListItem, ProfileNow } from '@/components/profiles/profilesModel'
import { entryLabel, cliLabel } from '@/components/agents/pool/poolModel'
import { agents, conversations, MOCK_NOW, tasks } from './fixtures'
import { POOL_CATALOG, poolEntry } from './poolMock'
import chartersJson from './fixtures/charters.json'
import ledgerJson from './fixtures/ledger.json'
import type { ProjectLedger } from '@/api/ledger'
import { LEANER_LEDGER } from './leanerMock'

const charters = chartersJson as unknown as Charter[]
// A fresh checkout's ledger fixture is a stub; fall back to the hand-written one so the screen still renders.
const ledger = ((ledgerJson as unknown as Partial<ProjectLedger>).spend ? ledgerJson : LEANER_LEDGER) as unknown as ProjectLedger

export type ProfilesMockState = 'populated' | 'single' | 'empty' | 'no-matches' | 'error' | 'loading'
export const PROFILES_MOCK_STATES: Array<{ value: ProfilesMockState; label: string }> = [
  { value: 'populated', label: 'Eight profiles' },
  { value: 'single', label: 'One profile' },
  { value: 'empty', label: 'No profiles' },
  { value: 'no-matches', label: 'Filter matches none' },
  { value: 'error', label: 'Could not load' },
  { value: 'loading', label: 'Loading' },
]

const ago = (minutes: number) => new Date(MOCK_NOW.getTime() - minutes * 60_000).toISOString()
const ahead = (minutes: number) => new Date(MOCK_NOW.getTime() + minutes * 60_000).toISOString()
const MIN = { hour: 60, day: 1440, week: 10_080 }

const TASK = tasks.find((t) => t.id === 'task-5fa7e0e0bf66')?.title ?? 'A folder watch that blocks renames'
const BUILD = 'Live updates that let folders be renamed' // mock state

interface Seed {
  name: string
  base: string // the recorded agent this one is cloned from
  colorIndex: number
  charter: string | null
  pool: AgentPoolEntry[]
  status: ProfileListItem['status']
  spend: ProfileListItem['spendUsd']
  lastActive: string | null
  archived?: boolean
  now: ProfileNow
}

const sonnet = (d = false) => poolEntry('runner-sonnet', null, d)
const opus = (effort: string | null, d = false) => poolEntry('runner-opus', effort, d)

// mock state: statuses, pools, charters and the four extra profiles.
const SEEDS: Seed[] = [
  {
    name: 'Builder',
    base: 'Builder',
    colorIndex: 1,
    charter: 'Developer',
    pool: [sonnet(true), poolEntry('runner-haiku', null), opus(null)],
    status: { kind: 'working', detail: TASK },
    spend: ledger.spend.by_agent.find((a) => a.agent === 'Builder')?.usd ?? 0,
    lastActive: ago(2),
    now: { kind: 'working', task: TASK, build: BUILD, since: ago(4) },
  },
  {
    name: 'QA1',
    base: 'QA1',
    colorIndex: 2,
    charter: 'Code Reviewer',
    pool: [opus(null, true), opus('high')],
    status: { kind: 'reviewing', detail: TASK },
    spend: ledger.spend.by_agent.find((a) => a.agent === 'QA1')?.usd ?? 0,
    lastActive: ago(1),
    now: { kind: 'reviewing', task: TASK, build: BUILD, since: ago(9), reviewing: 'Builder' },
  },
  {
    name: 'Architect',
    base: 'Architect',
    colorIndex: 0,
    charter: 'Spec Author',
    pool: [opus('high', true)],
    status: { kind: 'idle' },
    spend: ledger.spend.by_agent.find((a) => a.agent === 'Architect')?.usd ?? 0,
    lastActive: agents.find((a) => a.name === 'Architect')?.last_seen ?? null,
    now: { kind: 'last-run', at: agents.find((a) => a.name === 'Architect')?.last_seen ?? ago(70), task: 'Project status check and next steps' },
  },
  {
    name: 'QA2',
    base: 'QA2',
    colorIndex: 3,
    charter: 'Verifier',
    pool: [sonnet(true), opus(null)],
    status: { kind: 'idle' },
    spend: ledger.spend.by_agent.find((a) => a.agent === 'QA2')?.usd ?? 0,
    lastActive: agents.find((a) => a.name === 'QA2')?.last_seen ?? null,
    now: { kind: 'last-run', at: agents.find((a) => a.name === 'QA2')?.last_seen ?? ago(150), task: 'Review of live-update watcher folder-rename lock fix' },
  },
  {
    name: 'Guardian',
    base: 'QA2',
    colorIndex: 4,
    charter: 'Guardian',
    pool: [poolEntry('runner-sol', 'high', true)],
    status: { kind: 'held', detail: 'rate limit' },
    spend: null, // Codex runs are not priced
    lastActive: ago(26),
    now: { kind: 'held', reason: 'rate limit', until: ahead(80), lastTask: 'Security pass on the watcher change' },
  },
  {
    name: 'Docs',
    base: 'QA1',
    colorIndex: 5,
    charter: 'Tech Lead',
    pool: [poolEntry('runner-haiku', null, true)],
    status: { kind: 'idle' },
    spend: 0.42,
    lastActive: ago(3 * MIN.week),
    now: { kind: 'last-run', at: ago(3 * MIN.week), task: 'Release notes for the folder-watch fix' },
  },
  {
    name: 'Security',
    base: 'QA2',
    colorIndex: 6,
    charter: 'Security Engineer',
    pool: [],
    status: { kind: 'no-model' },
    spend: undefined,
    lastActive: null,
    now: { kind: 'never' },
  },
  {
    name: 'Scribe',
    base: 'Architect',
    colorIndex: 7,
    charter: 'Spec Author',
    pool: [sonnet(true)],
    status: { kind: 'idle' },
    spend: 3.18,
    lastActive: ago(9 * MIN.week),
    archived: true,
    now: { kind: 'last-run', at: ago(9 * MIN.week), task: 'First draft of the vault note' },
  },
]

const charterId = (name: string | null) => charters.find((c) => c.name === name)?.id ?? null

function toItem(s: Seed): ProfileListItem {
  const d = s.pool.find((e) => e.default) ?? s.pool[0]
  return {
    name: s.name,
    colorIndex: s.colorIndex,
    charterName: s.charter,
    provider: d?.cli ?? null,
    providerLabel: d ? cliLabel(d.cli) : null,
    model: d ? entryLabel(POOL_CATALOG, d) : null,
    moreModels: Math.max(0, s.pool.length - 1),
    status: s.status,
    spendUsd: s.spend,
    lastActiveAt: s.lastActive,
    archived: Boolean(s.archived),
  }
}

export const PROFILE_ITEMS: ProfileListItem[] = SEEDS.map(toItem)

export function itemsFor(state: ProfilesMockState): ProfileListItem[] {
  if (state === 'empty' || state === 'error' || state === 'loading') return []
  if (state === 'single') return [PROFILE_ITEMS[0]!]
  return PROFILE_ITEMS
}

export const nowFor = (name: string): ProfileNow => SEEDS.find((s) => s.name === name)?.now ?? { kind: 'never' }
export const poolFor = (name: string): AgentPoolEntry[] => SEEDS.find((s) => s.name === name)?.pool ?? []

/** The profile as the settings sections take it: the recorded agent it is cloned from, renamed. */
export function summaryFor(name: string): AgentSummary {
  const seed = SEEDS.find((s) => s.name === name)
  const base = agents.find((a) => a.name === (seed?.base ?? name)) ?? agents[0]!
  return {
    ...base,
    name,
    color_index: seed?.colorIndex ?? base.color_index,
    charter_id: charterId(seed?.charter ?? null),
    lifecycle: seed?.archived ? 'archived' : 'open',
    last_seen: seed?.lastActive ?? base.last_seen,
    status: seed?.status.kind === 'working' ? 'working' : 'idle',
  }
}

/** A profile's latest thread, if it has one: the recorded conversations are the Terra ones. */
export function latestThreadOf(name: string): string | null {
  return conversations.filter((c) => c.agent === name).sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0]?.id ?? null
}

export interface ProfilesAddress {
  profile: string | null
  section: string | null
  /** `null` when the address carries no filter (a mock state may then preset one). */
  q: string | null
  state: ProfilesMockState
}

const read = (): ProfilesAddress => {
  const q = new URLSearchParams(window.location.hash.split('?')[1] ?? '')
  const state = (PROFILES_MOCK_STATES.find((s) => s.value === q.get('state'))?.value ?? 'populated') as ProfilesMockState
  return { profile: q.get('profile'), section: q.get('section'), q: q.get('q'), state }
}

/** The page's address, kept in the hash (`#tab/profiles?profile=Builder&section=running&q=…&state=…`)
 *  so a selection, a section and a filter survive a reload and can be linked to (P8). Choosing a
 *  profile or section adds a history entry; typing a filter replaces the current one. */
export function useProfilesAddress(): ProfilesAddress & { set: (patch: Partial<ProfilesAddress>, replace?: boolean) => void } {
  const [value, setValue] = React.useState(read)
  React.useEffect(() => {
    const on = () => setValue(read())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  const set = React.useCallback((patch: Partial<ProfilesAddress>, replace = false) => {
    const next = { ...read(), ...patch }
    const q = new URLSearchParams()
    if (next.profile) q.set('profile', next.profile)
    if (next.section) q.set('section', next.section)
    if (next.q !== null) q.set('q', next.q)
    if (next.state !== 'populated') q.set('state', next.state)
    const hash = `#tab/profiles${q.toString() ? `?${q.toString()}` : ''}`
    if (replace) {
      window.history.replaceState(null, '', hash)
      setValue(read())
    } else {
      window.location.hash = hash
    }
  }, [])
  return { ...value, set }
}
