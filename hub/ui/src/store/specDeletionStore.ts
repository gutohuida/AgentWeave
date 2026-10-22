import { create } from 'zustand'

/** What the last "Delete document" removed, kept so the page the operator lands on can say so
 *  (F829). The deleted document's own panel is gone by then, so it cannot hold the sentence. */
export interface KeptWork {
  task_id: string
  branch?: string
  unmerged_commits?: number
  uncommitted?: boolean
  error?: string
}

export interface SpecDeletionNotice {
  path: string
  title: string
  tasks: number
  /** Checkouts of the deleted tasks that held work and were therefore kept (F838). */
  kept: KeptWork[]
}

interface SpecDeletionState {
  notice: SpecDeletionNotice | null
  set: (notice: SpecDeletionNotice) => void
  clear: () => void
}

export const useSpecDeletionStore = create<SpecDeletionState>((set) => ({
  notice: null,
  set: (notice) => set({ notice }),
  clear: () => set({ notice: null }),
}))
