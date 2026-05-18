import { NavLink, useLocation } from 'react-router-dom'
import { Bot } from 'lucide-react'
import { TaskPreviewBar } from '../tasks/TaskPreviewBar'
import { useTaskFloater } from '../../stores/taskFloater'
import { cn } from '../../lib/utils'
import { IS_MOCK_SANDBOX } from '../../lib/env'
import { navItems } from './navItems'
import AvatarMenu from './AvatarMenu'

export default function TopBar() {
  const location = useLocation()
  const { open } = useTaskFloater()

  return (
    <header className="topbar z-30 flex h-14 shrink-0 items-center border-b border-[var(--border)] bg-[var(--bg-secondary)]">
      <div className="flex h-full min-w-0 shrink-0 items-center gap-4 px-4">
        <NavLink to="/" className="flex items-center gap-2">
          <Bot className="h-6 w-6 text-[var(--accent)]" />
          <span className="font-semibold tracking-normal text-[var(--text-primary)]">AVA</span>
        </NavLink>
        {IS_MOCK_SANDBOX && (
          <span className="inline-flex rounded-full bg-[var(--ava-warning-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--ava-warning)]">
            MOCK SANDBOX
          </span>
        )}
        <nav className="flex h-full items-center gap-1">
          {navItems.map((item) => {
            const isActive = item.to === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(item.to)
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={cn(
                  'inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-[var(--accent)] text-white'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]',
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            )
          })}
        </nav>
      </div>

      <div className="min-w-0 flex-1">
        <TaskPreviewBar
          density="topbar"
          onOpenTask={(taskId) => open(taskId)}
          onOpenList={() => open()}
        />
      </div>

      <div className="flex h-full shrink-0 items-center px-4">
        <AvatarMenu />
      </div>
    </header>
  )
}
