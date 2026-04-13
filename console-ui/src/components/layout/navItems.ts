import {
  LayoutDashboard,
  Settings,
  Brain,
  Image,
  UserCog,
  Puzzle,
  MessageSquare,
  BarChart3,
  Timer,
  User,
  Cpu,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { UserRole } from '../../stores/auth'

export interface NavItem {
  to: string
  icon: LucideIcon
  label: string
  allowedRoles?: UserRole[]
}

export const navItems: NavItem[] = [
  { to: '/', icon: LayoutDashboard, label: '控制台' },
  { to: '/config', icon: Settings, label: '配置' },
  { to: '/tasks', icon: Timer, label: '定时任务' },
  { to: '/bg-tasks', icon: Cpu, label: '后台任务', allowedRoles: ['admin', 'editor', 'viewer', 'mock_tester'] },
  { to: '/memory', icon: Brain, label: '记忆' },
  { to: '/media', icon: Image, label: '生成图片' },
  { to: '/persona', icon: UserCog, label: '人设', allowedRoles: ['admin', 'editor', 'viewer', 'mock_tester'] },
  { to: '/skills', icon: Puzzle, label: '技能和工具', allowedRoles: ['admin', 'editor', 'viewer', 'mock_tester'] },
  { to: '/chat', icon: MessageSquare, label: '聊天', allowedRoles: ['admin', 'editor', 'viewer', 'mock_tester'] },
  { to: '/tokens', icon: BarChart3, label: 'Token 统计' },
]

export const userNavItem: NavItem = {
  to: '/users',
  icon: User,
  label: '用户',
  allowedRoles: ['admin'],
}

export function filterNavItems(role?: UserRole | null): NavItem[] {
  return navItems.filter(item => !item.allowedRoles || (role ? item.allowedRoles.includes(role) : false))
}
