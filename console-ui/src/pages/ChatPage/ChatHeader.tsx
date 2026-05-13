import { useCallback, useState } from 'react'
import { Copy, Check, RefreshCw, Search, Menu, MoreHorizontal } from 'lucide-react'
import type { SessionMeta, ConversationMeta, ActiveChatTransport, ChatStreamStatus } from './types'
import { SCENE_LABELS } from './types'
import { ConnectionBadge } from './ConnectionBadge'
import { AgentsDropdown } from './AgentsDropdown'
import { ContextChip } from './ContextChip'
import { ContextLensDrawer } from './ContextLensDrawer'
import { HeaderOverflowSheet } from './HeaderOverflowSheet'
import { SearchModal } from './SearchModal'
import type { TurnGroup } from './types'
import { getSessionParticipants, getSessionTitle } from './utils'

interface ChatHeaderProps {
  session: SessionMeta | null
  conversation: ConversationMeta | null
  turns: TurnGroup[]
  isReadOnly: boolean
  isMobile?: boolean
  transportStatus: ChatStreamStatus
  activeTransport: ActiveChatTransport
  onRefresh: () => void
  onToggleSessionPanel?: () => void
  onParticipantsChange?: (participants: string[]) => Promise<void> | void
}

export function ChatHeader({
  session,
  conversation,
  turns,
  isReadOnly,
  isMobile,
  transportStatus,
  activeTransport,
  onRefresh,
  onToggleSessionPanel,
  onParticipantsChange,
}: ChatHeaderProps) {
  const [keyCopied, setKeyCopied] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const [showLens, setShowLens] = useState(false)
  const [showOverflow, setShowOverflow] = useState(false)

  const handleCopyKey = useCallback(() => {
    if (!session) return
    navigator.clipboard.writeText(session.key)
    setKeyCopied(true)
    setTimeout(() => setKeyCopied(false), 1500)
  }, [session])

  const handleRefresh = useCallback(() => {
    setRefreshing(true)
    onRefresh()
    setTimeout(() => setRefreshing(false), 1000)
  }, [onRefresh])

  if (!session) return null

  const headerTitle = getSessionTitle(session)
  const participants = getSessionParticipants(session)

  if (isMobile) {
    return (
      <>
        <div className="flex items-center gap-1.5 border-b border-[var(--border)] px-3 py-2">
          {onToggleSessionPanel && (
            <button
              type="button"
              onClick={onToggleSessionPanel}
              className="rounded-md p-1 text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
            >
              <Menu className="h-4 w-4" />
            </button>
          )}
          <span className="min-w-0 flex-1 truncate text-sm font-medium text-[var(--text-primary)]">
            {headerTitle}
          </span>
          <button
            type="button"
            onClick={handleCopyKey}
            className="p-0.5 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            {keyCopied ? <Check className="h-3 w-3 text-[var(--success)]" /> : <Copy className="h-3 w-3" />}
          </button>

          <AgentsDropdown
            participants={participants}
            defaultResponderId={session.default_responder_agent_id}
            isReadOnly={isReadOnly}
            disabled={!onParticipantsChange}
            onParticipantsChange={onParticipantsChange}
          />

          <ContextChip
            sessionKey={session.key}
            onOpenLens={() => setShowLens(true)}
            isMobile
          />

          <button
            type="button"
            onClick={() => setShowOverflow(true)}
            className="rounded-md p-1.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </div>

        <HeaderOverflowSheet
          open={showOverflow}
          onClose={() => setShowOverflow(false)}
          onRefresh={handleRefresh}
          onSearch={() => setShowSearch(true)}
          transportStatus={transportStatus}
          activeTransport={activeTransport}
          isReadOnly={isReadOnly}
        />

        {showSearch && <SearchModal turns={turns} onClose={() => setShowSearch(false)} />}
        <ContextLensDrawer
          open={showLens}
          sessionKey={session.key}
          sessionLabel={headerTitle}
          disabled={isReadOnly}
          isMobile
          onClose={() => setShowLens(false)}
        />
      </>
    )
  }

  return (
    <>
      <div className="flex h-10 items-center gap-2 border-b border-[var(--border)] px-3">
        {/* Left: title + meta */}
        <div className="flex min-w-0 shrink items-center gap-1.5">
          <h3 className="truncate text-[13px] font-semibold text-[var(--text-primary)]">
            {headerTitle}
          </h3>
          <button
            type="button"
            onClick={handleCopyKey}
            className="shrink-0 rounded p-0.5 text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors"
            title="Copy session key"
          >
            {keyCopied ? <Check className="h-3 w-3 text-[var(--success)]" /> : <Copy className="h-3 w-3" />}
          </button>
          <span className="hidden shrink-0 text-[10px] text-[var(--text-tertiary)] lg:inline">
            {SCENE_LABELS[session.scene]}
          </span>
          {conversation && (
            <span className="hidden shrink-0 text-[10px] text-[var(--text-tertiary)] xl:inline">
              {conversation.is_legacy ? 'Legacy' : conversation.is_active ? 'Active' : 'Archived'}
            </span>
          )}
        </div>

        {/* Separator */}
        <div className="h-4 w-px shrink-0 bg-[var(--border)]" />

        {/* Center: agents + context chip */}
        <AgentsDropdown
          participants={participants}
          defaultResponderId={session.default_responder_agent_id}
          isReadOnly={isReadOnly}
          disabled={!onParticipantsChange}
          onParticipantsChange={onParticipantsChange}
        />

        <ContextChip
          sessionKey={session.key}
          onOpenLens={() => setShowLens(true)}
        />

        {/* Spacer */}
        <div className="flex-1" />

        {/* Right: status + actions */}
        <ConnectionBadge transport={activeTransport} status={transportStatus} />

        {isReadOnly && (
          <span className="shrink-0 rounded bg-[var(--bg-tertiary)] px-1.5 py-0.5 text-[10px] text-[var(--text-tertiary)]">
            RO
          </span>
        )}

        <button
          type="button"
          onClick={handleRefresh}
          className="shrink-0 rounded-md p-1.5 text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
          title="Refresh"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
        </button>
        <button
          type="button"
          onClick={() => setShowSearch(true)}
          className="shrink-0 rounded-md p-1.5 text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
          title="Search"
        >
          <Search className="h-3.5 w-3.5" />
        </button>
      </div>

      {showSearch && <SearchModal turns={turns} onClose={() => setShowSearch(false)} />}
      <ContextLensDrawer
        open={showLens}
        sessionKey={session.key}
        sessionLabel={headerTitle}
        disabled={isReadOnly}
        onClose={() => setShowLens(false)}
      />
    </>
  )
}
