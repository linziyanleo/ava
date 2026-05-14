export type StatusKind =
  | 'running'
  | 'available'
  | 'completed'
  | 'queued'
  | 'waiting'
  | 'retrying'
  | 'failed'
  | 'blocked'
  | 'disconnected'
  | 'idle'
  | 'paused'
  | 'cancelled'

export type StatusTone = 'running' | 'success' | 'queued' | 'warning' | 'danger' | 'idle'

export interface StatusToneClasses {
  badge: string
  surface: string
  text: string
  border: string
  dot: string
}

export const STATUS_KIND_TONE: Record<StatusKind, StatusTone> = {
  running: 'running',
  available: 'success',
  completed: 'success',
  queued: 'queued',
  waiting: 'warning',
  retrying: 'warning',
  failed: 'danger',
  blocked: 'danger',
  disconnected: 'danger',
  idle: 'idle',
  paused: 'idle',
  cancelled: 'idle',
}

export const STATUS_TONE_CLASSES: Record<StatusTone, StatusToneClasses> = {
  running: {
    badge: 'border-[var(--ava-running-border)] bg-[var(--ava-running-soft)] text-[var(--ava-running)]',
    surface: 'border-[var(--ava-running-border)] bg-[var(--ava-running-soft)]',
    text: 'text-[var(--ava-running)]',
    border: 'border-[var(--ava-running-border)]',
    dot: 'bg-[var(--ava-running)]',
  },
  success: {
    badge: 'border-[var(--ava-success-border)] bg-[var(--ava-success-soft)] text-[var(--ava-success)]',
    surface: 'border-[var(--ava-success-border)] bg-[var(--ava-success-soft)]',
    text: 'text-[var(--ava-success)]',
    border: 'border-[var(--ava-success-border)]',
    dot: 'bg-[var(--ava-success)]',
  },
  queued: {
    badge: 'border-[var(--ava-queued-border)] bg-[var(--ava-queued-soft)] text-[var(--ava-queued)]',
    surface: 'border-[var(--ava-queued-border)] bg-[var(--ava-queued-soft)]',
    text: 'text-[var(--ava-queued)]',
    border: 'border-[var(--ava-queued-border)]',
    dot: 'bg-[var(--ava-queued)]',
  },
  warning: {
    badge: 'border-[var(--ava-warning-border)] bg-[var(--ava-warning-soft)] text-[var(--ava-warning)]',
    surface: 'border-[var(--ava-warning-border)] bg-[var(--ava-warning-soft)]',
    text: 'text-[var(--ava-warning)]',
    border: 'border-[var(--ava-warning-border)]',
    dot: 'bg-[var(--ava-warning)]',
  },
  danger: {
    badge: 'border-[var(--ava-danger-border)] bg-[var(--ava-danger-soft)] text-[var(--ava-danger)]',
    surface: 'border-[var(--ava-danger-border)] bg-[var(--ava-danger-soft)]',
    text: 'text-[var(--ava-danger)]',
    border: 'border-[var(--ava-danger-border)]',
    dot: 'bg-[var(--ava-danger)]',
  },
  idle: {
    badge: 'border-[var(--ava-idle-border)] bg-[var(--ava-idle-soft)] text-[var(--ava-idle)]',
    surface: 'border-[var(--ava-idle-border)] bg-[var(--ava-idle-soft)]',
    text: 'text-[var(--ava-idle)]',
    border: 'border-[var(--ava-idle-border)]',
    dot: 'bg-[var(--ava-idle)]',
  },
}

export const STATUS_LABELS: Record<StatusKind, string> = {
  running: 'Running',
  available: 'Available',
  completed: 'Completed',
  queued: 'Queued',
  waiting: 'Waiting',
  retrying: 'Retrying',
  failed: 'Failed',
  blocked: 'Blocked',
  disconnected: 'Disconnected',
  idle: 'Idle',
  paused: 'Paused',
  cancelled: 'Cancelled',
}

export function statusTone(kind: StatusKind): StatusTone {
  return STATUS_KIND_TONE[kind]
}

export function statusToneClasses(kind: StatusKind): StatusToneClasses {
  return STATUS_TONE_CLASSES[statusTone(kind)]
}

export function normalizeStatusKind(status: string | null | undefined): StatusKind {
  const value = (status || '').trim().toLowerCase()
  if (value === 'streaming' || value === 'running' || value === 'active' || value === 'in_progress' || value === 'live') {
    return 'running'
  }
  if (value === 'available' || value === 'healthy' || value === 'ready') {
    return 'available'
  }
  if (value === 'completed' || value === 'complete' || value === 'success' || value === 'succeeded' || value === 'ok') {
    return 'completed'
  }
  if (value === 'queued' || value === 'pending') {
    return 'queued'
  }
  if (value === 'waiting' || value === 'awaiting_deps' || value === 'blocked_on_input' || value === 'slow') {
    return 'waiting'
  }
  if (value === 'retrying' || value === 'reconnecting' || value === 'connecting') {
    return 'retrying'
  }
  if (value === 'blocked') {
    return 'blocked'
  }
  if (value === 'disconnected' || value === 'offline' || value === 'closed' || value === 'unavailable') {
    return 'disconnected'
  }
  if (value === 'failed' || value === 'failure' || value === 'error' || value === 'timeout') {
    return 'failed'
  }
  if (value === 'paused') {
    return 'paused'
  }
  if (value === 'cancelled' || value === 'canceled') {
    return 'cancelled'
  }
  return 'idle'
}
