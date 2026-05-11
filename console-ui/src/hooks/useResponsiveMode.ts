import { useState, useEffect, useCallback, useSyncExternalStore } from 'react'

type ViewMode = 'auto' | 'desktop' | 'mobile'
type EffectiveMode = 'desktop' | 'mobile'

const STORAGE_KEY = 'nanobot-view-mode'
const MOBILE_BREAKPOINT = 768
const TABLET_MAX_WIDTH = 1024

// Shared state so all hook instances stay in sync
let _mode: ViewMode = (() => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'desktop' || stored === 'mobile') return stored
  } catch {}
  return 'auto'
})()

const listeners = new Set<() => void>()

function getMode() {
  return _mode
}

function subscribe(cb: () => void) {
  listeners.add(cb)
  return () => { listeners.delete(cb) }
}

function setModeGlobal(next: ViewMode) {
  _mode = next
  try {
    if (next === 'auto') localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, next)
  } catch {}
  listeners.forEach(cb => cb())
}

function getViewportMobile(): boolean {
  return typeof window !== 'undefined' && window.innerWidth < MOBILE_BREAKPOINT
}

function getViewportTablet(): boolean {
  return typeof window !== 'undefined' && window.innerWidth >= MOBILE_BREAKPOINT && window.innerWidth <= TABLET_MAX_WIDTH
}

function getViewportLandscape(): boolean {
  return typeof window !== 'undefined' && window.innerWidth > window.innerHeight
}

export function useResponsiveMode() {
  const mode = useSyncExternalStore(subscribe, getMode, getMode)
  const [viewportMobile, setViewportMobile] = useState(getViewportMobile)
  const [viewportTablet, setViewportTablet] = useState(getViewportTablet)
  const [viewportLandscape, setViewportLandscape] = useState(getViewportLandscape)

  useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
    const handler = (e: MediaQueryListEvent) => setViewportMobile(e.matches)
    mql.addEventListener('change', handler)
    setViewportMobile(mql.matches)
    return () => mql.removeEventListener('change', handler)
  }, [])

  useEffect(() => {
    const update = () => {
      setViewportTablet(getViewportTablet())
      setViewportLandscape(getViewportLandscape())
    }
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])

  const effectiveMode: EffectiveMode =
    mode === 'auto' ? (viewportMobile ? 'mobile' : 'desktop') : mode

  const setMode = useCallback((next: ViewMode) => {
    setModeGlobal(next)
  }, [])

  return {
    mode,
    effectiveMode,
    isMobile: effectiveMode === 'mobile',
    isTablet: mode === 'auto' ? viewportTablet : false,
    isLandscape: viewportLandscape,
    setMode,
  }
}
