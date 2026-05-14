import { MessageSquare, Settings } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export interface NavItem {
  to: string
  icon: LucideIcon
  label: string
}

export const navItems: NavItem[] = [
  { to: '/', icon: MessageSquare, label: 'Chat' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]
