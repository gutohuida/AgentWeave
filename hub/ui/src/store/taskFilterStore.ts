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
}

export const useTaskFilterStore = create<TaskFilterState>((set) => ({
  activeTaskIds: null,
  setActiveTaskIds: (ids) => set({ activeTaskIds: ids }),
  clearActiveTaskIds: () => set({ activeTaskIds: null }),
}))
