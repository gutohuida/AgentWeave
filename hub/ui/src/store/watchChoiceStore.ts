// What the Watch tab is watching, per project (`the-side-panel-s-watch-tab-...`, FR-7).
//
// Kept per project, not per conversation: switching the main view to any other conversation leaves
// the tab on the same agent and conversation. Only the operator's own choices are stored: the agent,
// and a conversation they picked by hand. A conversation the tab merely follows is derived from the
// agent's state (`watchModel.ts`), so it needs no storage and cannot go stale.

import { create } from 'zustand'

export const WATCH_CHOICE_STORAGE_KEY = 'aw.panel.watch.v1'

export interface WatchChoice {
  agent: string | null
  /** A conversation picked by hand; null while the tab follows the agent. */
  conversationId: string | null
}

export const NO_WATCH_CHOICE: WatchChoice = Object.freeze({ agent: null, conversationId: null })

type StoredChoices = Record<string, WatchChoice>

function load(): StoredChoices {
  if (typeof window === 'undefined') return {}
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(WATCH_CHOICE_STORAGE_KEY) ?? '{}')
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {}
    const out: StoredChoices = {}
    for (const [projectId, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof value !== 'object' || value === null) continue
      const record = value as Record<string, unknown>
      const agent = typeof record.agent === 'string' && record.agent ? record.agent : null
      out[projectId] = {
        agent,
        conversationId: agent && typeof record.conversationId === 'string' && record.conversationId ? record.conversationId : null,
      }
    }
    return out
  } catch {
    return {}
  }
}

function save(choices: StoredChoices): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(WATCH_CHOICE_STORAGE_KEY, JSON.stringify(choices))
  } catch {
    // Best-effort, like the panel's other per-project state.
  }
}

interface WatchChoiceState {
  choices: StoredChoices
  /** Choosing an agent drops any hand-picked conversation: the tab follows the new agent. */
  chooseAgent: (projectId: string, agent: string) => void
  /** A conversation picked by hand stays until an agent is chosen again. */
  pickConversation: (projectId: string, conversationId: string) => void
}

export const useWatchChoiceStore = create<WatchChoiceState>()((set, get) => {
  const write = (projectId: string, choice: WatchChoice) => {
    const choices = { ...get().choices, [projectId]: choice }
    save(choices)
    set({ choices })
  }
  return {
    choices: load(),
    chooseAgent: (projectId, agent) => write(projectId, { agent, conversationId: null }),
    pickConversation: (projectId, conversationId) =>
      write(projectId, { agent: get().choices[projectId]?.agent ?? null, conversationId }),
  }
})

export function selectWatchChoice(state: Pick<WatchChoiceState, 'choices'>, projectId: string): WatchChoice {
  return state.choices[projectId] ?? NO_WATCH_CHOICE
}
