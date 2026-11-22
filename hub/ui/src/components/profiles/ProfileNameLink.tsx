import type { ReactNode } from 'react'
import { ProfileLink } from '@/components/agents/ProfileLink'
import { agentSettingsDestination, goTo, profileHref, type AgentSettingsSection } from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'

/** A profile's name, wherever the app prints it, as the way to that profile's page (FR-15): the
 *  thread bar, a task card and its story, a build page. It addresses the open project; with none
 *  open (the mock, a test without a project) the name is plain text. */
export function ProfileNameLink({
  name,
  section,
  className,
  children,
}: {
  name: string
  section?: AgentSettingsSection
  className?: string
  children?: ReactNode
}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  if (!projectId) return <span className={className}>{children ?? name}</span>
  return (
    <ProfileLink
      name={name}
      href={profileHref(projectId, name, section)}
      onOpen={() => goTo(agentSettingsDestination(projectId, name, section))}
      className={className}
    >
      {children}
    </ProfileLink>
  )
}
