import * as React from 'react'
import { ProfilesPage } from '@/components/profiles/ProfilesPage'
import { toast } from '@/lib/toast'
import type { AgentSettingsSection, ScreenProps } from '../routes'
import { AgentSettingsBody } from './AgentSettings'
import { itemsFor, latestThreadOf, nowFor, poolFor, summaryFor, useProfilesAddress } from '../profilesMock'

const SECTION_IDS: AgentSettingsSection[] = ['agent', 'running', 'permissions', 'checkpoints', 'workspace']
const LABELS: Record<AgentSettingsSection, string> = { agent: 'Profile', running: 'Models', permissions: 'Permissions', checkpoints: 'Checkpoints', workspace: 'Workspace' }

/** The container the Profiles tab would be: the roster, the address (profile, section, filter,
 *  state) and the settings section as the open tab. Every simulated state is `// mock state` and
 *  set from the bar or `?state=`; the address carries the rest (P8). */
export default function Profiles({ go, now }: ScreenProps) {
  const address = useProfilesAddress()
  const { state, set } = address
  // mock state: "Filter matches none" presets a filter that matches nothing until one is typed.
  const query = address.q ?? (state === 'no-matches' ? 'payroll' : '')
  const shown = itemsFor(state === 'no-matches' ? 'populated' : state)
  const selected = state === 'populated' || state === 'single' || state === 'no-matches' ? (shown.find((p) => p.name === address.profile)?.name ?? null) : null
  const section = SECTION_IDS.find((s) => s === address.section) ?? 'agent'
  const profileHref = (name: string) => `#tab/profiles?profile=${encodeURIComponent(name)}`

  // The Models tab's count follows the pool as it is edited; it starts as the recorded pool's size.
  const [counts, setCounts] = React.useState<Record<string, number>>({})
  const countFor = (name: string) => counts[name] ?? poolFor(name).length
  const onPoolCount = React.useCallback((n: number) => selected && setCounts((c) => (c[selected] === n ? c : { ...c, [selected]: n })), [selected])

  return (
    <ProfilesPage
      items={state === 'error' || state === 'loading' ? [] : shown}
      selected={selected}
      query={query}
      onQueryChange={(q) => set({ q }, true)}
      onOpen={(name) => set({ profile: name, section: null })}
      onClose={() => set({ profile: null, section: null })}
      onAdd={() => toast({ title: 'Add profile opens the profile dialog' })}
      onAddPair={() => toast({ title: 'Adds a builder and a checker, each on its own model' })}
      state={state === 'error' ? 'error' : state === 'loading' ? 'loading' : 'ready'}
      onRetry={() => {
        toast({ title: 'Asking the Hub again…' })
        set({ state: 'populated' })
      }}
      now={now}
      nowFor={nowFor}
      hasThread={(name) => latestThreadOf(name) !== null}
      profileHref={profileHref}
      onNewThread={(name) => go({ kind: 'conversation', agent: name, conversationId: null })}
      onOpenLatestThread={(name) => go({ kind: 'conversation', agent: name, conversationId: latestThreadOf(name) })}
      onOpenTask={() => go({ kind: 'tab', tab: 'tasks' })}
      onOpenBuild={() => go({ kind: 'build', buildId: null })}
      sections={SECTION_IDS.map((id) => ({ value: id, label: LABELS[id], ...(id === 'running' && selected ? { count: countFor(selected) } : {}) }))}
      section={section}
      onSection={(id) => set({ section: id === 'agent' ? null : id })}
    >
      {selected ? (
        <AgentSettingsBody
          key={selected}
          embedded
          name={selected}
          section={section}
          onSelectSection={(id) => set({ section: id })}
          go={go}
          now={now}
          summary={summaryFor(selected)}
          initialPool={poolFor(selected)}
          onPoolCount={onPoolCount}
        />
      ) : null}
    </ProfilesPage>
  )
}
