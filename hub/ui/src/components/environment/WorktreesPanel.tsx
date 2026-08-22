import { SettingsSection } from '@/components/environment/SettingsSection'
import { EmptyState } from '@/components/common/EmptyState'

export function WorktreesPanel() {
  return (
    <SettingsSection
      title="Worktrees"
      description="Isolated agent worktrees and conflicts are managed from this project workspace."
    >
      <div className="py-4">
        <EmptyState
          icon="file_vcs"
          title="No worktree activity"
          description="Isolated workspaces appear here when an agent starts work that needs its own checkout."
        />
      </div>
    </SettingsSection>
  )
}
