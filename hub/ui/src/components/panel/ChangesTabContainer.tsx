import * as React from 'react'
import { useChangePatch, useConversationChanges, type ChangesScope } from '@/api/changes'
import { ChangesTab, type PatchState } from './ChangesTab'

/** The Changes tab fed from the Hub: the conversation's changed files, and the selected file's diff. */
export function ChangesTabContainer({
  agent,
  conversationId,
  onOpenFile,
}: {
  agent: string
  conversationId: string | null
  onOpenFile: (path: string) => void
}) {
  const [scope, setScope] = React.useState<ChangesScope>('turn')
  const [selected, setSelected] = React.useState<string | null>(null)
  const changes = useConversationChanges(conversationId)
  const patch = useChangePatch(conversationId, selected, scope)
  const state: PatchState | null = !selected
    ? null
    : patch.data
      ? { status: 'ready', patch: patch.data }
      : patch.isError
        ? { status: 'failed' }
        : { status: 'loading' }
  return (
    <ChangesTab
      agent={agent}
      data={changes.data}
      loadFailed={changes.isError}
      scope={scope}
      onScopeChange={(next) => {
        setScope(next)
        setSelected(null)
      }}
      selected={selected}
      onSelect={setSelected}
      patch={state}
      onOpenFile={onOpenFile}
    />
  )
}
