import * as React from 'react'
import { EmptyState } from '@/components/common/EmptyState'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/common/Icon'
import { ProfileDetailHeader, ProfileNowStrip } from './ProfileDetailHeader'
import { ProfilesList } from './ProfilesList'
import type { ProfileListItem, ProfileNow } from './profilesModel'
import '@/styles/profiles.css'

/**
 * The Profiles workspace: every profile in a list that stays put, and the selected profile's own
 * settings beside it (P5: the profile's one full view is its settings, so the page reuses the
 * settings sections as `children` rather than drawing its own). Three different empties are kept
 * apart (P19): no profiles at all, a filter that matches none, and a list that could not load.
 *
 * Escape inside the detail returns focus to the profile's row (P9).
 */
export function ProfilesPage({
  items,
  selected,
  query,
  onQueryChange,
  onSelect,
  onAdd,
  onAddPair,
  state = 'ready',
  onRetry,
  now,
  nowFor,
  hasThread,
  profileHref,
  onOpenProfile,
  onNewThread,
  onOpenLatestThread,
  onOpenTask,
  onOpenBuild,
  children,
}: {
  items: readonly ProfileListItem[]
  selected: string | null
  query: string
  onQueryChange: (query: string) => void
  onSelect: (name: string) => void
  onAdd: () => void
  /** Starts the usual pair: a builder and a checker. */
  onAddPair: () => void
  state?: 'ready' | 'loading' | 'error'
  onRetry?: () => void
  now: Date
  nowFor: (name: string) => ProfileNow
  hasThread: (name: string) => boolean
  profileHref: (name: string) => string
  onOpenProfile: (name: string) => void
  onNewThread: (name: string) => void
  onOpenLatestThread: (name: string) => void
  onOpenTask: (name: string) => void
  onOpenBuild: (name: string) => void
  /** The selected profile's settings sections (the page's detail). */
  children: React.ReactNode
}) {
  const rootRef = React.useRef<HTMLDivElement>(null)
  const profile = items.find((p) => p.name === selected) ?? null

  if (state === 'ready' && items.length === 0) {
    return (
      <div className="aw-pf-empty" data-testid="profiles-empty">
        <EmptyState
          icon="smart_toy"
          title="No profiles yet"
          description="A profile is a named agent with its own models, permissions and workspace. It works only when you start a thread with it or a build gives it a task, so add at least one. Most projects start with a builder and a checker."
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

  return (
    <div className="aw-pf" ref={rootRef} data-testid="profiles-page">
      <ProfilesList
        items={items}
        selected={profile?.name ?? null}
        query={query}
        onQueryChange={onQueryChange}
        onSelect={onSelect}
        onAdd={onAdd}
        state={state}
        onRetry={onRetry}
        now={now}
      />
      <div
        className="aw-pf-detail-pane"
        onKeyDown={(event) => {
          // Only keys pressed inside the detail itself: a menu or dialog is portalled, and its own
          // Escape closes it first.
          if (event.key !== 'Escape' || event.defaultPrevented || !profile) return
          if (!event.currentTarget.contains(event.target as Node)) return
          rootRef.current?.querySelector<HTMLElement>(`[data-slot="profile-row"][data-profile="${CSS.escape(profile.name)}"]`)?.focus()
        }}
      >
        {profile ? (
          <>
            <ProfileDetailHeader
              profile={profile}
              hasThread={hasThread(profile.name)}
              onNewThread={() => onNewThread(profile.name)}
              onOpenLatestThread={() => onOpenLatestThread(profile.name)}
            />
            <ProfileNowStrip
              now={nowFor(profile.name)}
              at={now}
              profileHref={profileHref}
              onOpenProfile={onOpenProfile}
              onOpenTask={() => onOpenTask(profile.name)}
              onOpenBuild={() => onOpenBuild(profile.name)}
            />
            <div className="aw-pf-settings" data-testid="profile-settings">
              {children}
            </div>
          </>
        ) : (
          <div className="aw-pf-nodetail">{state === 'ready' ? 'Choose a profile to see its settings.' : null}</div>
        )}
      </div>
    </div>
  )
}
