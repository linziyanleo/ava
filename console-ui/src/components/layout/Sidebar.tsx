import { useState, useCallback, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import {
  Bot,
  PanelLeftClose,
  User,
  Users,
  LogOut,
  Sun,
  Moon,
} from 'lucide-react'
import { useAuth } from '../../stores/auth'
import { useTheme } from '../../stores/theme'
import { cn } from '../../lib/utils'
import { filterNavItems } from './navItems'

const STORAGE_KEY = 'nanobot-sidebar-collapsed'

function FixedTooltip({ label, children }: { label: string; children: ReactNode }) {
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)

  const handleEnter = useCallback((e: React.MouseEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setPos({ top: rect.top + rect.height / 2, left: rect.right + 8 })
  }, [])

  const handleLeave = useCallback(() => setPos(null), [])

  return (
    <div onMouseEnter={handleEnter} onMouseLeave={handleLeave}>
      {children}
      {pos && (
        <div
          className="fixed z-[9999] px-2 py-1 rounded-md bg-[var(--bg-tertiary)] border border-[var(--border)] text-xs text-[var(--text-primary)] whitespace-nowrap shadow-lg pointer-events-none"
          style={{ top: pos.top, left: pos.left, transform: 'translateY(-50%)' }}
        >
          {label}
        </div>
      )}
    </div>
  )
}

export default function Sidebar() {
  const { user, logout, isAdmin } = useAuth()
  const { isDark, toggleTheme } = useTheme()
  const navItems = filterNavItems(user?.role ?? null)
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === '1'
    } catch {
      return false
    }
  })

  const toggle = () => {
    const next = !collapsed
    setCollapsed(next)
    try {
      localStorage.setItem(STORAGE_KEY, next ? '1' : '0')
    } catch {
      /* localStorage unavailable */
    }
  }

  return (
    <aside
      className={cn(
        'shrink-0 h-screen bg-[var(--bg-secondary)] border-r border-[var(--border)] flex flex-col sticky left-0 top-0 z-20 transition-all duration-200',
        collapsed ? 'w-16' : 'w-60',
      )}
    >
      <div
        className={cn(
          'border-b border-[var(--border)] flex items-center group/header',
          collapsed ? 'p-3 justify-center' : 'p-5 gap-3',
        )}
      >
        {collapsed ? (
          <FixedTooltip label="展开侧边栏">
            <button onClick={toggle}>
              <Bot className="w-7 h-7 text-[var(--accent)] shrink-0" />
            </button>
          </FixedTooltip>
        ) : (
          <>
            <Bot className="w-7 h-7 text-[var(--accent)] shrink-0" />
            <div className="min-w-0 flex-1">
              <h1 className="text-base font-bold text-[var(--text-primary)] truncate">Nanobot 控制台</h1>
              <p className="text-xs text-[var(--text-secondary)]">管理面板</p>
              {user?.role === 'mock_tester' && (
                <span className="inline-flex mt-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-400">
                  MOCK SANDBOX
                </span>
              )}
            </div>
            <button
              onClick={toggle}
              className="p-1 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-all opacity-0 group-hover/header:opacity-100 shrink-0"
              title="收起侧边栏"
            >
              <PanelLeftClose className="w-4 h-4" />
            </button>
          </>
        )}
      </div>

      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
        {navItems.map(item => {
          const link = (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                cn(
                  'flex items-center rounded-lg text-sm transition-all duration-150',
                  collapsed ? 'justify-center px-0 py-2.5' : 'gap-3 px-3 py-2.5',
                  isActive
                    ? 'bg-[var(--accent)] text-white font-medium'
                    : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]',
                )
              }
            >
              <item.icon className="w-4.5 h-4.5 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </NavLink>
          )
          return collapsed ? (
            <FixedTooltip key={item.to} label={item.label}>
              {link}
            </FixedTooltip>
          ) : (
            <div key={item.to}>{link}</div>
          )
        })}
      </nav>

      <div className={cn('border-t border-[var(--border)]', collapsed ? 'p-2' : 'p-4')}>
        {collapsed ? (
          <div className="space-y-1">
            <FixedTooltip label={user?.username ?? '用户'}>
              <div className="flex justify-center p-2 rounded-lg text-[var(--text-secondary)]">
                <User className="w-4 h-4" />
              </div>
            </FixedTooltip>
            {isAdmin() && (
              <FixedTooltip label="用户管理">
                <NavLink
                  to="/users"
                  className={({ isActive }) =>
                    cn(
                      'flex justify-center p-2 rounded-lg transition-colors',
                      isActive
                        ? 'bg-[var(--accent)] text-white'
                        : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]',
                    )
                  }
                >
                  <Users className="w-4 h-4" />
                </NavLink>
              </FixedTooltip>
            )}
            <FixedTooltip label={isDark ? '切换到白天模式' : '切换到黑夜模式'}>
              <button
                onClick={toggleTheme}
                className="flex justify-center p-2 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors w-full"
              >
                {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
              </button>
            </FixedTooltip>
            <FixedTooltip label="退出登录">
              <button
                onClick={logout}
                className="flex justify-center p-2 rounded-lg text-[var(--text-secondary)] hover:text-[var(--danger)] hover:bg-[var(--bg-tertiary)] transition-colors w-full"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </FixedTooltip>
          </div>
        ) : (
          <div className="flex items-center gap-2 px-1 py-1.5">
            <div className="w-8 h-8 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center shrink-0">
              <User className="w-4 h-4 text-[var(--text-secondary)]" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-[var(--text-primary)] truncate">{user?.username}</p>
              <p className="text-xs text-[var(--text-secondary)] capitalize">{user?.role}</p>
            </div>
            {isAdmin() && (
              <NavLink
                to="/users"
                title="用户管理"
                className={({ isActive }) =>
                  cn(
                    'p-1.5 rounded-lg transition-colors shrink-0',
                    isActive
                      ? 'text-[var(--accent)]'
                      : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]',
                  )
                }
              >
                <Users className="w-3.5 h-3.5" />
              </NavLink>
            )}
            <button
              onClick={toggleTheme}
              title={isDark ? '切换到白天模式' : '切换到黑夜模式'}
              className="p-1.5 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors shrink-0"
            >
              {isDark ? <Sun className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
            </button>
            <button
              onClick={logout}
              title="退出登录"
              className="p-1.5 rounded-lg text-[var(--text-secondary)] hover:text-[var(--danger)] hover:bg-[var(--bg-tertiary)] transition-colors shrink-0"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </aside>
  )
}
