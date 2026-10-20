import { create } from 'zustand'

/** The toast queue behind `<Toaster />` (components/ui/toast.tsx). Call `toast()` from anywhere. */
export type ToastTone = 'neutral' | 'success' | 'error'

export interface ToastInput {
  title: string
  description?: string
  tone?: ToastTone
  /** One action, e.g. Undo. Runs and dismisses. */
  action?: { label: string; onClick: () => void }
  duration?: number
}

interface ToastItem extends ToastInput {
  id: number
  open: boolean
}

interface ToastStore {
  items: ToastItem[]
  push: (input: ToastInput) => void
  close: (id: number) => void
  remove: (id: number) => void
}

let nextId = 1

export const useToastStore = create<ToastStore>((set) => ({
  items: [],
  push: (input) => set((s) => ({ items: [...s.items.slice(-2), { ...input, id: nextId++, open: true }] })),
  close: (id) => set((s) => ({ items: s.items.map((t) => (t.id === id ? { ...t, open: false } : t)) })),
  remove: (id) => set((s) => ({ items: s.items.filter((t) => t.id !== id) })),
}))

export function toast(input: ToastInput): void {
  useToastStore.getState().push(input)
}

