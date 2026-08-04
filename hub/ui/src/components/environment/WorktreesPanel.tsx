import { SettingsSection } from '@/components/environment/SettingsSection'

export function WorktreesPanel() {
  return (
    <SettingsSection
      title="Worktrees"
      description="Isolated agent worktrees and conflicts are managed from this project workspace."
    >
      <div className="py-6 text-xs" style={{ color: 'var(--text-3)' }}>
        No worktree activity yet.
      </div>
    </SettingsSection>
  )
}
