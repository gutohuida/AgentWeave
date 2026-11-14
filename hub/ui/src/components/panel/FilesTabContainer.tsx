import * as React from 'react'
import { useConversationFiles, type FilesLocation } from '@/api/workspace'
import { LoadingThread } from '@/components/common/LoadingThread'
import { FilesTab, type ChangeMark } from './FilesTab'

const KEY_PREFIX = 'aw.files.location'

/** The location the operator last chose for this conversation, or null when they never chose. */
function loadFilesLocation(projectId: string, conversationId: string | null): FilesLocation | null {
  if (!conversationId) return null
  try {
    const value = window.localStorage.getItem(`${KEY_PREFIX}.${projectId}.${conversationId}`)
    return value === 'worktree' || value === 'root' ? value : null
  } catch {
    return null
  }
}

function saveFilesLocation(projectId: string, conversationId: string, location: FilesLocation) {
  try {
    window.localStorage.setItem(`${KEY_PREFIX}.${projectId}.${conversationId}`, location)
  } catch {
    // Storage unavailable: the choice holds for this page view only.
  }
}

/** The Files tab fed from the Hub: the conversation's checkout or the project root, as a tree. */
export function FilesTabContainer({
  agent,
  projectId,
  conversationId,
  currentPath,
  currentLocation,
  onOpen,
}: {
  agent: string
  projectId: string
  conversationId: string | null
  /** The file open in a file tab right now, and where it was read from. */
  currentPath: string | null
  currentLocation: FilesLocation | null
  onOpen: (path: string, location: FilesLocation) => void
}) {
  // Undefined until the operator chooses: the Hub then answers with the checkout when there is one.
  const [chosen, setChosen] = React.useState<FilesLocation | undefined>(
    () => loadFilesLocation(projectId, conversationId) ?? undefined,
  )
  React.useEffect(() => {
    setChosen(loadFilesLocation(projectId, conversationId) ?? undefined)
  }, [projectId, conversationId])

  const listing = useConversationFiles(conversationId, chosen)
  const data = listing.data

  if (!conversationId) return <p className="aw-ptab-note">Start a conversation to browse its files.</p>
  if (!data) {
    return listing.isError ? (
      <p className="aw-ptab-note">The files could not be listed. Try again in a moment.</p>
    ) : (
      <LoadingThread label="Loading files" />
    )
  }

  const location: FilesLocation = data.has_checkout ? data.location : 'root'
  const changed: Record<string, ChangeMark> = {}
  for (const [path, status] of Object.entries(data.changed ?? {})) {
    // A rename reads as a modification of its new path in the tree.
    changed[path] = status === 'A' || status === 'D' ? status : 'M'
  }

  return (
    <FilesTab
      agent={agent}
      location={location}
      hasCheckout={data.has_checkout}
      note={!data.has_checkout ? data.message ?? null : null}
      branch={data.branch ?? null}
      onLocationChange={(next) => {
        setChosen(next)
        saveFilesLocation(projectId, conversationId, next)
      }}
      paths={data.paths}
      changed={changed}
      currentPath={currentLocation === location ? currentPath : null}
      onOpen={(path) => onOpen(path, location)}
    />
  )
}
