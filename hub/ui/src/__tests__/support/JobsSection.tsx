import { ProjectSettingsScreen } from '@/components/settings/ProjectSettingsScreen'
import { useTaskFilterStore } from '@/store/taskFilterStore'

/** The Jobs view where it now lives, Project settings › Jobs (leaner-navigation FR-6), for the
 *  Jobs view tests. A loop's open tasks reach `onOpenTasks` the way the section sends them: the
 *  board's task filter is set, then the app navigates to Tasks. */
export function JobsSection({ onOpenTasks, focus = null }: { onOpenTasks?: (taskIds: string[]) => void; focus?: string | null }) {
  return (
    <ProjectSettingsScreen
      section="jobs"
      focus={focus}
      onSelectSection={() => undefined}
      onNavigate={(value) => {
        if (value === 'tasks') onOpenTasks?.(useTaskFilterStore.getState().activeTaskIds ?? [])
      }}
    />
  )
}
