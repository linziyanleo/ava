import { useCallback, useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  BarChart3,
  Bot,
  Brain,
  Cpu,
  FolderOpen,
  Image,
  KeyRound,
  Monitor,
  Puzzle,
  RefreshCw,
  Shield,
  User,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '../lib/utils'
import { useAuth, type UserRole } from '../stores/auth'

interface SettingsNode {
  to: string
  label: string
  description: string
  icon?: LucideIcon
  allowedRoles?: UserRole[]
  children?: SettingsNode[]
}

const READ_ONLY_ROLES: UserRole[] = ['admin', 'editor', 'viewer', 'read_only', 'mock_tester']

const settingsTree: SettingsNode[] = [
  {
    to: '/settings/agents-config',
    label: 'Agents Config',
    description: 'Agent 状态、版本、路径与自有配置',
    icon: Bot,
    allowedRoles: READ_ONLY_ROLES,
    children: [
      { to: '/settings/agents-config', label: 'Overview', description: '', allowedRoles: READ_ONLY_ROLES },
      {
        to: '/settings/agents-config/nanobot',
        label: 'Nanobot',
        description: '',
        icon: Bot,
        allowedRoles: READ_ONLY_ROLES,
        children: [
          { to: '/settings/agents-config/nanobot/config', label: 'Config', description: '', allowedRoles: READ_ONLY_ROLES },
          { to: '/settings/agents-config/nanobot/memory', label: 'Memory', description: '', icon: Brain, allowedRoles: READ_ONLY_ROLES },
          { to: '/settings/agents-config/nanobot/persona', label: 'Persona', description: '', icon: User, allowedRoles: READ_ONLY_ROLES },
        ],
      },
      {
        to: '/settings/agents-config/codex',
        label: 'Codex',
        description: '',
        icon: Cpu,
        allowedRoles: READ_ONLY_ROLES,
        children: [
          { to: '/settings/agents-config/codex/config', label: 'Config', description: '', allowedRoles: READ_ONLY_ROLES },
        ],
      },
      {
        to: '/settings/agents-config/claude-code',
        label: 'Claude Code',
        description: '',
        icon: Monitor,
        allowedRoles: READ_ONLY_ROLES,
        children: [
          { to: '/settings/agents-config/claude-code/config', label: 'Config', description: '', allowedRoles: READ_ONLY_ROLES },
        ],
      },
      {
        to: '/settings/agents-config/image-gen',
        label: 'Image Gen',
        description: '',
        icon: Image,
        allowedRoles: READ_ONLY_ROLES,
        children: [
          { to: '/settings/agents-config/image-gen/config', label: 'Config', description: '', allowedRoles: READ_ONLY_ROLES },
        ],
      },
    ],
  },
  {
    to: '/settings/statistics',
    label: 'Statistics',
    description: 'Token、会话与模型消耗统计',
    icon: BarChart3,
    allowedRoles: READ_ONLY_ROLES,
  },
  {
    to: '/settings/tools/skills',
    label: 'Tools',
    description: 'Skill、内置工具与 MCP 管理',
    icon: Puzzle,
    allowedRoles: READ_ONLY_ROLES,
    children: [
      { to: '/settings/tools/skills', label: 'Skills', description: '', icon: Puzzle, allowedRoles: READ_ONLY_ROLES },
    ],
  },
  {
    to: '/settings/users',
    label: 'Users',
    description: '账号、RBAC 与设备权限',
    icon: User,
    allowedRoles: ['admin'],
  },
  {
    to: '/settings/system/gateway',
    label: 'System',
    description: 'Gateway、Browser 与 Console 设置',
    icon: Shield,
    allowedRoles: READ_ONLY_ROLES,
    children: [
      { to: '/settings/system/desktop', label: 'Desktop', description: '', icon: Monitor, allowedRoles: ['admin'] },
      { to: '/settings/system/lan-access', label: 'LAN Access', description: '', icon: KeyRound, allowedRoles: ['admin'] },
      { to: '/settings/system/gateway', label: 'Gateway', description: '', icon: Cpu, allowedRoles: READ_ONLY_ROLES },
      { to: '/settings/system/browser', label: 'Browser', description: '', icon: Monitor, allowedRoles: ['admin', 'editor', 'viewer'] },
      { to: '/settings/system/console', label: 'Console', description: '', allowedRoles: READ_ONLY_ROLES },
      { to: '/settings/system/version', label: 'Version', description: '', icon: Shield, allowedRoles: READ_ONLY_ROLES },
    ],
  },
]

function canAccess(item: SettingsNode, role?: UserRole | null) {
  return !item.allowedRoles || (role ? item.allowedRoles.includes(role) : false)
}

function isNodeActive(item: SettingsNode, pathname: string): boolean {
  return pathname === item.to
    || pathname.startsWith(`${item.to}/`)
    || Boolean(item.children?.some((child) => isNodeActive(child, pathname)))
}

function SettingsTreeLinks({
  nodes,
  role,
}: {
  nodes: SettingsNode[]
  role?: UserRole | null
}) {
  return (
    <div className="space-y-1">
      {nodes.filter((node) => canAccess(node, role)).map((node) => {
        const Icon = node.icon
        return (
          <div key={node.to}>
            <NavLink
              to={node.to}
              end={!node.children}
              className={({ isActive }) => cn(
                'flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors',
                isActive
                  ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)]'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]',
              )}
            >
              {Icon && <Icon className="h-4 w-4" />}
              {node.label}
            </NavLink>
            {node.children && (
              <div className="ml-4 mt-1 border-l border-[var(--border)] pl-2">
                <SettingsTreeLinks nodes={node.children} role={role} />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

export function SettingsVersionPage() {
  return (
    <section className="max-w-3xl">
      <h1 className="text-2xl font-bold text-[var(--text-primary)]">Version</h1>
      <p className="mt-2 text-sm text-[var(--text-secondary)]">
        Core 与 Agent version 详情已在 Gateway 与 Agents Config 中展示；这里先保留为 Settings 的系统级入口。
      </p>
    </section>
  )
}

interface AvaDesktopApi {
  selectDirectory: () => Promise<string | null>
  openLogs: () => Promise<{ ok: boolean; error?: string }>
  readDesktopConfig: () => Promise<{ nanobotRoot?: string }>
  setNanobotRoot: (root: string) => Promise<{ ok: boolean; error?: string }>
  retryCore: () => Promise<{ ok: boolean; error?: string }>
}

function desktopApi(): AvaDesktopApi | null {
  return (window as unknown as { avaDesktop?: AvaDesktopApi }).avaDesktop || null
}

export function DesktopSettingsPage() {
  const [nanobotRoot, setNanobotRootState] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const api = desktopApi()

  const loadConfig = useCallback(async () => {
    if (!api) return
    setError('')
    try {
      const config = await api.readDesktopConfig()
      setNanobotRootState(config.nanobotRoot || '')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load desktop config')
    }
  }, [api])

  useEffect(() => {
    loadConfig()
  }, [loadConfig])

  const chooseNanobot = useCallback(async () => {
    if (!api) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const selected = await api.selectDirectory()
      if (!selected) return
      const result = await api.setNanobotRoot(selected)
      if (!result.ok) {
        setError(result.error || 'Invalid nanobot checkout')
        return
      }
      setNanobotRootState(selected)
      setMessage('Nanobot checkout saved.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save nanobot checkout')
    } finally {
      setBusy(false)
    }
  }, [api])

  const retryCore = useCallback(async () => {
    if (!api) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await api.retryCore()
      setMessage('Ava core retry requested.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retry Ava core')
    } finally {
      setBusy(false)
    }
  }, [api])

  if (!api) {
    return (
      <section className="max-w-3xl">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Desktop</h1>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          Desktop controls are available inside Ava.app.
        </p>
      </section>
    )
  }

  return (
    <section className="max-w-3xl space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Desktop</h1>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">Finder launch, local logs, and nanobot checkout selection.</p>
      </div>

      {message && <div className="rounded-lg bg-[var(--success)]/10 p-3 text-sm text-[var(--success)]">{message}</div>}
      {error && <div className="rounded-lg bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]">{error}</div>}

      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
        <p className="text-xs uppercase text-[var(--text-secondary)]">Nanobot checkout</p>
        <p className="mt-2 break-all font-mono text-sm text-[var(--text-primary)]">{nanobotRoot || '-'}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={chooseNanobot}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-primary)] hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:opacity-50"
          >
            <FolderOpen className="h-4 w-4" />
            Select
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={retryCore}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-primary)] hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:opacity-50"
          >
            <RefreshCw className="h-4 w-4" />
            Retry Core
          </button>
          <button
            type="button"
            onClick={() => api.openLogs()}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-primary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            Open Logs
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
        <p className="text-xs uppercase text-[var(--text-secondary)]">Agent configuration</p>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">Open the existing agent config editors from the desktop setup area.</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <NavLink
            to="/settings/agents-config/codex/config"
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-primary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            <Cpu className="h-4 w-4" />
            Codex Config
          </NavLink>
          <NavLink
            to="/settings/agents-config/claude-code/config"
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-primary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            <Monitor className="h-4 w-4" />
            Claude Code Config
          </NavLink>
        </div>
      </div>
    </section>
  )
}

export default function SettingsPage() {
  const { user } = useAuth()
  const location = useLocation()
  const visibleItems = settingsTree.filter((item) => canAccess(item, user?.role))
  const activeRoot = visibleItems.find((item) => isNodeActive(item, location.pathname))

  return (
    <div className="flex min-h-full flex-col bg-[var(--bg-primary)] md:h-full md:min-h-0 md:flex-row">
      <aside className="w-full shrink-0 border-b border-[var(--border)] bg-[var(--bg-secondary)] p-4 md:w-72 md:border-b-0 md:border-r">
        <div className="mb-4">
          <h1 className="text-lg font-semibold text-[var(--text-primary)]">Settings</h1>
        </div>

        <nav className="flex gap-1 overflow-x-auto pb-1 md:block md:space-y-1 md:overflow-visible md:pb-0">
          {visibleItems.map((item) => {
            const isActive = isNodeActive(item, location.pathname)
            const Icon = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={cn(
                  'flex min-w-52 items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors md:min-w-0',
                  isActive
                    ? 'bg-[var(--accent)] text-white'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]',
                  )}
              >
                {Icon && <Icon className="mt-0.5 h-4 w-4 shrink-0" />}
                <span className="min-w-0">
                  <span className="flex min-w-0 items-center gap-2 text-sm font-medium">
                    <span className="truncate">{item.label}</span>
                  </span>
                  <span className={cn('mt-0.5 block text-xs leading-snug', isActive ? 'text-white/75' : 'text-[var(--text-secondary)]')}>
                    {item.description}
                  </span>
                </span>
              </NavLink>
            )
          })}
        </nav>

        {activeRoot?.children && (
          <div className="mt-5 border-t border-[var(--border)] pt-4">
            <p className="mb-2 px-3 text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">{activeRoot.label}</p>
            <SettingsTreeLinks nodes={activeRoot.children} role={user?.role} />
          </div>
        )}
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto p-4 md:p-6">
        <Outlet />
      </main>
    </div>
  )
}
