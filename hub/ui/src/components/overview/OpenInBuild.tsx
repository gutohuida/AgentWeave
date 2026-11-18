import { useProjectBuilds } from '@/api/projectBuilds'
import { Icon } from '@/components/common/Icon'
import { buildDestination, buildHref, goTo } from '@/lib/navigation'

/** "Open in its build" for a running turn whose task belongs to a build, shown only while that
 *  build is running (Overview lists running work). It opens the build view at the task (FR-15). */
export function OpenInBuild({ projectId, buildId, task }: { projectId: string; buildId: string; task: string }) {
  const { data: builds = [], error } = useProjectBuilds()
  // The link is an extra on a running row: when the builds cannot be read it is left out, not guessed.
  if (error || !builds.some((b) => b.id === buildId && b.state === 'running')) return null
  return (
    <a
      className="aw-ov-build-link"
      href={buildHref(projectId, buildId, task)}
      onClick={(event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return
        event.preventDefault()
        goTo(buildDestination(projectId, buildId, { task }))
      }}
    >
      Open in its build
      <Icon name="arrow_forward" size={12} />
    </a>
  )
}
