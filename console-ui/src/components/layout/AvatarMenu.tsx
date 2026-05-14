import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, LogOut, Moon, Settings, Sun, User } from 'lucide-react'
import { cn } from '../../lib/utils'
import { useAuth } from '../../stores/auth'
import { useTheme } from '../../stores/theme'

function userInitial(username?: string) {
  return (username?.trim().charAt(0) || 'U').toUpperCase()
}

export default function AvatarMenu() {
  const { user, logout } = useAuth()
  const { isDark, toggleTheme } = useTheme()
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('pointerdown', onPointerDown)
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('pointerdown', onPointerDown)
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const itemClass = 'flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]'

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex h-10 items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] px-2 text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--bg-tertiary)] text-xs font-semibold">
          {userInitial(user?.username)}
        </span>
        <span className="hidden min-w-0 text-left sm:block">
          <span className="block max-w-28 truncate text-xs font-medium">{user?.username}</span>
        </span>
        <ChevronDown className={cn('h-3.5 w-3.5 text-[var(--text-secondary)] transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div
          className="absolute right-0 top-full z-50 mt-2 w-56 rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-2 shadow-2xl"
          role="menu"
        >
          <div className="mb-1 flex items-center gap-2 border-b border-[var(--border)] px-2 pb-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--bg-tertiary)] text-sm font-semibold">
              <User className="h-4 w-4 text-[var(--text-secondary)]" />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-[var(--text-primary)]">{user?.username}</span>
            </span>
          </div>

          <button
            type="button"
            onClick={() => {
              toggleTheme()
              setOpen(false)
            }}
            className={itemClass}
            role="menuitem"
          >
            {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            {isDark ? '切换到白天模式' : '切换到黑夜模式'}
          </button>

          <Link to="/settings" className={itemClass} role="menuitem" onClick={() => setOpen(false)}>
            <Settings className="h-4 w-4" />
            Settings
          </Link>

          <button
            type="button"
            onClick={() => {
              logout()
              setOpen(false)
            }}
            className={cn(itemClass, 'text-[var(--danger)] hover:text-[var(--danger)]')}
            role="menuitem"
          >
            <LogOut className="h-4 w-4" />
            退出登录
          </button>
        </div>
      )}
    </div>
  )
}
