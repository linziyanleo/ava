#!/usr/bin/env node
import assert from 'node:assert/strict'
import { chromium, firefox, webkit } from 'playwright'

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:4173'
const browserType = { chromium, firefox, webkit }[process.env.PW_BROWSER || 'chromium'] || chromium
const now = new Date().toISOString()

function json(route, data, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
}

const task = {
  task_id: 'p2-mobile-task',
  task_type: 'codex',
  origin_session_key: 'session-a',
  status: 'running',
  prompt_preview: 'Mobile acceptance smoke',
  started_at: Date.now(),
  finished_at: null,
  elapsed_ms: 1200,
  result_preview: '',
  error_message: '',
  timeline: [],
  phase: 'execute',
  last_tool_name: '',
  todo_summary: null,
  project_path: '/Users/fanghu/Documents/Test/ava',
  cli_run_id: '',
  cli_session_id: '',
  repo_root: '/Users/fanghu/Documents/Test/ava',
  workdir_relpath: '.',
  workspace_key: 'ava',
  workspace_id: 'ava',
  execution_cwd: '/Users/fanghu/Documents/Test/ava',
  isolation_mode: 'worktree',
  branch_name: 'feat/0.1.0',
  worktree_path: '/Users/fanghu/Documents/Test/ava/.worktrees/p2-mobile-remote-linked',
}

const codexAgent = {
  name: 'codex',
  instance_id: 'codex-standard',
  display_name: 'Codex',
  kind: 'cli',
  status: 'available',
  installed: true,
  path: '/usr/local/bin/codex',
  version: 'test',
  detail: '',
  install_url: '',
  active_tasks: 1,
  recent_events: [],
  recent_artifacts: [],
  capabilities: {
    supports_chat: true,
    supports_task: true,
    supports_cancel: true,
    supports_restart: false,
    supports_streaming: true,
    supports_artifacts: true,
    max_concurrent_tasks: 1,
    supported_artifact_types: ['text'],
  },
}

async function installMocks(page) {
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, '')
    if (path === '/auth/me') return json(route, { username: 'editor', role: 'editor', created_at: now })
    if (path === '/chat/sessions') return json(route, [])
    if (path === '/chat/conversations') return json(route, [])
    if (path === '/skills/list') return json(route, { skills: [{ name: 'playwright', enabled: true, description: 'Browser' }] })
    if (path === '/gateway/status') return json(route, { memory_rss_bytes: 1024 })
    if (path === '/artifacts') return json(route, { artifacts: [] })
    if (path === '/agents') return json(route, { agents: [codexAgent], summary: { total: 1, available: 1, running: 0 } })
    if (path === '/console/direct-tasks') return json(route, { task_id: 'direct-p2', status: 'queued', task_type: 'codex' })
    if (path === '/bg-tasks/history') return json(route, { tasks: [], total: 0, page: 1, page_size: 20 })
    if (path === '/bg-tasks/p2-mobile-task') return json(route, task)
    if (path === '/bg-tasks/p2-mobile-task/detail') return json(route, { full_prompt: task.prompt_preview, full_result: '' })
    if (path.startsWith('/bg-tasks')) return json(route, { running: 1, total: 1, tasks: [task] })
    return json(route, {})
  })
}

const browser = await browserType.launch()
for (const viewport of [
  { width: 390, height: 844, mobile: true },
  { width: 900, height: 700, tablet: true },
  { width: 1180, height: 760, desktop: true },
]) {
  const page = await browser.newPage({ viewport })
  await installMocks(page)
  await page.goto(baseURL)
  await page.getByText('Chat').first().waitFor()
  const mode = await page.evaluate(() => ({
    isTablet: window.innerWidth >= 768 && window.innerWidth <= 1024,
    isLandscape: window.innerWidth > window.innerHeight,
  }))
  assert.equal(mode.isTablet, !!viewport.tablet)
  assert.equal(mode.isLandscape, viewport.width > viewport.height)
  await page.getByText('Skills').first().click()
  await page.getByText('playwright').waitFor()
  if (viewport.mobile) {
    await page.getByRole('button', { name: '展开' }).click()
    await page.getByText('Mobile acceptance smoke').waitFor()
    await page.getByRole('button', { name: '关闭任务浮窗' }).click()
  }
  await page.close()
}

const dashboardPage = await browser.newPage({ viewport: { width: 390, height: 844 } })
await installMocks(dashboardPage)
await dashboardPage.goto(`${baseURL}/settings/agents-config`)
await dashboardPage.getByText('Agent Dashboard').waitFor()
await dashboardPage.getByText('Codex').waitFor()
await dashboardPage.getByRole('button', { name: 'Run Task' }).click()
await dashboardPage.getByText('Run Codex Task').waitFor()
const modalClass = await dashboardPage.locator('section').filter({ hasText: 'Run Codex Task' }).getAttribute('class')
assert.match(modalClass, /max-h-\[calc\(100vh-2rem\)\]/)
assert.match(modalClass, /w-full/)
await dashboardPage.close()
await browser.close()
