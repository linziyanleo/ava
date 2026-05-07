import { Square } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ChatComposePayload } from './types'

export interface ChatCommandRunContext {
  send: (payload: ChatComposePayload) => Promise<void> | void
  stopCurrentTurn: () => Promise<void> | void
  setInput: (text: string) => void
  closeMenu: () => void
}

export interface ChatCommand {
  id: string
  label: string
  description: string
  icon?: LucideIcon
  populateOnly?: boolean
  runWhenBusy?: boolean
  run?: (ctx: ChatCommandRunContext) => Promise<void> | void
}

export const CHAT_COMMANDS: ChatCommand[] = [
  {
    id: '/stop',
    label: 'Stop',
    description: 'Stop current output and active tasks',
    icon: Square,
    runWhenBusy: true,
    run: ({ stopCurrentTurn }) => stopCurrentTurn(),
  },
]

export function findCommandsByPrefix(prefix: string): ChatCommand[] {
  const normalized = prefix.trimStart().toLowerCase()
  if (!normalized.startsWith('/')) return []
  return CHAT_COMMANDS.filter((command) => command.id.toLowerCase().startsWith(normalized))
}
