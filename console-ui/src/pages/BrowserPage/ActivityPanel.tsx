import type { ActivityEntry } from './types'

interface ActivityPanelProps {
  entries: ActivityEntry[]
  status: string
  pageUrl: string
  stepCount: number
}

const typeConfig: Record<string, { icon: string; color: string; label: string }> = {
  thinking: { icon: '●', color: 'text-yellow-400', label: 'Thinking' },
  executing: { icon: '◉', color: 'text-blue-400', label: 'Executing' },
  executed: { icon: '✓', color: 'text-green-400', label: 'Executed' },
  retrying: { icon: '↻', color: 'text-orange-400', label: 'Retrying' },
  error: { icon: '✗', color: 'text-red-400', label: 'Error' },
}

const statusColors: Record<string, string> = {
  idle: 'bg-gray-400',
  running: 'bg-green-400 animate-pulse',
  completed: 'bg-blue-400',
  error: 'bg-red-400',
}

export default function ActivityPanel({ entries, status, pageUrl, stepCount }: ActivityPanelProps) {
  return (
    <div className="w-80 flex flex-col border-l border-[var(--border)] bg-[var(--bg-secondary)]">
      {/* Header */}
      <div className="p-3 border-b border-[var(--border)]">
        <h3 className="text-sm font-medium text-[var(--text-primary)]">Agent Activity</h3>
      </div>

      {/* Event list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2 scrollbar-none">
        {entries.length === 0 ? (
          <p className="text-xs text-[var(--text-secondary)] text-center mt-8">
            暂无活动
          </p>
        ) : (
          entries.map((entry) => {
            const cfg = typeConfig[entry.type] || typeConfig.executing
            return (
              <div key={entry.id} className="text-xs space-y-0.5">
                <div className="flex items-center gap-1.5">
                  <span className={cfg.color}>{cfg.icon}</span>
                  <span className="text-[var(--text-primary)] font-medium">{cfg.label}</span>
                  {entry.tool && (
                    <span className="text-[var(--text-secondary)] font-mono">{entry.tool}</span>
                  )}
                </div>
                {entry.detail && (
                  <p className="text-[var(--text-secondary)] pl-4 break-words">{entry.detail}</p>
                )}
              </div>
            )
          })
        )}
      </div>

      {/* Status bar */}
      <div className="p-3 border-t border-[var(--border)] space-y-1.5">
        <div className="flex items-center gap-2 text-xs">
          <span className={`w-2 h-2 rounded-full ${statusColors[status] || statusColors.idle}`} />
          <span className="text-[var(--text-secondary)] capitalize">{status}</span>
          {stepCount > 0 && (
            <span className="text-[var(--text-secondary)] ml-auto">{stepCount} steps</span>
          )}
        </div>
        {pageUrl && (
          <p className="text-xs text-[var(--text-secondary)] truncate" title={pageUrl}>
            {pageUrl}
          </p>
        )}
      </div>
    </div>
  )
}
