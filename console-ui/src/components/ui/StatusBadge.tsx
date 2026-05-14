import { cn } from '../../lib/utils'
import { statusToneClasses, type StatusKind } from '../../lib/statusSemantics'

export type { StatusKind } from '../../lib/statusSemantics'

export interface StatusBadgeProps {
  kind: StatusKind
  label: string
  detail?: string
  size?: 'sm' | 'md'
  withDot?: boolean
  className?: string
}

export function StatusBadge({
  kind,
  label,
  detail,
  size = 'sm',
  withDot = true,
  className,
}: StatusBadgeProps) {
  const tone = statusToneClasses(kind)
  const isRunning = kind === 'running' || kind === 'retrying'

  return (
    <span
      className={cn(
        'inline-flex max-w-full items-center rounded-full border font-medium',
        tone.badge,
        size === 'md' ? 'gap-2 px-2.5 py-1 text-xs' : 'gap-1.5 px-2 py-0.5 text-[11px]',
        className,
      )}
    >
      {withDot && (
        <span className="relative inline-flex h-1.5 w-1.5 shrink-0" aria-hidden>
          {isRunning && <span className={cn('absolute h-full w-full rounded-full opacity-60 motion-safe:animate-ping', tone.dot)} />}
          <span className={cn('relative h-1.5 w-1.5 rounded-full', tone.dot)} />
        </span>
      )}
      <span className="truncate">{label}</span>
      {detail && (
        <>
          <span className="shrink-0 opacity-55">·</span>
          <span className="truncate opacity-80">{detail}</span>
        </>
      )}
    </span>
  )
}
