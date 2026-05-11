#!/usr/bin/env node
import assert from 'node:assert/strict'
import { chromium, firefox, webkit } from 'playwright'

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:4173'
const browserType = { chromium, firefox, webkit }[process.env.PW_BROWSER || 'chromium'] || chromium
const now = new Date().toISOString()

function json(route, data, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
}

let capabilityRequests = 0
let renewRequests = 0
let tunnelRequests = 0

async function installMocks(page) {
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace(/^\/api/, '')
    if (path === '/auth/me') return json(route, { username: 'admin', role: 'admin', created_at: now })
    if (path === '/lan-access/status') {
      return json(route, {
        enabled: true,
        bind_host: '0.0.0.0',
        port: 6688,
        lan_urls: ['http://192.168.1.20:6688/'],
        pairing_active: true,
        pairing_expires_at: now,
        devices: [{
          device_id: 'phone',
          name: 'Phone',
          role: 'read_only',
          capabilities: ['read', 'review'],
          created_at: now,
          last_seen_at: now,
          last_ip: '192.168.1.50',
          user_agent: 'mobile',
          expires_at: now,
          revoked_at: null,
        }],
        mdns: { running: true, name: 'Ava Console', service_type: '_ava._tcp.local.', error: '' },
        tunnel: { running: true, public_url: 'https://remote.trycloudflare.com', binary_path: '/vendor/cloudflared', pid: 123, error: '' },
        https: { enabled: true, ca_certificate_path: '', certificate_path: '', key_path: '' },
      })
    }
    if (path === '/lan-access/devices/phone/capability') {
      capabilityRequests += 1
      assert.deepEqual(JSON.parse(request.postData() || '{}'), { capabilities: ['read', 'review', 'operate'] })
      return json(route, { ok: true })
    }
    if (path === '/lan-access/devices/phone/renew') {
      renewRequests += 1
      return json(route, { ok: true })
    }
    if (path === '/lan-access/tunnel/stop') {
      tunnelRequests += 1
      return json(route, { ok: true })
    }
    if (path === '/lan-access/pin') {
      return json(route, {
        pin: '123456',
        expires_at: now,
        pairing_url: 'http://192.168.1.20:6688/lan/pair?pin=123456',
        qr_payload: 'http://192.168.1.20:6688/lan/pair?pin=123456',
      })
    }
    if (path.startsWith('/lan-access/')) return json(route, { ok: true })
    if (path === '/audit/logs') return json(route, { entries: [] })
    return json(route, {})
  })
}

const browser = await browserType.launch()
const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
await installMocks(page)
await page.goto(`${baseURL}/settings/system/lan-access`)
await page.getByText('LAN Access', { exact: true }).waitFor()
await page.getByText('_ava._tcp.local.').waitFor()
await page.getByText('https://remote.trycloudflare.com').waitFor()
await page.getByRole('button', { name: 'Generate PIN' }).click()
await page.getByText('Pairing QR').waitFor()
await page.getByText('reviewer').waitFor()
assert.equal(await page.locator('canvas').count(), 1)
await page.getByRole('button', { name: 'operator' }).click()
await page.getByRole('button', { name: 'Renew' }).click()
await page.getByRole('button', { name: 'Stop' }).click()
assert.equal(capabilityRequests, 1)
assert.equal(renewRequests, 1)
assert.equal(tunnelRequests, 1)
await browser.close()
