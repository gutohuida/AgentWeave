import * as React from 'react'
import type { SetupItem } from '@/components/overview/SetupList'
import { toast } from '@/lib/toast'
import type { MockRoute } from './routes'

// mock state: what each project still needs (`a-project-says-what-it-still-needs`). The recorded
// projects have nothing missing; this shows the list as it reads for a Terra copied into a folder
// without git, with QA2 on Codex while Codex is not logged in, and for an agentless "huida".
// Dismissals are shared by every screen, so dismissing on Overview clears the rail and settings.

const dismissed = new Set<string>()
const listeners = new Set<() => void>()
let version = 0
const subscribe = (fn: () => void) => {
  listeners.add(fn)
  return () => listeners.delete(fn)
}
const bump = () => {
  version += 1
  listeners.forEach((fn) => fn())
}

export function dismissSetup(id: string) {
  dismissed.add(id)
  bump()
}
export function restoreSetup(id: string) {
  dismissed.delete(id)
  bump()
}

function terraItems(go: (route: MockRoute) => void): SetupItem[] {
  return [
    {
      id: 'repository',
      key: 'repository',
      title: 'Make the folder a git repository',
      detail: 'Without one, every agent writes in the same folder: none gets a branch of its own, and nothing is merged.',
      action: { label: 'Make it a repository…', onClick: () => go({ kind: 'settings', section: 'general' }) },
      dismissable: true,
    },
    {
      id: 'can-run-QA2',
      key: 'can-run',
      title: 'QA2 cannot run: Codex is not logged in',
      detail: 'Its turns fail at launch. Log in to Codex on this machine, or give QA2 a model whose coding agent is logged in.',
      action: { label: 'Choose its model', onClick: () => go({ kind: 'agent-settings', agent: 'QA2', section: 'running' }) },
    },
  ]
}

function huidaItems(): SetupItem[] {
  return [
    {
      id: 'agent',
      key: 'agent',
      title: 'Add an agent',
      detail: 'A project with no agent has nobody to give work to.',
      action: { label: 'Add an agent', onClick: () => toast({ title: 'Add an agent', description: 'Opens the new agent dialog (unchanged in this mock).' }) },
    },
  ]
}

/** The items still shown for Terra, and the ones dismissed, re-read whenever a dismissal changes. */
export function useTerraSetup(go: (route: MockRoute) => void) {
  React.useSyncExternalStore(subscribe, () => version)
  const all = terraItems(go)
  return { items: all.filter((i) => !dismissed.has(i.id)), dismissed: all.filter((i) => dismissed.has(i.id)) }
}

/** The rail's titles per project. */
export function useSetupTitles(): (projectId: string) => string[] {
  React.useSyncExternalStore(subscribe, () => version)
  return (projectId) => {
    if (projectId === 'proj-cd006955cbe2') return terraItems(() => {}).filter((i) => !dismissed.has(i.id)).map((i) => i.title)
    if (projectId === 'proj-a92672bc3fa1') return huidaItems().map((i) => i.title)
    return []
  }
}
