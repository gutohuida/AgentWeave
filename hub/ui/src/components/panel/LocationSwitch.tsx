import { Segmented } from '@/components/ui/segmented'

/** Where a Files or Terminal tab points: the conversation agent's own worktree, or the project's
 *  registered directory (roadmap `a-side-panel-worth-keeping-open-…`, operator 2026-11-12). */
export type PanelLocation = 'worktree' | 'root'

export function LocationSwitch({ agent, value, onChange }: { agent: string; value: PanelLocation; onChange: (next: PanelLocation) => void }) {
  return (
    <Segmented<PanelLocation>
      label="Where"
      size="xs"
      value={value}
      onChange={onChange}
      options={[
        { value: 'worktree', label: `${agent}’s worktree` },
        { value: 'root', label: 'Project root' },
      ]}
    />
  )
}
