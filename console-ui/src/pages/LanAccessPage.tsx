import { useCallback, useEffect, useState } from 'react'
import { QRCodeCanvas } from 'qrcode.react'
import { Copy, KeyRound, Loader2, RadioTower, RefreshCw, ShieldCheck, Smartphone, Wifi } from 'lucide-react'
import { api } from '../api/client'
import {
  createLanPin,
  renewLanDevice,
  revokeLanDevice,
  setLanEnabled,
  setLanHttps,
  setLanTunnel,
  updateLanDeviceCapabilities,
  type DeviceCapability,
  type LanDevice,
  type LanStatus,
  type PinResponse,
} from '../api/lan-access'
import { ToggleSwitch } from './ConfigPage/FormWidgets'

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

const CAPABILITIES: DeviceCapability[] = ['read', 'review', 'operate']

function formatDate(value: string | null) {
  if (!value) return 'never'
  return new Date(value).toLocaleString()
}

function CapabilityEditor({
  device,
  onChange,
}: {
  device: LanDevice
  onChange: (deviceId: string, capabilities: DeviceCapability[]) => void
}) {
  const selected = new Set(device.capabilities)
  const toggle = (capability: DeviceCapability) => {
    const next = new Set(selected)
    if (next.has(capability)) next.delete(capability)
    else next.add(capability)
    onChange(device.device_id, CAPABILITIES.filter((item) => next.has(item)))
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        <button type="button" onClick={() => onChange(device.device_id, ['read', 'review'])} className="rounded-md border border-[var(--border)] px-2 py-1 text-xs hover:border-[var(--accent)]">reviewer</button>
        <button type="button" onClick={() => onChange(device.device_id, ['read', 'review', 'operate'])} className="rounded-md border border-[var(--border)] px-2 py-1 text-xs hover:border-[var(--accent)]">operator</button>
      </div>
      <div className="flex flex-wrap gap-2">
        {CAPABILITIES.map((capability) => (
          <label key={capability} className="inline-flex items-center gap-1 text-xs text-[var(--text-secondary)]">
            <input
              type="checkbox"
              checked={selected.has(capability)}
              onChange={() => toggle(capability)}
            />
            {capability}
          </label>
        ))}
      </div>
    </div>
  )
}

