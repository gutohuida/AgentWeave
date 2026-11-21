import { ProfilesPage } from '@/components/profiles/ProfilesPage'
import { groupProfiles, listOrder } from '@/components/profiles/profilesModel'
import { toast } from '@/lib/toast'
import type { AgentSettingsSection, ScreenProps } from '../routes'
import { AgentSettingsBody } from './AgentSettings'
import { itemsFor, latestThreadOf, nowFor, poolFor, summaryFor, useProfilesAddress } from '../profilesMock'

const SECTION_IDS: AgentSettingsSection[] = ['agent', 'running', 'permissions', 'checkpoints', 'workspace']

/** The container the Profiles tab would be: the roster, the address (selected profile, section,
 *  filter, state) and the settings sections as the detail. Every simulated state is `// mock state`
 *  and set from the bar or `?state=`; the address carries the rest (P8). */
export default function Profiles({ go, now }: ScreenProps) {
  const address = useProfilesAddress()
  const { state, set } = address
  // mock state: "Filter matches none" presets a filter that matches nothing until one is typed.
  const query = address.q ?? (state === 'no-matches' ? 'payroll' : '')
  const shown = itemsFor(state === 'no-matches' ? 'populated' : state)

  // The default selection is the first row drawn; the address only carries a choice the operator made.
  const first = listOrder(groupProfiles(shown, ''), false)[0]?.name ?? null
  const selected = shown.find((p) => p.name === address.profile)?.name ?? first
  const section = SECTION_IDS.find((s) => s === address.section) ?? 'agent'
  const profileHref = (name: string) => `#tab/profiles?profile=${encodeURIComponent(name)}`

  return (
    <ProfilesPage
      items={state === 'error' || state === 'loading' ? [] : shown}
      selected={state === 'error' || state === 'loading' ? null : selected}
      query={query}
      onQueryChange={(q) => set({ q }, true)}
      onSelect={(name) => set({ profile: name, section: null })}
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
      onOpenProfile={(name) => set({ profile: name, section: null })}
      onNewThread={(name) => go({ kind: 'conversation', agent: name, conversationId: null })}
      onOpenLatestThread={(name) => go({ kind: 'conversation', agent: name, conversationId: latestThreadOf(name) })}
      onOpenTask={() => go({ kind: 'tab', tab: 'tasks' })}
      onOpenBuild={() => go({ kind: 'build', buildId: null })}
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
        />
      ) : null}
    </ProfilesPage>
  )
}
