import {
  MessageSquare,
  Settings,
  User,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { UserRole } from '../../stores/auth'

export interface NavItem {
  to: string
  icon: LucideIcon
  label: string
  allowedRoles?: UserRole[]
}

const READ_ONLY_ROLES: UserRole[] = ['admin', 'editor', 'viewer', 'read_only', 'mock_tester']

export const navItems: NavItem[] = [
  { to: '/', icon: MessageSquare, label: 'Chat', allowedRoles: READ_ONLY_ROLES },
  { to: '/settings', icon: Settings, label: 'Settings', allowedRoles: READ_ONLY_ROLES },
]

export const userNavItem: NavItem = {
  to: '/settings/users',
  icon: User,
  label: '用户',
  allowedRoles: ['admin'],
}

export function filterNavItems(role?: UserRole | null): NavItem[] {
  return navItems.filter(item => !item.allowedRoles || (role ? item.allowedRoles.includes(role) : false))
}
