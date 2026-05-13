import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

interface DeepLinkPayload {
  path?: string
}

interface AvaDesktopApi {
  onDeepLink?: (callback: (payload: DeepLinkPayload) => void) => () => void
  rendererReady?: () => Promise<{ ok: boolean }>
}

function desktopApi(): AvaDesktopApi | null {
  return (window as unknown as { avaDesktop?: AvaDesktopApi }).avaDesktop || null
}

export function useDeepLink() {
  const navigate = useNavigate()

  useEffect(() => {
    const api = desktopApi()
    if (!api?.onDeepLink) return

    const openDeepLink = (payload: DeepLinkPayload) => {
      if (typeof payload.path !== 'string' || !payload.path.startsWith('/')) return
      navigate(payload.path)
    }

    const unsubscribe = api.onDeepLink(openDeepLink)
    void api.rendererReady?.()
    return unsubscribe
  }, [navigate])
}
