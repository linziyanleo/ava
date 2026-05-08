import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  BarChart3,
  Bot,
  Brain,
  Cpu,
  Image,
  KeyRound,
  Monitor,
  Puzzle,
  Settings,
  Shield,
  User,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '../lib/utils'
import { useAuth, type UserRole } from '../stores/auth'

interface SettingsItem {
  to: string
  label: string
  description: string
  icon: LucideIcon
  allowedRoles?: UserRole[]
}

const READ_ONLY_ROLES: UserRole[] = ['admin', 'editor', 'viewer', 'read_only', 'mock_tester']

const settingsItems: SettingsItem[] = [
  {
    to: '/settings/agents-config',
    label: 'Agents Config',
    description: 'Agent 状态、版本、路径与自有配置',
    icon: Bot,
    allowedRoles: READ_ONLY_ROLES,
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
    icon: Settings,
    allowedRoles: READ_ONLY_ROLES,
  },
]

const systemLinks: SettingsItem[] = [
  { to: '/settings/system/lan-access', label: 'LAN Access', description: '', icon: KeyRound, allowedRoles: ['admin'] },
  { to: '/settings/system/gateway', label: 'Gateway', description: '', icon: Cpu, allowedRoles: READ_ONLY_ROLES },
  { to: '/settings/system/browser', label: 'Browser', description: '', icon: Monitor, allowedRoles: ['admin', 'editor', 'viewer'] },
  { to: '/settings/system/console', label: 'Console', description: '', icon: Settings, allowedRoles: READ_ONLY_ROLES },
  { to: '/settings/system/version', label: 'Version', description: '', icon: Shield, allowedRoles: READ_ONLY_ROLES },
]

const toolsLinks: SettingsItem[] = [
  { to: '/settings/tools/skills', label: 'Skills', description: '', icon: Puzzle, allowedRoles: READ_ONLY_ROLES },
]

const agentLinks: SettingsItem[] = [
  { to: '/settings/agents-config', label: 'Overview', description: '', icon: Bot, allowedRoles: READ_ONLY_ROLES },
  { to: '/settings/agents-config/nanobot', label: 'Nanobot', description: '', icon: Bot, allowedRoles: READ_ONLY_ROLES },
  { to: '/settings/agents-config/codex', label: 'Codex', description: '', icon: Cpu, allowedRoles: READ_ONLY_ROLES },
  { to: '/settings/agents-config/claude-code', label: 'Claude Code', description: '', icon: Monitor, allowedRoles: READ_ONLY_ROLES },
  { to: '/settings/agents-config/image-gen', label: 'Image Gen', description: '', icon: Image, allowedRoles: READ_ONLY_ROLES },
  { to: '/settings/agents-config/nanobot/config', label: 'Nanobot Config', description: '', icon: Settings, allowedRoles: READ_ONLY_ROLES },
  { to: '/settings/agents-config/codex/config', label: 'Codex Config', description: '', icon: Settings, allowedRoles: READ_ONLY_ROLES },
  { to: '/settings/agents-config/claude-code/config', label: 'Claude Config', description: '', icon: Settings, allowedRoles: READ_ONLY_ROLES },
  { to: '/settings/agents-config/nanobot/memory', label: 'Memory', description: '', icon: Brain, allowedRoles: READ_ONLY_ROLES },
  { to: '/settings/agents-config/nanobot/persona', label: 'Persona', description: '', icon: User, allowedRoles: READ_ONLY_ROLES },
  { to: '/settings/agents-config/image-gen/config', label: 'Image Gen Config', description: '', icon: Settings, allowedRoles: READ_ONLY_ROLES },
]

function canAccess(item: SettingsItem, role?: UserRole | null) {
  return !item.allowedRoles || (role ? item.allowedRoles.includes(role) : false)
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

export default function SettingsPage() {
  const { user } = useAuth()
  const location = useLocation()
  const visibleItems = settingsItems.filter((item) => canAccess(item, user?.role))
  const inAgentsConfig = location.pathname.startsWith('/settings/agents-config')
  const inSystem = location.pathname.startsWith('/settings/system')
  const inTools = location.pathname.startsWith('/settings/tools')

  return (
    <div className="-m-4 -mb-20 flex min-h-[calc(100dvh-4rem)] flex-col bg-[var(--bg-primary)] md:-m-6 md:h-[calc(100%+3rem)] md:min-h-0 md:flex-row">
      <aside className="w-full shrink-0 border-b border-[var(--border)] bg-[var(--bg-secondary)] p-4 md:w-72 md:border-b-0 md:border-r">
        <div className="mb-4">
          <h1 className="text-lg font-semibold text-[var(--text-primary)]">Settings</h1>
        </div>

        <nav className="flex gap-1 overflow-x-auto pb-1 md:block md:space-y-1 md:overflow-visible md:pb-0">
          {visibleItems.map((item) => {
            const isActive = location.pathname === item.to || location.pathname.startsWith(`${item.to}/`)
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
                <item.icon className="mt-0.5 h-4 w-4 shrink-0" />
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

        {inAgentsConfig && (
          <div className="mt-5 border-t border-[var(--border)] pt-4">
            <p className="mb-2 px-3 text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">Agents</p>
            <div className="space-y-1">
              {agentLinks.filter((link) => canAccess(link, user?.role)).map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  end={link.to === '/settings/agents-config'}
                  className={({ isActive }) => cn(
                    'flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors',
                    isActive
                      ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)]'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]',
                  )}
                >
                  <link.icon className="h-4 w-4" />
                  {link.label}
                </NavLink>
              ))}
            </div>
          </div>
        )}

        {inTools && (
          <div className="mt-5 border-t border-[var(--border)] pt-4">
            <p className="mb-2 px-3 text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">Tools</p>
            <div className="space-y-1">
              {toolsLinks.filter((link) => canAccess(link, user?.role)).map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  className={({ isActive }) => cn(
                    'flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors',
                    isActive
                      ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)]'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]',
                  )}
                >
                  <link.icon className="h-4 w-4" />
                  {link.label}
                </NavLink>
              ))}
            </div>
          </div>
        )}

        {inSystem && (
          <div className="mt-5 border-t border-[var(--border)] pt-4">
            <p className="mb-2 px-3 text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">System</p>
            <div className="space-y-1">
              {systemLinks.filter((link) => canAccess(link, user?.role)).map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  className={({ isActive }) => cn(
                    'flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors',
                    isActive
                      ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)]'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]',
                  )}
                >
                  <link.icon className="h-4 w-4" />
                  {link.label}
                </NavLink>
              ))}
            </div>
          </div>
        )}
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto p-4 md:p-6">
        <Outlet />
      </main>
    </div>
  )
}
