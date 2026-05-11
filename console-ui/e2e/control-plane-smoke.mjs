#!/usr/bin/env node
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium, firefox, webkit } from 'playwright'

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:4173'
const browserName = process.env.BROWSER || 'chromium'
const pageDiagnostics = new WeakMap()

const now = new Date().toISOString()
const session = {
  key: 'console:smoke',
  scene: 'console',
  created_at: now,
  updated_at: now,
  conversation_id: 'conv-smoke',
  participants: ['nanobot', 'codex'],
  default_responder_agent_id: 'nanobot',
  token_stats: {
    total_prompt_tokens: 120,
    total_completion_tokens: 80,
    total_tokens: 200,
    llm_calls: 2,
  },
  message_count: 2,
}

const taskSnapshot = {
  task_id: 'task-smoke',
  task_type: 'codex',
  status: 'succeeded',
  started_at: Math.floor(Date.now() / 1000) - 3,
  elapsed_ms: 3000,
  result_preview: 'Smoke task result',
  error_message: '',
  trace_id: 'trace-smoke',
  origin_session_key: session.key,
  origin_conversation_id: session.conversation_id,
  origin_turn_seq: 0,
  prompt_preview: 'Run smoke task',
  chain_id: '',
  parent_task_ids: [],
  node_kind: 'task',
}

function json(route, data, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(data),
  })
}

function lanStatus() {
  return {
    enabled: true,
    bind_host: '0.0.0.0',
    port: 8765,
    lan_urls: ['http://192.168.1.20:8765'],
    pairing_active: true,
    pairing_expires_at: now,
    devices: [
      {
        device_id: 'phone-1',
        name: 'Smoke phone',
        role: 'read_only',
        capabilities: ['read'],
        created_at: now,
        last_seen_at: now,
        last_ip: '192.168.1.50',
        user_agent: 'mobile',
        expires_at: now,
        revoked_at: null,
      },
    ],
    mdns: { running: true, name: 'Ava Console', service_type: '_ava._tcp.local.', error: '' },
    tunnel: { running: false, public_url: '', binary_path: '', pid: null, error: '' },
    https: { enabled: false, ca_certificate_path: '', certificate_path: '', key_path: '' },
  }
}

async function installApiMocks(page) {
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace(/^\/api/, '')

    if (path === '/auth/me') {
      return json(route, { username: 'smoke-admin', role: 'admin', created_at: now })
    }
    if (path === '/chat/sessions') return json(route, [session])
    if (path === '/chat/conversations') {
      return json(route, [
        {
          conversation_id: 'conv-smoke',
          first_message_preview: 'Smoke conversation',
          message_count: 2,
          created_at: now,
          updated_at: now,
          is_active: true,
        },
      ])
    }
    if (path === '/chat/messages') {
      return json(route, [
        { role: 'user', content: 'Hello from smoke', timestamp: now, trace_id: 'trace-smoke' },
        { role: 'assistant', content: 'Smoke response', timestamp: now, from_agent_id: 'nanobot' },
      ])
    }
    if (path.startsWith('/chat/sessions/') && path.endsWith('/context-size')) {
      return json(route, { used_tokens: 200, model_limit: 200000, breakdown: { messages: 200 } })
    }
    if (path.startsWith('/chat/sessions/') && request.method() === 'PATCH') return json(route, session)
    if (path === '/skills/tools') return json(route, { tools: [] })
    if (path === '/skills/mcp/status') {
      return json(route, {
        servers: [],
        runtime: {
          loaded: true,
          mcp_connected: false,
          mcp_connecting: false,
          connected_servers: [],
        },
      })
    }
    if (path === '/skills/list') {
      return json(route, {
        skills: [{
          name: 'playwright',
          source: 'builtin',
          path: '/skills/playwright',
          enabled: true,
          description: 'Browser smoke skill',
          always: false,
        }],
      })
    }
    if (path === '/gateway/status') return json(route, { memory_rss_bytes: 123456789 })
    if (path === '/bg-tasks/task-smoke') return json(route, taskSnapshot)
    if (path.startsWith('/bg-tasks')) return json(route, { tasks: [] })
    if (path.startsWith('/stats/tokens')) return json(route, [])
    if (path === '/workflows') {
      if (request.method() === 'POST') return json(route, { chain_id: 'chain-smoke', trace_id: 'trace-smoke' })
      return json(route, { chains: [] })
    }
    if (path.startsWith('/workflows/')) return json(route, { ok: true })
    if (path === '/artifacts') return json(route, { artifacts: [] })
    if (path === '/lan-access/status' || path === '/lan-access/config') return json(route, lanStatus())
    if (path === '/lan-access/pin') {
      return json(route, {
        pin: '123456',
        expires_at: now,
        pairing_url: 'http://192.168.1.20:8765/lan/pair?pin=123456',
        qr_payload: 'http://192.168.1.20:8765/lan/pair?pin=123456',
      })
    }
    if (path.startsWith('/lan-access/devices/')) return json(route, { ok: true })
    if (path === '/audit/logs') {
      return json(route, {
        entries: [
          {
            ts: now,
            user: 'smoke-admin',
            action: 'lan.device_access',
            target: '/api/chat/sessions',
            ip: '192.168.1.50',
          },
        ],
      })
    }
    return json(route, {})
  })
}

