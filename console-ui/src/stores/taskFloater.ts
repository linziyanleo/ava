import { create } from 'zustand'

interface TaskFloaterState {
  isOpen: boolean
  selectedTaskId: string | null
  open: (taskId?: string) => void
  close: () => void
}

export const useTaskFloater = create<TaskFloaterState>((set) => ({
  isOpen: false,
  selectedTaskId: null,
  open: (taskId) => set({ isOpen: true, selectedTaskId: taskId ?? null }),
  close: () => set({ isOpen: false, selectedTaskId: null }),
}))
