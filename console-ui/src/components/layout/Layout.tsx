import { useRef, useEffect } from 'react'
import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { cn } from '../../lib/utils'
import { useResponsiveMode } from '../../hooks/useResponsiveMode'
import { useBgTaskNotifications } from '../../hooks/useBgTaskNotifications'
import { installTaskFloaterDesktopBridge } from '../../stores/taskFloater'
import { IS_MOCK_SANDBOX } from '../../lib/env'
import { navItems } from './navItems'
import TaskFloater from '../tasks/TaskFloater'
import TopBar from './TopBar'
import BootstrapBanner from './BootstrapBanner'

function MobileBottomNav() {
  const location = useLocation()
  const scrollRef = useRef<HTMLDivElement>(null)
  const activeRef = useRef<HTMLAnchorElement>(null)

  useEffect(() => {
    if (activeRef.current && scrollRef.current) {
      const container = scrollRef.current
      const el = activeRef.current
      const left = el.offsetLeft - container.offsetWidth / 2 + el.offsetWidth / 2
      container.scrollTo({ left: Math.max(0, left), behavior: 'smooth' })
    }
  }, [location.pathname])

  return (
    <nav
      ref={scrollRef}
      className="fixed bottom-0 left-0 right-0 z-30 flex items-stretch bg-[var(--bg-secondary)] border-t border-[var(--border)] overflow-x-auto scrollbar-none safe-bottom"
      style={{ WebkitOverflowScrolling: 'touch', paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      {navItems.map(item => {
        const isActive =
          item.to === '/'
            ? location.pathname === '/'
            : location.pathname.startsWith(item.to)
        return (
          <NavLink
            key={item.to}
            to={item.to}
            ref={isActive ? activeRef : undefined}
            className={cn(
              'flex flex-col items-center justify-center gap-0.5 min-w-[4rem] py-2 px-2 text-center transition-colors shrink-0',
              isActive
                ? 'text-[var(--accent)]'
                : 'text-[var(--text-secondary)]',
            )}
          >
            <item.icon className="w-5 h-5" />
            <span className={cn('text-[10px] leading-tight', isActive ? 'font-semibold' : 'font-medium')}>{item.label}</span>
          </NavLink>
        )
      })}
    </nav>
  )
}

export default function Layout() {
  const { isMobile } = useResponsiveMode()
  const location = useLocation()
  const isSettingsRoute = location.pathname.startsWith('/settings')
  useBgTaskNotifications()

  useEffect(() => installTaskFloaterDesktopBridge(), [])

  if (isMobile) {
    return (
      <div className="flex flex-col h-dvh">
        <BootstrapBanner />
        <main className="flex-1 min-h-0 overflow-y-auto">
          {IS_MOCK_SANDBOX && (
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-[var(--ava-warning-border)] bg-[var(--ava-warning-soft)] px-3 py-1 text-xs font-medium text-[var(--ava-warning)]">
              MOCK SANDBOX
            </div>
          )}
          <Outlet />
        </main>
        <TaskFloater />
        <MobileBottomNav />
      </div>
    )
  }

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <TopBar />
      <BootstrapBanner />
      <main className={cn('min-h-0 flex-1', isSettingsRoute ? 'overflow-hidden' : 'overflow-y-auto')}>
        <Outlet />
      </main>
      <TaskFloater />
    </div>
  )
}