async function expectVisible(page, text) {
  try {
    await page.getByText(text, { exact: false }).first().waitFor({ state: 'visible', timeout: 7000 })
  } catch (error) {
    await mkdir('../output/playwright', { recursive: true })
    await page.screenshot({ path: `../output/playwright/control-plane-smoke-${text.replaceAll(/\W+/g, '-')}.png`, fullPage: true })
    const bodyText = await page.locator('body').innerText().catch(() => '')
    const bodyHtml = await page.locator('body').evaluate((node) => node.innerHTML.slice(0, 2000)).catch(() => '')
    const elementCount = await page.locator('body *').count().catch(() => 0)
    for (const diagnostic of pageDiagnostics.get(page) || []) {
      console.error(diagnostic)
    }
    console.error(`control-plane-smoke: url ${page.url()}, body elements ${elementCount}`)
    console.error(`control-plane-smoke: missing visible text "${text}"`)
    console.error(bodyText.split('\n').slice(0, 80).join('\n'))
    console.error(bodyHtml)
    throw error
  }
}

function attachPageDiagnostics(page) {
  const diagnostics = []
  pageDiagnostics.set(page, diagnostics)
  page.on('console', (message) => {
    if (message.type() === 'error') diagnostics.push(`browser-console-error: ${message.text()}`)
  })
  page.on('pageerror', (error) => {
    diagnostics.push(`browser-page-error: ${error.stack || error.message}`)
  })
}

async function runDesktopSmoke(browser) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
  attachPageDiagnostics(page)
  await installApiMocks(page)
  await page.addInitScript(() => {
    window.localStorage.setItem('chat-sidebar-collapsed', 'false')
  })

  await page.goto(baseURL)
  await expectVisible(page, 'Console Chat smoke')
  assert.equal(await page.getByText('console:smoke', { exact: false }).count(), 0)
  await expectVisible(page, 'Nanobot / Codex')
  await expectVisible(page, 'Token')
  await expectVisible(page, 'Skills')
  await expectVisible(page, 'Artifacts')
  await expectVisible(page, 'Memory')
  assert.equal(await page.getByText('presence', { exact: false }).count(), 0)
  assert.equal(await page.getByText('conflict aware', { exact: false }).count(), 0)

  await page.goto(`${baseURL}/?task_id=task-smoke`)
  const taskCard = page.locator('[data-bg-task-id="task-smoke"]')
  await taskCard.waitFor({ state: 'visible', timeout: 7000 })
  assert.equal(await taskCard.count(), 1)
  await expectVisible(page, 'Smoke task result')
  const userBox = await page.getByText('Hello from smoke').first().boundingBox()
  const taskBox = await taskCard.first().boundingBox()
  assert(userBox && taskBox && taskBox.y > userBox.y, 'anchored task card should render after its trigger turn')

  await page.goto(`${baseURL}/settings/tools/skills`)
  await expectVisible(page, 'Skills')

  await page.goto(`${baseURL}/settings/system/lan-access`)
  await expectVisible(page, 'LAN Access')
  await expectVisible(page, 'LAN URLs')
  await expectVisible(page, 'PIN Pairing')
  await expectVisible(page, 'Device Tokens')
  await expectVisible(page, 'Audit')

  await page.close()
}

async function runMobileSmoke(browser) {
  const page = await browser.newPage({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  })
  attachPageDiagnostics(page)
  await installApiMocks(page)

  await page.goto(baseURL)
  await expectVisible(page, 'Chat')
  await expectVisible(page, 'Settings')
  await expectVisible(page, 'Nanobot / Codex')
  assert(await page.locator('.mobile-chat-shell').count(), 'mobile chat shell should render')

  await page.goto(`${baseURL}/?view=tasks`)
  assert(await page.locator('.mobile-task-overlay-body').count(), 'mobile task overlay should render')

  await page.close()
}

const browserTypes = { chromium, firefox, webkit }
const browserType = browserTypes[browserName]
if (!browserType) {
  throw new Error(`Unsupported BROWSER=${browserName}`)
}

const browser = await browserType.launch({ headless: true })
try {
  await runDesktopSmoke(browser)
  await runMobileSmoke(browser)
  console.log('control-plane-smoke: passed')
} finally {
  await browser.close()
}
