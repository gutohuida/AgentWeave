export function WorktreesPanel() {
  return (
    <section className="p-4" aria-labelledby="worktrees-heading">
      <h2 id="worktrees-heading" className="text-sm font-semibold">Worktrees</h2>
      <p className="mt-2 text-xs" style={{ color: 'var(--text-3)' }}>
        Isolated agent worktrees and conflicts are managed from this project workspace.
      </p>
    </section>
  )
}
