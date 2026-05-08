import { useCallback, useEffect, useState } from 'react'
import { Copy, KeyRound, Loader2, RefreshCw, ShieldOff, Smartphone } from 'lucide-react'
import { api } from '../api/client'
import { ToggleSwitch } from './ConfigPage/FormWidgets'

interface LanDevice {
  device_id: string
  name: string
  role: string
  capabilities: string[]
  created_at: string
  last_seen_at: string
  last_ip: string
  revoked_at: string | null
}

interface LanStatus {
  enabled: boolean
  bind_host: string
  port: number
  lan_urls: string[]
  pairing_active: boolean
  pairing_expires_at: string | null
  devices: LanDevice[]
}

interface PinResponse {
  pin: string
  expires_at: string
}

interface AuditEntry {
  ts: string
  user: string
  action: string
  target: string
  ip: string
}

interface AuditResponse {
  entries: AuditEntry[]
}

function formatDate(value: string | null) {
  if (!value) return 'never'
  return new Date(value).toLocaleString()
}

export default function LanAccessPage() {
  const [status, setStatus] = useState<LanStatus | null>(null)
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [pin, setPin] = useState<PinResponse | null>(null)
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [nextStatus, auditLog] = await Promise.all([
        api<LanStatus>('/lan-access/status'),
        api<AuditResponse>('/audit/logs?action=lan.device_access&size=5'),
      ])
      setStatus(nextStatus)
      setAudit(auditLog.entries || [])
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Failed to load LAN Access')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const setEnabled = async (enabled: boolean) => {
    setMessage('')
    setStatus(await api<LanStatus>('/lan-access/config', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }))
    if (!enabled) setPin(null)
  }

  const createPin = async () => {
    setMessage('')
    setPin(await api<PinResponse>('/lan-access/pin', { method: 'POST' }))
  }

  const revoke = async (deviceId: string) => {
    setMessage('')
    await api(`/lan-access/devices/${encodeURIComponent(deviceId)}/revoke`, { method: 'POST' })
    await load()
  }

  const copyUrl = async (url: string) => {
    await navigator.clipboard.writeText(url)
    setMessage('LAN URL copied')
  }

  const activeDevices = status?.devices.filter((device) => !device.revoked_at) || []

  return (
    <section className="max-w-5xl space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">LAN Access</h1>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">Local network access, PIN pairing, and read-only device tokens.</p>
        </div>
        <button
          type="button"
          onClick={load}
          className="inline-flex items-center gap-2 rounded-md border border-[var(--border)] px-3 py-2 text-sm text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Refresh
        </button>
      </div>

      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-[var(--text-primary)]">LAN Access</div>
            <div className="mt-1 text-xs text-[var(--text-secondary)]">Bind host: {status?.bind_host || '127.0.0.1'}:{status?.port || '-'}</div>
          </div>
          <ToggleSwitch value={!!status?.enabled} onChange={setEnabled} readOnly={!status} />
        </div>
      </div>

      {status?.enabled && (
        <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
          <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
              <Smartphone className="h-4 w-4" />
              LAN URLs
            </div>
            <div className="space-y-2">
              {status.lan_urls.length === 0 && <div className="text-sm text-[var(--text-secondary)]">No non-loopback IPv4 address detected.</div>}
              {status.lan_urls.map((url) => (
                <button
                  key={url}
                  type="button"
                  onClick={() => copyUrl(url)}
                  className="flex w-full items-center justify-between gap-2 rounded-md border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-2 text-left font-mono text-sm hover:border-[var(--accent)]"
                >
                  <span className="truncate">{url}</span>
                  <Copy className="h-4 w-4 shrink-0 text-[var(--text-secondary)]" />
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
                <KeyRound className="h-4 w-4" />
                PIN Pairing
              </div>
              <button
                type="button"
                onClick={createPin}
                className="rounded-md border border-[var(--border)] px-3 py-1.5 text-sm text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
              >
                Generate PIN
              </button>
            </div>
            {pin ? (
              <div>
                <div className="font-mono text-3xl font-semibold tracking-wider text-[var(--text-primary)]">{pin.pin}</div>
                <div className="mt-1 text-xs text-[var(--text-secondary)]">Expires {formatDate(pin.expires_at)}</div>
              </div>
            ) : (
              <div className="text-sm text-[var(--text-secondary)]">No active PIN displayed.</div>
            )}
          </div>
        </div>
      )}

      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
          <ShieldOff className="h-4 w-4" />
          Device Tokens
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase text-[var(--text-tertiary)]">
              <tr>
                <th className="py-2 pr-3">Device</th>
                <th className="py-2 pr-3">Role</th>
                <th className="py-2 pr-3">Last Seen</th>
                <th className="py-2 pr-3">IP</th>
                <th className="py-2 pr-3"></th>
              </tr>
            </thead>
            <tbody>
              {activeDevices.map((device) => (
                <tr key={device.device_id} className="border-t border-[var(--border)]">
                  <td className="py-2 pr-3">
                    <div className="font-medium text-[var(--text-primary)]">{device.name}</div>
                    <div className="font-mono text-xs text-[var(--text-tertiary)]">{device.device_id}</div>
                  </td>
                  <td className="py-2 pr-3 text-[var(--text-secondary)]">{device.role}</td>
                  <td className="py-2 pr-3 text-[var(--text-secondary)]">{formatDate(device.last_seen_at)}</td>
                  <td className="py-2 pr-3 font-mono text-[var(--text-secondary)]">{device.last_ip || '-'}</td>
                  <td className="py-2 pr-3 text-right">
                    <button
                      type="button"
                      onClick={() => revoke(device.device_id)}
                      className="rounded-md border border-[var(--border)] px-2 py-1 text-xs text-red-400 hover:border-red-400"
                    >
                      Revoke
                    </button>
                  </td>
                </tr>
              ))}
              {activeDevices.length === 0 && (
                <tr>
                  <td colSpan={5} className="border-t border-[var(--border)] py-4 text-center text-[var(--text-secondary)]">No paired devices.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
        <div className="mb-3 text-sm font-semibold text-[var(--text-primary)]">Audit</div>
        <div className="space-y-2">
          {audit.map((entry) => (
            <div key={`${entry.ts}:${entry.target}`} className="grid gap-1 rounded-md border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-2 text-xs md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_8rem]">
              <span className="truncate font-mono text-[var(--text-secondary)]">{entry.user}</span>
              <span className="truncate text-[var(--text-primary)]">{entry.target}</span>
              <span className="font-mono text-[var(--text-tertiary)]">{entry.ip || '-'}</span>
            </div>
          ))}
          {audit.length === 0 && <div className="text-sm text-[var(--text-secondary)]">No LAN device access yet.</div>}
        </div>
      </div>

      {message && <div className="text-sm text-[var(--text-secondary)]">{message}</div>}
    </section>
  )
}
