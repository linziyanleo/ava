import { create } from 'zustand'

export type TaskFloaterPanel = 'background' | 'scheduled' | 'artifacts'
export type TaskFloaterBgView = 'all' | 'current' | 'history'

interface TaskFloaterOpenOptions {
  panel?: TaskFloaterPanel
  bgView?: TaskFloaterBgView
  taskId?: string | null
  traceId?: string | null
  chainId?: string | null
}

interface TaskFloaterState {
  isOpen: boolean
  panel: TaskFloaterPanel
  bgView: TaskFloaterBgView
  selectedTaskId: string | null
  traceId: string | null
  chainId: string | null
  open: (options?: string | TaskFloaterOpenOptions) => void
  setPanel: (panel: TaskFloaterPanel) => void
  setBgView: (bgView: TaskFloaterBgView) => void
  close: () => void
}

export const useTaskFloater = create<TaskFloaterState>((set) => ({
  isOpen: false,
  panel: 'background',
  bgView: 'all',
  selectedTaskId: null,
  traceId: null,
  chainId: null,
  open: (options) => {
    if (typeof options === 'string') {
      set({
        isOpen: true,
        panel: 'background',
        bgView: 'all',
        selectedTaskId: options,
        traceId: null,
        chainId: null,
      })
      return
    }
    set({
      isOpen: true,
      panel: options?.panel ?? 'background',
      bgView: options?.bgView ?? 'all',
      selectedTaskId: options?.taskId ?? null,
      traceId: options?.traceId ?? null,
      chainId: options?.chainId ?? null,
    })
  },
  setPanel: (panel) => set({ panel }),
  setBgView: (bgView) => set({ bgView }),
  close: () => set({
    isOpen: false,
    panel: 'background',
    bgView: 'all',
    selectedTaskId: null,
    traceId: null,
    chainId: null,
  }),
}))

interface AvaDesktopApi {
  onOpenTaskFloater?: (callback: (payload?: { taskId?: string | null }) => void) => () => void
}

let uninstallDesktopBridge: (() => void) | null = null

export function installTaskFloaterDesktopBridge() {
  if (uninstallDesktopBridge) return uninstallDesktopBridge

  const api = (window as unknown as { avaDesktop?: AvaDesktopApi }).avaDesktop
  if (!api?.onOpenTaskFloater) return () => {}

  uninstallDesktopBridge = api.onOpenTaskFloater((payload) => {
    useTaskFloater.getState().open({
      panel: 'background',
      bgView: 'all',
      taskId: payload?.taskId ?? null,
    })
  })

  return () => {
    uninstallDesktopBridge?.()
    uninstallDesktopBridge = null
  }
}
