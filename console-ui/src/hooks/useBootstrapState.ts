import { useCallback, useEffect, useState } from 'react'

export interface BootstrapState {
  stage: string
  message: string
  error?: string
  stderrTail?: string
  logDir?: string
  nanobotRoot?: string
  coreEndpoint?: string
}

interface AvaDesktopApi {
  getBootstrapState?: () => Promise<BootstrapState>
  onBootstrapState?: (callback: (state: BootstrapState) => void) => () => void
  retryCore?: () => Promise<{ ok: boolean; error?: string }>
}

function desktopApi(): AvaDesktopApi | null {
  return (window as unknown as { avaDesktop?: AvaDesktopApi }).avaDesktop || null
}

export function useBootstrapState() {
  const [state, setState] = useState<BootstrapState | null>(null)

  useEffect(() => {
    const api = desktopApi()
    if (!api?.getBootstrapState || !api.onBootstrapState) return

    let disposed = false
    void api.getBootstrapState().then((snapshot) => {
      if (!disposed) setState(snapshot)
    })
    const unsubscribe = api.onBootstrapState((next) => {
      if (!disposed) setState(next)
    })

    return () => {
      disposed = true
      unsubscribe()
    }
  }, [])

  const retry = useCallback(async () => {
    const api = desktopApi()
    if (!api?.retryCore) return
    await api.retryCore()
  }, [])

  return { state, retry }
}