export default function LanAccessPage() {
  const [status, setStatus] = useState<LanStatus | null>(null)
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [pin, setPin] = useState<PinResponse | null>(null)
  const [qrOpen, setQrOpen] = useState(false)
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
    setStatus(await setLanEnabled(enabled))
    if (!enabled) setPin(null)
  }

  const createPin = async () => {
    setMessage('')
    const nextPin = await createLanPin()
    setPin(nextPin)
    setQrOpen(true)
  }

  const revoke = async (deviceId: string) => {
    setMessage('')
    await revokeLanDevice(deviceId)
    await load()
  }

  const renew = async (deviceId: string) => {
    setMessage('')
    await renewLanDevice(deviceId)
    await load()
  }

  const setCapabilities = async (deviceId: string, capabilities: DeviceCapability[]) => {
    setMessage('')
    await updateLanDeviceCapabilities(deviceId, capabilities)
    await load()
  }

  const copyText = async (value: string, label: string) => {
    await navigator.clipboard.writeText(value)
    setMessage(`${label} copied`)
  }

  const toggleTunnel = async () => {
    setMessage('')
    await setLanTunnel(status?.tunnel?.running ? 'stop' : 'start')
    await load()
  }

  const toggleHttps = async () => {
    setMessage('')
    if (!status?.https?.enabled && !window.confirm('Enable HTTPS for LAN Access?')) return
    await setLanHttps(status?.https?.enabled ? 'disable' : 'enable')
    await load()
  }

  const activeDevices = status?.devices.filter((device) => !device.revoked_at) || []

  return (
    <section className="max-w-6xl space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">LAN Access</h1>
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

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
                <Wifi className="h-4 w-4" />
                LAN
              </div>
              <div className="mt-1 text-xs text-[var(--text-secondary)]">{status?.bind_host || '127.0.0.1'}:{status?.port || '-'}</div>
            </div>
            <ToggleSwitch value={!!status?.enabled} onChange={setEnabled} readOnly={!status} />
          </div>
        </div>

        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
                <RadioTower className="h-4 w-4" />
                mDNS
              </div>
              <div className="mt-1 text-xs text-[var(--text-secondary)]">{status?.mdns?.running ? status.mdns.service_type : status?.mdns?.error || 'stopped'}</div>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
                <ShieldCheck className="h-4 w-4" />
                HTTPS
              </div>
              <div className="mt-1 text-xs text-[var(--text-secondary)]">{status?.https?.enabled ? 'enabled' : 'disabled'}</div>
            </div>
            <ToggleSwitch value={!!status?.https?.enabled} onChange={toggleHttps} readOnly={!status?.enabled} />
          </div>
          {status?.https?.enabled && (
            <div className="mt-3 flex flex-wrap gap-3 text-xs">
              <a className="text-[var(--accent)]" href="/api/lan-access/cert/ca.crt">Download CA</a>
              <a className="text-[var(--text-secondary)] hover:text-[var(--accent)]" href="https://support.apple.com/guide/iphone/install-or-remove-configuration-profiles-iph6c493b19/ios" target="_blank" rel="noreferrer">iOS</a>
              <a className="text-[var(--text-secondary)] hover:text-[var(--accent)]" href="https://support.apple.com/guide/keychain-access/change-the-trust-settings-of-a-certificate-kyca11871/mac" target="_blank" rel="noreferrer">macOS</a>
              <a className="text-[var(--text-secondary)] hover:text-[var(--accent)]" href="https://support.google.com/android/answer/132441?hl=en" target="_blank" rel="noreferrer">Android</a>
            </div>
          )}
        </div>
      </div>

      {status?.enabled && (
        <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
          <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
              <Smartphone className="h-4 w-4" />
              URLs
            </div>
            <div className="space-y-2">
              {status.lan_urls.length === 0 && <div className="text-sm text-[var(--text-secondary)]">No LAN URL detected.</div>}
              {status.lan_urls.map((url) => (
                <button
                  key={url}
                  type="button"
                  onClick={() => copyText(url, 'LAN URL')}
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
                Pairing
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
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="font-mono text-3xl font-semibold text-[var(--text-primary)]">{pin.pin}</div>
                  <div className="mt-1 text-xs text-[var(--text-secondary)]">Expires {formatDate(pin.expires_at)}</div>
                </div>
                <button type="button" onClick={() => setQrOpen(true)} className="rounded-md border border-[var(--border)] px-3 py-2 text-sm hover:border-[var(--accent)]">QR</button>
              </div>
            ) : (
              <div className="text-sm text-[var(--text-secondary)]">No active PIN displayed.</div>
            )}
          </div>
        </div>
      )}

      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="text-sm font-semibold text-[var(--text-primary)]">Tunnel</div>
          <button
            type="button"
            onClick={toggleTunnel}
            disabled={!status?.enabled}
            className="rounded-md border border-[var(--border)] px-3 py-1.5 text-sm text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {status?.tunnel?.running ? 'Stop' : 'Start'}
          </button>
        </div>
        {status?.tunnel?.public_url ? (
          <button type="button" onClick={() => copyText(status.tunnel?.public_url || '', 'Tunnel URL')} className="flex w-full items-center justify-between gap-2 rounded-md border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-2 text-left font-mono text-sm hover:border-[var(--accent)]">
            <span className="truncate">{status.tunnel.public_url}</span>
            <Copy className="h-4 w-4 shrink-0 text-[var(--text-secondary)]" />
          </button>
        ) : (
          <div className="text-sm text-[var(--text-secondary)]">{status?.tunnel?.error || 'No tunnel URL.'}</div>
        )}
      </div>

      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
        <div className="mb-3 text-sm font-semibold text-[var(--text-primary)]">Device Tokens</div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase text-[var(--text-tertiary)]">
              <tr>
                <th className="py-2 pr-3">Device</th>
                <th className="py-2 pr-3">Capabilities</th>
                <th className="py-2 pr-3">Expires</th>
                <th className="py-2 pr-3">Last Seen</th>
                <th className="py-2 pr-3">IP</th>
                <th className="py-2 pr-3"></th>
              </tr>
            </thead>
            <tbody>
              {activeDevices.map((device) => (
                <tr key={device.device_id} className="border-t border-[var(--border)] align-top">
                  <td className="py-3 pr-3">
                    <div className="font-medium text-[var(--text-primary)]">{device.name}</div>
                    <div className="font-mono text-xs text-[var(--text-tertiary)]">{device.device_id}</div>
                  </td>
                  <td className="py-3 pr-3 text-[var(--text-secondary)]">
                    <CapabilityEditor device={device} onChange={setCapabilities} />
                  </td>
                  <td className="py-3 pr-3 text-[var(--text-secondary)]">{formatDate(device.expires_at)}</td>
                  <td className="py-3 pr-3 text-[var(--text-secondary)]">{formatDate(device.last_seen_at)}</td>
                  <td className="py-3 pr-3 font-mono text-[var(--text-secondary)]">{device.last_ip || '-'}</td>
                  <td className="py-3 pr-3 text-right">
                    <div className="flex justify-end gap-2">
                      <button type="button" onClick={() => renew(device.device_id)} className="rounded-md border border-[var(--border)] px-2 py-1 text-xs hover:border-[var(--accent)]">Renew</button>
                      <button type="button" onClick={() => revoke(device.device_id)} className="rounded-md border border-[var(--border)] px-2 py-1 text-xs text-red-400 hover:border-red-400">Revoke</button>
                    </div>
                  </td>
                </tr>
              ))}
              {activeDevices.length === 0 && (
                <tr>
                  <td colSpan={6} className="border-t border-[var(--border)] py-4 text-center text-[var(--text-secondary)]">No paired devices.</td>
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

      {qrOpen && pin && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-sm rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] p-5 shadow-xl">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div className="text-sm font-semibold text-[var(--text-primary)]">Pairing QR</div>
              <button type="button" onClick={() => setQrOpen(false)} className="rounded-md border border-[var(--border)] px-2 py-1 text-xs hover:border-[var(--accent)]">Close</button>
            </div>
            <div className="flex justify-center rounded-md bg-white p-4">
              <QRCodeCanvas value={pin.qr_payload || pin.pairing_url} size={220} />
            </div>
            <button type="button" onClick={() => copyText(pin.pairing_url, 'Pairing URL')} className="mt-4 flex w-full items-center justify-between gap-2 rounded-md border border-[var(--border)] px-3 py-2 text-left font-mono text-xs hover:border-[var(--accent)]">
              <span className="truncate">{pin.pairing_url}</span>
              <Copy className="h-4 w-4 shrink-0 text-[var(--text-secondary)]" />
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
