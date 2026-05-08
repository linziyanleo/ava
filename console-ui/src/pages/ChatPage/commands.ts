import { Image as ImageIcon, Square, Terminal, Zap } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ChatComposePayload, DirectTaskSubmitParams } from './types'

export interface ChatCommandRunContext {
  send: (payload: ChatComposePayload) => Promise<void> | void
  stopCurrentTurn: () => Promise<void> | void
  submitDirectTask: (params: DirectTaskSubmitParams) => Promise<void> | void
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
  {
    id: '/codex',
    label: 'Codex',
    description: 'Run Codex task directly',
    icon: Zap,
    populateOnly: true,
  },
  {
    id: '/claude-code',
    label: 'Claude Code',
    description: 'Run Claude Code task directly',
    icon: Terminal,
    populateOnly: true,
  },
  {
    id: '/image-gen',
    label: 'Image Gen',
    description: 'Generate or edit an image from the prompt',
    icon: ImageIcon,
    populateOnly: true,
  },
]

export function findCommandsByPrefix(prefix: string): ChatCommand[] {
  const normalized = prefix.trimStart().toLowerCase()
  if (!normalized.startsWith('/')) return []
  return CHAT_COMMANDS.filter((command) => command.id.toLowerCase().startsWith(normalized))
}
