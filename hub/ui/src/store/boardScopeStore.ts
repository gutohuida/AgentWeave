import { create } from 'zustand'

/** What the Tasks board shows: every task (as the board always has), the tasks that belong to no
 *  spec, or exactly one spec's tasks. */
export type BoardScope = { kind: 'all' } | { kind: 'none' } | { kind: 'spec'; id: string }

export const ALL_SCOPE: BoardScope = { kind: 'all' }
const SCOPE_KEY = 'aw.boardScope'

/** The scope this window last chose in a project, or All. Read from local storage, as the board's
 *  column folds are: the choice belongs to the window, not to the Hub. */
export function loadScope(projectId: string | null): BoardScope {
  if (!projectId) return ALL_SCOPE
  try {
    const parsed = JSON.parse(localStorage.getItem(`${SCOPE_KEY}.${projectId}`) ?? 'null') as BoardScope | null
    if (parsed?.kind === 'none') return { kind: 'none' }
    if (parsed?.kind === 'spec' && typeof parsed.id === 'string' && parsed.id) return { kind: 'spec', id: parsed.id }
  } catch {
    // Unreadable storage is no scope.
  }
  return ALL_SCOPE
}

interface BoardScopeState {
  /** Scopes chosen or read since this page loaded, by project id; a project absent here reads from
   *  storage. */
  scopes: Record<string, BoardScope>
  setScope: (projectId: string, scope: BoardScope) => void
}

export const useBoardScopeStore = create<BoardScopeState>((set) => ({
  scopes: {},
  setScope: (projectId, scope) => {
    try {
      localStorage.setItem(`${SCOPE_KEY}.${projectId}`, JSON.stringify(scope))
    } catch {
      // Persistence is optional.
    }
    set((state) => ({ scopes: { ...state.scopes, [projectId]: scope } }))
  },
}))
