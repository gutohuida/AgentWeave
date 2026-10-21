import { useWorktreeConflicts, useWorktrees } from '@/api/workspace'
import { WorktreesSettings } from '../OtherSettings'

/** Project settings → Worktrees, on the Hub: `GET /worktrees` and its conflict check, both
 *  refetched by `useSSE` on run and task events (F250). Reading them provisions nothing. */
export function WorktreesSection() {
  const { data, error } = useWorktrees()
  const conflicts = useWorktreeConflicts()
  return (
    <WorktreesSettings
      listing={data}
      error={Boolean(error)}
      conflicts={conflicts.data?.conflicts}
      conflictsError={Boolean(conflicts.error)}
    />
  )
}
