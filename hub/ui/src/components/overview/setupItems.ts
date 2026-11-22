import type { ProjectSetupItem } from '@/api/projects'
import { agentSettingsDestination, environmentDestination, goTo, projectDestination } from '@/lib/navigation'
import type { SetupItem } from './SetupList'

export const QUICKSTART_URL = 'https://gutohuida.github.io/AgentWeave/getting-started/quickstart/'

/** Scroll an element into view once its screen has rendered it (the navigation is asynchronous). */
export function scrollToAnchor(id: string): void {
  let tries = 0
  const timer = window.setInterval(() => {
    const el = document.getElementById(id)
    tries += 1
    if (el) {
      el.scrollIntoView({ block: 'center' })
      window.clearInterval(timer)
    } else if (tries > 30) {
      window.clearInterval(timer)
    }
  }, 100)
}

const LOCATE_PROJECT_ANCHOR = 'locate-project'

const WHY: Record<NonNullable<ProjectSetupItem['reason']>, string> = {
  not_installed: 'its coding CLI is not installed on this machine',
  not_logged_in: 'its coding CLI is not logged in on this machine',
  no_model: 'it has no model chosen',
  cannot_run: 'its coding CLI cannot run',
}

export function describeSetupItem(
  item: ProjectSetupItem,
  projectId: string,
  onOfferProfiles?: () => void,
): SetupItem {
  const base = { id: item.id, key: item.key, dismissable: item.dismissable }
  switch (item.key) {
    case 'folder':
      return {
        ...base,
        title: 'Locate the project folder',
        detail: 'The folder this project was opened on is no longer where it was. Nothing can run until it is found.',
        action: {
          label: 'Locate it',
          onClick: () => {
            goTo(environmentDestination(projectId, 'general'))
            scrollToAnchor(LOCATE_PROJECT_ANCHOR)
          },
        },
      }
    case 'repository':
      return {
        ...base,
        title: 'Make the folder a git repository',
        detail: 'Without one, every profile writes in the same folder: none gets a branch of its own, and nothing is merged.',
        action: {
          label: 'Make it a repository…',
          onClick: () => {
            goTo(environmentDestination(projectId, 'general'))
            scrollToAnchor('make-repository')
          },
        },
      }
    case 'profiles':
      return {
        ...base,
        title: 'Add a builder and a checker',
        detail: 'A build needs two profiles: one builds each task and the other checks it. Name them and choose what runs each.',
        action: { label: 'Add both…', onClick: () => onOfferProfiles?.() },
      }
    case 'specification':
      return {
        ...base,
        title: 'Start your specifications',
        detail: 'This project has no specification documents yet. A profile can write down what its code does, or interview you to plan it.',
        action: { label: 'Start…', onClick: () => goTo(projectDestination(projectId, 'spec')) },
      }
    case 'can-run': {
      const agent = item.agent ?? ''
      const why = item.reason ? WHY[item.reason] : 'it cannot run'
      return {
        ...base,
        title: `${agent} cannot run: ${why}`,
        detail:
          item.reason === 'cannot_run' && item.detail
            ? item.detail
            : 'Its runs fail at launch. Fix that on this machine, or give it a model whose coding CLI runs.',
        action: {
          label: 'Choose its model',
          onClick: () => {
            goTo(agentSettingsDestination(projectId, agent, 'running'))
          },
        },
      }
    }
  }
}

/** What the rail names on hover. */
export const setupTitle = (item: ProjectSetupItem): string => describeSetupItem(item, '').title
