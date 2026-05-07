import { chromium } from 'playwright'

const BASE = 'http://localhost:6688'
const MOCK_TESTER_PASSWORD = process.env.MOCK_TESTER_PASSWORD ?? ''

function log(msg) { console.log(msg) }

async function login(page) {
  if (!MOCK_TESTER_PASSWORD) {
    throw new Error('Missing MOCK_TESTER_PASSWORD env var')
  }
  // Use API login for reliability
  const resp = await page.request.post(`${BASE}/api/auth/login`, {
    data: { username: 'mock_tester', password: MOCK_TESTER_PASSWORD },
  })
  if (!resp.ok()) {
    log(`  Login API failed: ${resp.status()}`)
    // Fallback: UI login
    await page.goto(`${BASE}/login`)
    await page.waitForLoadState('networkidle')
    const usernameInput = page.locator('input').first()
    await usernameInput.fill('mock_tester')
    const pwdInput = page.locator('input[type="password"]').first()
    await pwdInput.fill(MOCK_TESTER_PASSWORD)
    await page.keyboard.press('Enter')
    await page.waitForTimeout(2000)
  } else {
    log('  Login API: OK')
  }
  return true
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext()
  const page = await context.newPage()
  let allPassed = true

  try {
    log('\n=== LOGIN ===')
    await login(page)
    log('  Page loaded at: ' + page.url())
    
    // Test 1: /bg-tasks?task_id=mock-task-run-1
    log('\n=== TEST 1: /bg-tasks?task_id=mock-task-run-1 ===')
    await page.goto(`${BASE}/bg-tasks?task_id=mock-task-run-1`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    
    const taskCard = page.locator('[data-task-id="mock-task-run-1"]')
    const taskCardCount = await taskCard.count()
    log(`  [${taskCardCount > 0 ? 'PASS' : 'FAIL'}] data-task-id="mock-task-run-1" card: ${taskCardCount > 0}`)
    if (taskCardCount === 0) allPassed = false
    
    if (taskCardCount > 0) {
      // Check for "查看对话" button (MessageSquare icon with 对话)
      const chatBtns = await page.locator('[data-task-id="mock-task-run-1"] button').all()
      let hasChatBtn = false
      for (const btn of chatBtns) {
        const title = await btn.getAttribute('title').catch(() => '')
        const text = await btn.textContent().catch(() => '')
        if (title?.includes('对话') || text?.includes('对话')) {
          hasChatBtn = true
          break
        }
      }
      log(`  [${hasChatBtn ? 'PASS' : 'FAIL'}] "对话" button on task card: ${hasChatBtn}`)
      if (!hasChatBtn) allPassed = false
      
      // Check card has an id
      const cardId = await taskCard.first().getAttribute('id')
      log(`  [${cardId === 'bg-task-mock-task-run-1' ? 'PASS' : 'FAIL'}] card id=bg-task-mock-task-run-1: ${cardId}`)
      if (cardId !== 'bg-task-mock-task-run-1') allPassed = false
    }
    
    await page.screenshot({ path: '/tmp/bg-tasks-deeplink.png', fullPage: false })
    log('  Screenshot: /tmp/bg-tasks-deeplink.png')
    
    // Test 2: /chat deep link - use session-1 which has a completed bg task result (mock-task-ok-1)
    log('\n=== TEST 2: /chat deep link to mock-session-1 with completed task ===')
    await page.goto(`${BASE}/chat?session_key=console:mock-session-1&conversation_id=mock-conv-1&task_id=mock-task-ok-1`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)
    
    // Check if data-turn-seq attrs exist
    const turnSeqElems = await page.locator('[data-turn-seq]').all()
    log(`  [${turnSeqElems.length > 0 ? 'PASS' : 'FAIL'}] data-turn-seq elements: ${turnSeqElems.length}`)
    if (turnSeqElems.length === 0) allPassed = false
    
    if (turnSeqElems.length > 0) {
      const seqVal = await turnSeqElems[0].getAttribute('data-turn-seq')
      log(`  First turn data-turn-seq value: ${seqVal}`)
      const firstTurnId = await turnSeqElems[0].getAttribute('id')
      log(`  First turn id: ${firstTurnId}`)
    }
    
    // Check for background task blocks with data-bg-task-id (mock-task-ok-1)
    const bgTaskBlocks = await page.locator('[data-bg-task-id="mock-task-ok-1"]').all()
    log(`  [${bgTaskBlocks.length > 0 ? 'PASS' : 'FAIL'}] data-bg-task-id="mock-task-ok-1" elements: ${bgTaskBlocks.length}`)
    if (bgTaskBlocks.length === 0) allPassed = false
    
    if (bgTaskBlocks.length > 0) {
      // Check for "查看后台任务" button
      let hasBgTaskBtn = false
      const blockBtns = await page.locator('[data-bg-task-id="mock-task-ok-1"] button').all()
      for (const btn of blockBtns) {
        const title = await btn.getAttribute('title').catch(() => '')
        const text = await btn.textContent().catch(() => '')
        if (title?.includes('后台任务') || text?.includes('后台任务') || title?.includes('bg') || text?.includes('bg')) {
          hasBgTaskBtn = true
          break
        }
      }
      log(`  [${hasBgTaskBtn ? 'PASS' : 'FAIL'}] "查看后台任务" button on bg task result: ${hasBgTaskBtn}`)
      if (!hasBgTaskBtn) allPassed = false
    }
    
    await page.screenshot({ path: '/tmp/chat-deeplink.png', fullPage: false })
    log('  Screenshot: /tmp/chat-deeplink.png')
    
    // Test 2b: Click "查看后台任务" button and verify navigation
    log('\n=== TEST 2b: Click "查看后台任务" to navigate to BgTasks ===')
    const bgTaskBtns2 = await page.locator('[data-bg-task-id="mock-task-ok-1"] button').all()
    let navigatedToBgTasks = false
    for (const btn of bgTaskBtns2) {
      const title = await btn.getAttribute('title').catch(() => '')
      const text = await btn.textContent().catch(() => '')
      if (title?.includes('后台任务') || text?.includes('后台任务')) {
        await btn.click()
        await page.waitForTimeout(1500)
        const navUrl = page.url()
        navigatedToBgTasks = navUrl.includes('/bg-tasks') && navUrl.includes('task_id=mock-task-ok-1')
        log(`  Navigated to: ${navUrl}`)
        log(`  [${navigatedToBgTasks ? 'PASS' : 'FAIL'}] URL contains /bg-tasks?task_id=mock-task-ok-1`)
        if (!navigatedToBgTasks) allPassed = false
        break
      }
    }
    if (!navigatedToBgTasks && bgTaskBtns2.length === 0) {
      log('  [SKIP] No bg task button found')
    }

    // Test 2c: On BgTasks page from navigation, click "对话" button back to chat
    log('\n=== TEST 2c: Click "对话" to navigate back to Chat ===')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    const convBtns = await page.locator('[data-task-id] button').all()
    let navigatedToChat = false
    for (const btn of convBtns) {
      const title = await btn.getAttribute('title').catch(() => '')
      const text = await btn.textContent().catch(() => '')
      if (title?.includes('对话') || text?.includes('对话')) {
        await btn.click()
        await page.waitForTimeout(1500)
        const chatUrl = page.url()
        navigatedToChat = chatUrl.includes('/chat') && chatUrl.includes('session_key=')
        log(`  Navigated to: ${chatUrl}`)
        log(`  [${navigatedToChat ? 'PASS' : 'FAIL'}] URL contains /chat with session_key`)
        if (!navigatedToChat) allPassed = false
        break
      }
    }
    if (!navigatedToChat && convBtns.length === 0) {
      log('  [SKIP] No conversation button found on bg-tasks page')
    }

    // Test 3: /bg-tasks?task_id=nonexistent 
    log('\n=== TEST 3: /bg-tasks?task_id=nonexistent ===')
    await page.goto(`${BASE}/bg-tasks?task_id=nonexistent-xyz-999`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    // Should show notice, not crash
    const bodyText = await page.locator('body').textContent()
    const hasNotice = bodyText.includes('找不到') || bodyText.includes('任务')
    log(`  [${!bodyText.includes('Error') ? 'PASS' : 'FAIL'}] No crash on nonexistent task`)
    log(`  Notice text found: ${hasNotice}`)
    
  } catch (e) {
    log(`  FATAL ERROR: ${e.message}`)
    allPassed = false
  } finally {
    await browser.close()
  }
  
  log('\n=== SUMMARY ===')
  log(`All tests ${allPassed ? 'PASSED' : 'had failures'}`)
  process.exit(allPassed ? 0 : 1)
}

main().catch(e => { console.error(e); process.exit(1) })
