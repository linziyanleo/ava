import { api } from './client'

export type DeviceCapability = 'read' | 'review' | 'operate'

export interface LanDevice {
  device_id: string
  name: string
  role: string
  capabilities: DeviceCapability[]
  created_at: string
  last_seen_at: string
  last_ip: string
  user_agent: string
  expires_at: string
  revoked_at: string | null
}

export interface LanStatus {
  enabled: boolean
  bind_host: string
  port: number
  lan_urls: string[]
  pairing_active: boolean
  pairing_expires_at: string | null
  devices: LanDevice[]
  https_enabled: boolean
  mdns?: { running: boolean; name: string; service_type: string; error: string }
  tunnel?: { running: boolean; public_url: string; binary_path: string; pid: number | null; error: string }
  https?: { enabled: boolean; ca_certificate_path: string; certificate_path: string; key_path: string }
}

export interface PinResponse {
  pin: string
  expires_at: string
  pairing_url: string
  qr_payload: string
}

export interface PairResponse {
  access_token: string
  token_type: string
  device: LanDevice
}

export function getLanStatus() {
  return api<LanStatus>('/lan-access/status')
}

export function getLanDiscovery() {
  return api('/lan-access/discovery')
}

export function setLanEnabled(enabled: boolean) {
  return api<LanStatus>('/lan-access/config', {
    method: 'PUT',
    body: JSON.stringify({ enabled }),
  })
}

export function createLanPin() {
  return api<PinResponse>('/lan-access/pin', { method: 'POST' })
}

export function pairLanDevice(pin: string, deviceName: string) {
  return api<PairResponse>('/lan-access/pair', {
    method: 'POST',
    body: JSON.stringify({ pin, device_name: deviceName }),
  })
}

export function revokeLanDevice(deviceId: string) {
  return api<LanDevice>(`/lan-access/devices/${encodeURIComponent(deviceId)}/revoke`, { method: 'POST' })
}

export function updateLanDeviceCapabilities(deviceId: string, capabilities: DeviceCapability[]) {
  return api<LanDevice>(`/lan-access/devices/${encodeURIComponent(deviceId)}/capability`, {
    method: 'POST',
    body: JSON.stringify({ capabilities }),
  })
}

export function renewLanDevice(deviceId: string) {
  return api<LanDevice>(`/lan-access/devices/${encodeURIComponent(deviceId)}/renew`, { method: 'POST' })
}

export function setLanTunnel(action: 'start' | 'stop') {
  return api(`/lan-access/tunnel/${action}`, { method: 'POST' })
}

export function setLanHttps(action: 'enable' | 'disable') {
  return api(`/lan-access/https/${action}`, { method: 'POST' })
}
