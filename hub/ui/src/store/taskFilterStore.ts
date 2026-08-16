import { create } from 'zustand'

interface TaskFilterState {
  /** Which tasks the board should show, set from a screen the board is not part of — a coverage
   *  row's task-count link (`SpecCoverageBar.tsx`), which switches to the Tasks tab and needs the
   *  board already filtered once it mounts. `null` means unfiltered, the board's normal state.
   *
   *  Global rather than route-carried (`design.md` D7): this is one more piece of local filter
   *  state alongside `TasksBoard.tsx`'s existing `activeFilter`, not a new filtering mechanism —
   *  a store is just what lets a screen outside the board set it. */
  activeTaskIds: string[] | null
  setActiveTaskIds: (ids: string[]) => void
  clearActiveTaskIds: () => void
  /** The one task a screen outside the board wants opened — the command palette's "open task"
   *  action (D3), which switches to the Tasks tab and needs the drawer open once it mounts, same
   *  shape as `activeTaskIds` above. The board consumes and clears it on mount/update rather than
   *  leaving it set, so navigating away and back to Tasks does not reopen a stale drawer. */
  pendingOpenTaskId: string | null
  setPendingOpenTaskId: (id: string) => void
  clearPendingOpenTaskId: () => void
}

export const useTaskFilterStore = create<TaskFilterState>((set) => ({
  activeTaskIds: null,
  setActiveTaskIds: (ids) => set({ activeTaskIds: ids }),
  clearActiveTaskIds: () => set({ activeTaskIds: null }),
  pendingOpenTaskId: null,
  setPendingOpenTaskId: (id) => set({ pendingOpenTaskId: id }),
  clearPendingOpenTaskId: () => set({ pendingOpenTaskId: null }),
}))
