import { useEffect, useRef, useState, useCallback } from 'react'

interface VersionInfo {
  hash: string
  timestamp: number
  built_at: string
}

interface VersionCheckState {
  currentVersion: VersionInfo | null
  updateAvailable: boolean
  dismiss: () => void
  refresh: () => void
}

const POLL_INTERVAL = 60_000

export function useVersionCheck(): VersionCheckState {
  const [currentVersion, setCurrentVersion] = useState<VersionInfo | null>(null)
  const [updateAvailable, setUpdateAvailable] = useState(false)
  const initialHash = useRef<string | null>(null)

  const fetchVersion = useCallback(async () => {
    try {
      const res = await fetch(`/version.json?_t=${Date.now()}`, { cache: 'no-store' })
      if (!res.ok) return
      const data: VersionInfo = await res.json()
      setCurrentVersion(data)

      if (initialHash.current === null) {
        initialHash.current = data.hash
      } else if (data.hash !== initialHash.current) {
        setUpdateAvailable(true)
      }
    } catch {
      // version.json 不存在时静默忽略（开发模式等）
    }
  }, [])

  useEffect(() => {
    fetchVersion()
    const id = setInterval(fetchVersion, POLL_INTERVAL)
    return () => clearInterval(id)
  }, [fetchVersion])

  const dismiss = useCallback(() => setUpdateAvailable(false), [])
  const refresh = useCallback(() => window.location.reload(), [])

  return { currentVersion, updateAvailable, dismiss, refresh }
}
