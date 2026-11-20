import { useState } from 'react'
import { useProjects, useSetupDismissal, type ProjectSetupItem } from '@/api/projects'
import { useConfigStore } from '@/store/configStore'
import { describeSetupItem } from './setupItems'
import { SetupList } from './SetupList'
import { SetupProfilesDialog } from './SetupProfilesDialog'

/**
 * The set-up list, wired (`a-project-says-what-it-still-needs`): the Hub's items for one project,
 * read from the same `['projects']` collection the rail reads, so the rail's count, Overview and
 * Project settings change together and follow the project update events with no state of their own.
 * The profiles item opens the setup offer's dialog (`profiles-threads-and-builds-everywhere` D6).
 */

export function ProjectSetupList({
  place,
  showDismissed = true,
}: {
  place: 'overview' | 'settings'
  /** Dismissed items, with their way back: Project settings -> Project only. */
  showDismissed?: boolean
}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: projects = [] } = useProjects()
  const setup = projects.find((p) => p.id === projectId)?.setup
  if (!projectId || !setup) return null
  const dismissed = showDismissed ? setup.dismissed : []
  if (!setup.items.length && !dismissed.length) return null
  return <WiredList projectId={projectId} items={setup.items} dismissed={dismissed} place={place} />
}

/** Split out so a project with nothing to show never needs the dismissal mutation. */
function WiredList({
  projectId,
  items,
  dismissed,
  place,
}: {
  projectId: string
  items: ProjectSetupItem[]
  dismissed: ProjectSetupItem[]
  place: 'overview' | 'settings'
}) {
  const dismissal = useSetupDismissal(projectId)
  const [offerOpen, setOfferOpen] = useState(false)
  const describe = (i: ProjectSetupItem) => describeSetupItem(i, projectId, () => setOfferOpen(true))
  return (
    <>
    <SetupList
      place={place}
      items={items.map(describe)}
      dismissed={dismissed.map(describe)}
      onDismiss={(item) => dismissal.mutate({ item: item.id, show: false })}
      onRestore={(item) => dismissal.mutate({ item: item.id, show: true })}
    />
    <SetupProfilesDialog projectId={projectId} open={offerOpen} onOpenChange={setOfferOpen} />
    </>
  )
}
