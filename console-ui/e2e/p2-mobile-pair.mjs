#!/usr/bin/env node
import { chromium, firefox, webkit } from 'playwright'

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:4173'
const browserType = { chromium, firefox, webkit }[process.env.PW_BROWSER || 'chromium'] || chromium
const now = new Date().toISOString()

function json(route, data, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
}

async function installMocks(page) {
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, '')
    if (path === '/auth/me') return json(route, null, 401)
    if (path === '/lan-access/pair') {
      const body = JSON.parse(route.request().postData() || '{}')
      if (body.pin === '000000') {
        return json(route, { detail: 'Too many pairing attempts' }, 429)
      }
      return json(route, {
        access_token: 'token',
        token_type: 'bearer',
        device: {
          device_id: 'phone',
          name: 'Phone',
          role: 'read_only',
          capabilities: ['read'],
          created_at: now,
          last_seen_at: now,
          last_ip: '192.168.1.50',
          user_agent: 'mobile',
          expires_at: now,
          revoked_at: null,
        },
      })
    }
    return json(route, {})
  })
}

const browser = await browserType.launch()

const successPage = await browser.newPage({ viewport: { width: 390, height: 844 } })
await installMocks(successPage)
await successPage.goto(`${baseURL}/lan/pair?pin=123456`)
await successPage.getByText('Pair Ava Console').waitFor()
await successPage.getByLabel('Device name').fill('Phone')
await successPage.getByRole('button', { name: 'Pair' }).click()
await successPage.waitForURL(`${baseURL}/`)
await successPage.close()

const failurePage = await browser.newPage({ viewport: { width: 390, height: 844 } })
await installMocks(failurePage)
await failurePage.goto(`${baseURL}/lan/pair?pin=000000`)
await failurePage.getByText('Pair Ava Console').waitFor()
await failurePage.getByLabel('Device name').fill('Phone')
await failurePage.getByRole('button', { name: 'Pair' }).click()
await failurePage.getByText('Too many pairing attempts').waitFor()
await failurePage.close()

await browser.close()
