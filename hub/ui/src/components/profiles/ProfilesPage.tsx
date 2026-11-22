import * as React from 'react'
import { EmptyState } from '@/components/common/EmptyState'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/common/Icon'
import { Segmented, type SegmentedOption } from '@/components/ui/segmented'
import { ProfileDetailHeader, ProfileNowStrip } from './ProfileDetailHeader'
import { ProfilesIndex } from './ProfilesIndex'
import type { ProfileListItem, ProfileNow } from './profilesModel'
import '@/styles/profiles.css'

/**
 * The Profiles tab: an index of every profile, and one profile's own page. Two levels, one
 * horizontal navigation on each: the app's top bar, then (on a profile) one row of tabs. There is
 * no list or section column beside the content; the profile's name switches to another profile.
 *
 * The profile's page is its settings (P5: one canonical full view), reused as `children` under the
 * tabs rather than drawn again. Three different empties are kept apart (P19): no profiles at all, a
 * filter that matches none, and a list that could not load. Escape on a profile's page goes back to
 * the index with that profile's row focused (P9).
 */
export function ProfilesPage({
  items,
  selected,
  query,
  onQueryChange,
  onOpen,
  onClose,
  onAdd,
  onAddPair,
  state = 'ready',
  onRetry,
  now,
  nowFor,
  hasThread,
  profileHref,
  onNewThread,
  onOpenLatestThread,
  onOpenTask,
  onOpenBuild,
  sections,
  section,
  onSection,
  children,
}: {
  items: readonly ProfileListItem[]
  /** The profile whose page is open; null shows the index. */
  selected: string | null
  query: string
  onQueryChange: (query: string) => void
  /** Opens a profile's page (a row, the switcher, a link to another profile). */
  onOpen: (name: string) => void
  /** Back to the index. */
  onClose: () => void
  onAdd: () => void
  /** Starts the usual pair: a builder and a checker. */
  onAddPair: () => void
  state?: 'ready' | 'loading' | 'error'
  onRetry?: () => void
  now: Date
  nowFor: (name: string) => ProfileNow
  hasThread: (name: string) => boolean
  profileHref: (name: string) => string
  onNewThread: (name: string) => void
  onOpenLatestThread: (name: string) => void
  onOpenTask: (name: string) => void
  onOpenBuild: (name: string) => void
  /** The page's tabs, in order, and the one open. */
  sections: ReadonlyArray<SegmentedOption<string>>
  section: string
  onSection: (section: string) => void
  /** The open tab's content: the profile's own settings section. */
  children: React.ReactNode
}) {
  const profile = items.find((p) => p.name === selected) ?? null
  // The profile the operator last had open, so the index can hand focus back to its row.
  const lastOpen = React.useRef<string | null>(null)
  if (profile) lastOpen.current = profile.name

  if (state === 'ready' && items.length === 0) {
    return (
      <div className="aw-pf-empty" data-testid="profiles-empty">
        <EmptyState
          icon="smart_toy"
          title="No profiles yet"
          description="A profile has its own name, models, permissions and workspace. It works only when you start a thread with it or a build gives it a task, so add at least one. Most projects start with a builder and a checker."
          action={
            <div className="aw-pf-empty-actions">
              <Button variant="primary" size="sm" onClick={onAddPair}>
                Add a builder and a checker
              </Button>
              <Button variant="outline" size="sm" onClick={onAdd}>
                <Icon name="add" size={14} />
                Add profile
              </Button>
            </div>
          }
        />
      </div>
    )
  }

  if (!profile || state !== 'ready') {
    return (
      <div data-testid="profiles-page">
        <ProfilesIndex
          items={items}
          query={query}
          onQueryChange={onQueryChange}
          onOpen={onOpen}
          onNewThread={onNewThread}
          onAdd={onAdd}
          state={state}
          onRetry={onRetry}
          now={now}
          focusProfile={lastOpen.current}
        />
      </div>
    )
  }

  return (
    <div
      className="aw-pf-page"
      data-testid="profile-page"
      onKeyDown={(event) => {
        // Only a key pressed on the page itself: a menu or dialog is portalled, and its own Escape
        // closes it first. A text field keeps its Escape.
        if (event.key !== 'Escape' || event.defaultPrevented) return
        if (!event.currentTarget.contains(event.target as Node)) return
        if ((event.target as HTMLElement).closest('input, textarea, [role="combobox"]')) return
        onClose()
      }}
    >
      <ProfileDetailHeader
        profile={profile}
        all={items}
        onBack={onClose}
        onSwitch={onOpen}
        hasThread={hasThread(profile.name)}
        onNewThread={() => onNewThread(profile.name)}
        onOpenLatestThread={() => onOpenLatestThread(profile.name)}
      />
      <ProfileNowStrip
        now={nowFor(profile.name)}
        at={now}
        profileHref={profileHref}
        onOpenProfile={onOpen}
        onOpenTask={() => onOpenTask(profile.name)}
        onOpenBuild={() => onOpenBuild(profile.name)}
      />
      <div className="aw-pf-tabs">
        <Segmented value={section} onChange={onSection} options={sections} label={`${profile.name} sections`} />
      </div>
      <div className="aw-pf-section" data-testid="profile-settings">
        {children}
      </div>
    </div>
  )
}
