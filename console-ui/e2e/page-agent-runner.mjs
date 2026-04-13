#!/usr/bin/env node
/**
 * page-agent-runner.mjs
 *
 * 常驻 Node 进程，通过 stdin/stdout JSON-RPC 与 Python PageAgentTool 通信。
 * 负责：Playwright 浏览器管理、page-agent 注入与执行、CDP screencast、activity 事件转发。
 *
 * 通信协议：
 *   stdin  → 每行一个 JSON（RPC 请求，带 id + method + params）
 *   stdout → 每行一个 JSON
 *            - RPC 响应：{ id, success, result/error }
 *            - 推送事件：{ type: "frame"/"activity"/"status"/"session_closed", session_id, ... }（无 id）
 *   stderr → 心跳和日志（不影响 RPC）
 */

import { createInterface } from "node:readline";
import { readFileSync, mkdirSync } from "node:fs";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";
import { chromium, firefox, webkit } from "playwright";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PAGE_AGENT_BUNDLE = readFileSync(
  resolve(__dirname, '../node_modules/page-agent/dist/iife/page-agent.demo.js'),
  'utf-8',
);

// ---------------------------------------------------------------------------
// 全局状态
// ---------------------------------------------------------------------------

/** @type {import('playwright').Browser | import('playwright').BrowserContext | null} */
let browser = null;
/** 持久化 context 模式时为 true（此时 browser 实际是 BrowserContext） */
let persistentMode = false;

/** @type {Map<string, { page: import('playwright').Page, cdp: any | null, screencastActive: boolean, activityBridgeExposed: boolean, createdAt: number, lastTouched: number, inFlight: number, llmUsage: { requests: number, promptTokens: number, completionTokens: number, totalTokens: number } }>} */
const sessions = new Map();

/** 启动时从 init 命令接收的配置 */
let config = {
  headless: true,
  browserType: "chromium",
  viewportWidth: 1280,
  viewportHeight: 720,
  userDataDir: "",
  // page-agent LLM 配置
  apiBase: "",
  apiKey: "",
  model: "",
  maxSteps: 40,
  stepDelay: 0.4,
  language: "zh-CN",
};

const MAX_SESSIONS = 5;
const SESSION_IDLE_TTL_MS = 10 * 60 * 1000;
const SESSION_SWEEP_INTERVAL_MS = 60 * 1000;

const DEFAULT_USER_DATA_DIR = join(homedir(), ".nanobot", "page-agent", "chrome-data");

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

function send(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

function log(msg) {
  process.stderr.write(`[runner] ${new Date().toISOString()} ${msg}\n`);
}

function reply(id, success, data) {
  if (success) {
    send({ id, success: true, result: data });
  } else {
    send({ id, success: false, error: data });
  }
}

function pushEvent(type, sessionId, payload) {
  send({ type, session_id: sessionId, ...payload });
}

function touchSession(session) {
  session.lastTouched = Date.now();
}

function canEvictSession(session) {
  return !session.screencastActive && (session.inFlight || 0) === 0;
}

async function disposeSession(sessionId, reason = "closed") {
  if (!sessions.has(sessionId)) return false;

  const session = sessions.get(sessionId);
  await stopScreencast(session, sessionId);

  try {
    if (persistentMode) {
      await session.page.close();
    } else {
      await session.page.context().close();
    }
  } catch { /* ignore */ }

  sessions.delete(sessionId);
  pushEvent("session_closed", sessionId, { reason });
  log(`session closed: ${sessionId} (${reason})`);
  return true;
}

async function evictIdleSessions() {
  const now = Date.now();
  for (const [sessionId, session] of Array.from(sessions.entries())) {
    if (!canEvictSession(session)) continue;
    if ((now - session.lastTouched) < SESSION_IDLE_TTL_MS) continue;
    await disposeSession(sessionId, "idle_timeout");
  }
}

async function ensureSessionCapacity() {
  await evictIdleSessions();
  while (sessions.size >= MAX_SESSIONS) {
    let oldestEntry = null;
    for (const entry of sessions.entries()) {
      const [, session] = entry;
      if (!canEvictSession(session)) continue;
      if (!oldestEntry || session.lastTouched < oldestEntry[1].lastTouched) {
        oldestEntry = entry;
      }
    }
    if (!oldestEntry) break;
    await disposeSession(oldestEntry[0], "capacity_eviction");
  }
  if (sessions.size >= MAX_SESSIONS) {
    throw new Error(`session limit reached (max ${MAX_SESSIONS})`);
  }
}

// ---------------------------------------------------------------------------
// 浏览器管理
// ---------------------------------------------------------------------------

async function ensureBrowser() {
  if (browser) {
    const connected = persistentMode
      ? !browser.pages ? false : true
      : browser.isConnected();
    if (connected) return browser;
  }

  const launchers = { chromium, firefox, webkit };
  const launcher = launchers[config.browserType] || chromium;

  const launchOpts = { headless: config.headless };
  if (!config.headless) {
    launchOpts.args = ["--start-maximized"];
  }

  // 持久化模式：仅当 userDataDir 配置时启用
  if (config.userDataDir && (config.browserType === "chromium" || !config.browserType)) {
    const dataDir = config.userDataDir === "default" ? DEFAULT_USER_DATA_DIR : config.userDataDir;
    mkdirSync(dataDir, { recursive: true });
    if (!config.headless) {
      launchOpts.viewport = null;
    } else {
      launchOpts.viewport = { width: config.viewportWidth, height: config.viewportHeight };
    }
    browser = await launcher.launchPersistentContext(dataDir, launchOpts);
    persistentMode = true;
    log(`persistent browser launched (userDataDir=${dataDir}, headless=${config.headless})`);
  } else {
    browser = await launcher.launch(launchOpts);
    persistentMode = false;
    log(`browser launched (${config.browserType}, headless=${config.headless})`);
  }

  return browser;
}

async function getOrCreateSession(sessionId) {
  if (sessions.has(sessionId)) {
    const existing = sessions.get(sessionId);
    touchSession(existing);
    return existing;
  }

  await ensureSessionCapacity();

  const b = await ensureBrowser();
  let page;
  if (persistentMode) {
    page = await b.newPage();
  } else {
    const viewport = config.headless
      ? { width: config.viewportWidth, height: config.viewportHeight }
      : null;
    const context = await b.newContext({ viewport });
    page = await context.newPage();
  }
  const session = {
    page,
    cdp: null,
    screencastActive: false,
    activityBridgeExposed: false,
    createdAt: Date.now(),
    lastTouched: Date.now(),
    inFlight: 0,
    llmUsage: { requests: 0, promptTokens: 0, completionTokens: 0, totalTokens: 0 },
  };

  // 拦截 page-agent 内部的 LLM API 调用，累积 token usage
  if (config.apiBase) {
    const apiOrigin = new URL(config.apiBase).origin;
    log(`setting up LLM usage route interception for ${apiOrigin}`);
    await page.route(`${apiOrigin}/**`, async (route) => {
      const response = await route.fetch();
      const bodyBuf = await response.body();
      const contentType = response.headers()["content-type"] || "";

      const extractUsage = (usage) => {
        if (!usage) return;
        session.llmUsage.requests += 1;
        session.llmUsage.promptTokens += usage.prompt_tokens || 0;
        session.llmUsage.completionTokens += usage.completion_tokens || 0;
        session.llmUsage.totalTokens += usage.total_tokens || 0;
        log(`LLM usage captured: prompt=${usage.prompt_tokens || 0} completion=${usage.completion_tokens || 0}`);
      };

      if (contentType.includes("json")) {
        try {
          const data = JSON.parse(bodyBuf.toString("utf-8"));
          extractUsage(data?.usage);
        } catch { /* parse error — ignore */ }
      } else if (contentType.includes("event-stream")) {
        // SSE 流式响应：从最后一个 data 行中提取 usage
        try {
          const lines = bodyBuf.toString("utf-8").split("\n");
          for (let i = lines.length - 1; i >= 0; i--) {
            const line = lines[i];
            if (line.startsWith("data: ") && !line.includes("[DONE]")) {
              const data = JSON.parse(line.slice(6));
              if (data?.usage?.total_tokens) {
                extractUsage(data.usage);
                break;
              }
            }
          }
        } catch { /* SSE parse error — ignore */ }
      }

      await route.fulfill({
        status: response.status(),
        headers: response.headers(),
        body: bodyBuf,
      });
    });
  }

  sessions.set(sessionId, session);
  log(`session created: ${sessionId}`);
  return session;
}

// ---------------------------------------------------------------------------
// page-agent 注入与执行
// ---------------------------------------------------------------------------

/**
 * 在页面中注入 page-agent 并执行指令。
 * page-agent 是纯前端库，必须在浏览器页面上下文中运行。
 */
async function executePageAgent(page, instruction) {
  // 注入 page-agent（如果尚未注入）
  const alreadyInjected = await page.evaluate(() => !!window.__pageAgentInjected);

  if (!alreadyInjected) {
    // 通过本地 bundle 内容注入 page-agent（避免 CSP 限制）
    // 重试机制：SPA 路由跳转可能导致执行上下文短暂销毁
    let injected = false;
    for (let attempt = 0; attempt < 3 && !injected; attempt++) {
      try {
        await page.addScriptTag({ content: PAGE_AGENT_BUNDLE });
        await page.evaluate(() => {
          window.__pageAgentInjected = true;
        });
        injected = true;
      } catch (err) {
        if (attempt < 2 && err.message.includes("Execution context")) {
          log(`addScriptTag attempt ${attempt + 1} failed (context destroyed), retrying...`);
          await new Promise((r) => setTimeout(r, 300));
          continue;
        }
        throw err;
      }
    }
    log("page-agent injected via local bundle");
  }

  // 在页面上下文中创建 PageAgent 实例并执行
  const result = await page.evaluate(
    async ({ instruction, cfg }) => {
      const PageAgent = window.PageAgent;
      if (typeof PageAgent !== "function") {
        throw new Error("PageAgent constructor not found on window after injection");
      }

      const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

      // 每次执行复用或新建 agent
      if (!window.__paAgent) {
        // demo bundle 会异步自动创建 window.pageAgent；先等它跑完再清理，
        // 避免和 runner 自己管理的实例重复叠加。
        for (let i = 0; i < 5 && !window.pageAgent; i += 1) {
          await wait(0);
        }
        if (window.pageAgent) {
          try {
            window.pageAgent.dispose?.();
          } catch {
            /* ignore demo bundle cleanup failure */
          }
          window.pageAgent = null;
        }

        window.__paAgent = new PageAgent({
          baseURL: cfg.apiBase || undefined,
          apiKey: cfg.apiKey || undefined,
          model: cfg.model || undefined,
          maxSteps: cfg.maxSteps || 40,
          stepDelay: cfg.stepDelay || 0.4,
          language: cfg.language || "zh-CN",
          enableMask: true,
          viewportExpansion: 0,
        });
      }

      const agent = window.__paAgent;
      const executionResult = await agent.execute(instruction);

      // 提取当前页面结构化状态，供外层 LLM 判断而无需调用 vision
      let pageState = {};
      try {
        const vis = (el) => el && el.offsetParent !== null;
        const txt = (el) => (el.textContent || "").trim();
        const headings = [...document.querySelectorAll("h1, h2, h3")]
          .filter(vis)
          .map(txt)
          .filter(Boolean)
          .slice(0, 8);
        const alerts = [
          ...document.querySelectorAll(
            '[role="alert"], .error, .alert, .warning, .success, .toast, .notification'
          ),
        ]
          .filter(vis)
          .map(txt)
          .filter(Boolean)
          .slice(0, 5);
        const forms = [...document.querySelectorAll("form")].slice(0, 3).map((f) => {
          const inputs = [...f.querySelectorAll("input, select, textarea")]
            .slice(0, 10)
            .map((i) => ({
              type: i.type || "text",
              name: i.name || i.id || "",
              placeholder: i.placeholder || "",
              hasValue: i.type === "password" ? i.value.length > 0 : Boolean(i.value),
            }));
          return { inputs };
        });
        const buttons = [...document.querySelectorAll("button, [role='button'], input[type='submit']")]
          .filter(vis)
          .map(txt)
          .filter(Boolean)
          .slice(0, 10);
        pageState = { headings, alerts, forms, buttons };
      } catch {
        /* DOM 提取失败不影响主流程 */
      }

      return {
        success: executionResult.success,
        data: executionResult.data || "",
        steps: executionResult.history
          ? executionResult.history.filter((e) => e.type === "step").length
          : 0,
        pageState,
      };
    },
    {
      instruction,
      cfg: {
        apiBase: config.apiBase,
        apiKey: config.apiKey,
        model: config.model,
        maxSteps: config.maxSteps,
        stepDelay: config.stepDelay,
        language: config.language,
      },
    }
  );

  return result;
}

// ---------------------------------------------------------------------------
// Activity 事件监听（通过 page.exposeFunction 桥接）
// ---------------------------------------------------------------------------

async function setupActivityBridge(sessionId, session) {
  const { page } = session;

  // page.exposeFunction 绑定在 Playwright Page 对象上，而不是页面 DOM 上。
  // 导航后 window 标记会丢，但 exposeFunction 仍然存在，因此注册状态必须保存在 session 侧。
  if (!session.activityBridgeExposed) {
    await page.exposeFunction("__paOnActivity", (activityJson) => {
      try {
        const activity = JSON.parse(activityJson);
        pushEvent("activity", sessionId, { activity });
      } catch { /* ignore parse errors */ }
    });

    await page.exposeFunction("__paOnStatus", (status) => {
      pushEvent("status", sessionId, { status });
    });

    session.activityBridgeExposed = true;
  }

  // 页面内监听器需要按 document 生命周期重建；导航后该标记会自然丢失。
  let bridged = false;
  try {
    bridged = await page.evaluate(() => !!window.__paActivityBridged);
  } catch { /* 导航后上下文可能已销毁，视为未桥接 */ }
  if (bridged) return;

  // 在页面中挂载监听器
  await page.evaluate(() => {
    window.__paActivityBridged = true;

    // 轮询等待 agent 实例化后挂载监听
    const poll = setInterval(() => {
      const agent = window.__paAgent;
      if (!agent) return;
      clearInterval(poll);

      agent.addEventListener("activity", (e) => {
        window.__paOnActivity(JSON.stringify(e.detail || e.data || {}));
      });
      agent.addEventListener("statuschange", (e) => {
        window.__paOnStatus(e.detail || e.data || "unknown");
      });
    }, 200);

    // 30 秒后停止轮询
    setTimeout(() => clearInterval(poll), 30000);
  });
}

// ---------------------------------------------------------------------------
// CDP Screencast
// ---------------------------------------------------------------------------

async function startScreencast(session, sessionId, params) {
  touchSession(session);
  if (session.screencastActive) return;

  // CDP 只在 Chromium 上可用
  if (config.browserType !== "chromium") {
    throw new Error("screencast requires chromium browser");
  }

  const context = session.page.context();
  session.cdp = await context.newCDPSession(session.page);

  session.cdp.on("Page.screencastFrame", async (frame) => {
    pushEvent("frame", sessionId, {
      data: frame.data,
      metadata: { timestamp: frame.metadata?.timestamp },
    });
    // ack 以触发下一帧
    try {
      await session.cdp.send("Page.screencastFrameAck", {
        sessionId: frame.sessionId,
      });
    } catch { /* session 可能已关闭 */ }
  });

  await session.cdp.send("Page.startScreencast", {
    format: "jpeg",
    quality: params?.quality || 60,
    maxWidth: params?.maxWidth || config.viewportWidth,
    maxHeight: params?.maxHeight || config.viewportHeight,
    everyNthFrame: params?.everyNthFrame || 2,
  });

  session.screencastActive = true;
  log(`screencast started for ${sessionId}`);
}

async function stopScreencast(session, sessionId) {
  if (!session.screencastActive || !session.cdp) return;

  try {
    await session.cdp.send("Page.stopScreencast");
    await session.cdp.detach();
  } catch { /* ignore */ }

  session.cdp = null;
  session.screencastActive = false;
  touchSession(session);
  log(`screencast stopped for ${sessionId}`);
}

// ---------------------------------------------------------------------------
// RPC Method Handlers
// ---------------------------------------------------------------------------

const handlers = {
  async init(id, params) {
    Object.assign(config, params);
    reply(id, true, { message: "config updated" });
    log(`config updated: browserType=${config.browserType}, headless=${config.headless}, model=${config.model}`);
  },

  async execute(id, params) {
    const { url, instruction, session_id: sid } = params;
    if (!instruction) {
      return reply(id, false, { code: "MISSING_PARAM", message: "instruction is required" });
    }

    const sessionId = sid || `s_${Date.now().toString(36)}`;
    let session = null;
    const startMs = Date.now();

    try {
      session = await getOrCreateSession(sessionId);
      session.inFlight += 1;
      touchSession(session);

      if (url) {
        await session.page.goto(url, { waitUntil: "load", timeout: 30000 });
        // SPA 客户端路由可能在 load 后触发二次导航（如 / → /login），
        // 等待网络空闲以确保重定向链完成、执行上下文稳定。
        await session.page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
        touchSession(session);
      }

      await setupActivityBridge(sessionId, session);

      const result = await executePageAgent(session.page, instruction);

      const pageUrl = session.page.url();
      const pageTitle = await session.page.title();

      const llmUsage = session ? { ...session.llmUsage } : {};
      if (session) {
        session.llmUsage = { requests: 0, promptTokens: 0, completionTokens: 0, totalTokens: 0 };
        touchSession(session);
      }
      reply(id, true, {
        session_id: sessionId,
        data: result.data,
        success: result.success,
        steps: result.steps,
        duration: Date.now() - startMs,
        page_url: pageUrl,
        page_title: pageTitle,
        page_state: result.pageState || {},
        llm_usage: llmUsage,
      });
    } catch (err) {
      let pageUrl = url || "unknown";
      let pageTitle = "unknown";
      if (session?.page) {
        try {
          pageUrl = session.page.url();
          pageTitle = await session.page.title();
        } catch { /* ignore */ }
      }
      reply(id, false, {
        code: "EXECUTION_FAILED",
        message: err.message,
        session_id: sessionId,
        duration: Date.now() - startMs,
        page_url: pageUrl,
        page_title: pageTitle,
      });
    } finally {
      if (session) {
        session.inFlight = Math.max(0, session.inFlight - 1);
        touchSession(session);
      }
    }
  },

  async screenshot(id, params) {
    const { session_id: sid, path: savePath, url } = params;
    if (!sid) {
      return reply(id, false, { code: "NO_SESSION", message: "session_id is required" });
    }

    try {
      // 若 session 不存在但提供了 url，自动创建 session 并导航
      let session = sessions.get(sid);
      if (!session) {
        if (!url) {
          return reply(id, false, { code: "NO_SESSION", message: `session ${sid} not found` });
        }
        session = await getOrCreateSession(sid);
        await session.page.goto(url, { waitUntil: "load", timeout: 30000 });
        await session.page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
      } else if (url) {
        // session 已存在但提供了新 url，导航到新页面
        await session.page.goto(url, { waitUntil: "load", timeout: 30000 });
        await session.page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
      }
      touchSession(session);

      // 截图前隐藏 page-agent 注入的 UI 面板，避免遮挡页面内容
      await session.page.evaluate(() => {
        const selectors = [
          '[class*="page-agent"]',
          '[class*="pageagent"]',
          '[id*="page-agent"]',
          '[id*="pageagent"]',
          '[class*="agent-panel"]',
          '[class*="runtime_agent"]',
        ];
        window.__paHiddenEls = [];
        for (const sel of selectors) {
          for (const el of document.querySelectorAll(sel)) {
            if (el.style.display !== "none") {
              window.__paHiddenEls.push({ el, prev: el.style.display });
              el.style.display = "none";
            }
          }
        }
      }).catch(() => {});

      const buffer = await session.page.screenshot({
        type: "png",
        fullPage: false,
      });

      // 截图后恢复
      await session.page.evaluate(() => {
        if (window.__paHiddenEls) {
          for (const { el, prev } of window.__paHiddenEls) {
            el.style.display = prev;
          }
          window.__paHiddenEls = null;
        }
      }).catch(() => {});

      if (savePath) {
        const { writeFileSync } = await import("node:fs");
        writeFileSync(savePath, buffer);
        reply(id, true, { path: savePath, size: buffer.length });
      } else {
        // 返回 base64
        reply(id, true, { data: buffer.toString("base64"), size: buffer.length });
      }
    } catch (err) {
      reply(id, false, { code: "SCREENSHOT_FAILED", message: err.message });
    }
  },

  async get_page_info(id, params) {
    const { session_id: sid } = params;
    if (!sid || !sessions.has(sid)) {
      return reply(id, false, { code: "NO_SESSION", message: `session ${sid} not found` });
    }

    const session = sessions.get(sid);
    touchSession(session);
    const pageUrl = session.page.url();
    const pageTitle = await session.page.title();
    const viewport = session.page.viewportSize();

    reply(id, true, {
      page_url: pageUrl,
      page_title: pageTitle,
      viewport: viewport ? `${viewport.width}x${viewport.height}` : "unknown",
    });
  },

  async list_sessions(id) {
    await evictIdleSessions();
    reply(id, true, {
      sessions: Array.from(sessions.keys()),
    });
  },

  async close_session(id, params) {
    const { session_id: sid } = params;
    if (!sid || !sessions.has(sid)) {
      return reply(id, true, { message: `session ${sid} already closed` });
    }

    await disposeSession(sid, "close_session");
    reply(id, true, { message: `session ${sid} closed` });
  },

  async start_screencast(id, params) {
    const { session_id: sid } = params;
    if (!sid || !sessions.has(sid)) {
      return reply(id, false, { code: "NO_SESSION", message: `session ${sid} not found` });
    }

    try {
      const session = sessions.get(sid);
      touchSession(session);
      await startScreencast(session, sid, params);
      reply(id, true, { message: "screencast started" });
    } catch (err) {
      reply(id, false, { code: "SCREENCAST_FAILED", message: err.message });
    }
  },

  async stop_screencast(id, params) {
    const { session_id: sid } = params;
    if (!sid || !sessions.has(sid)) {
      return reply(id, true, { message: "no active screencast" });
    }

    const session = sessions.get(sid);
    touchSession(session);
    await stopScreencast(session, sid);
    reply(id, true, { message: "screencast stopped" });
  },

  async shutdown(id) {
    log("shutdown requested");

    for (const sid of Array.from(sessions.keys())) {
      await disposeSession(sid, "runner_shutdown");
    }

    if (browser) {
      try { await browser.close(); } catch { /* ignore */ }
      browser = null;
    }

    reply(id, true, { message: "shutdown complete" });

    // 延迟退出，确保响应已写入 stdout
    setTimeout(() => process.exit(0), 100);
  },
};

// ---------------------------------------------------------------------------
// stdin RPC 循环
// ---------------------------------------------------------------------------

const rl = createInterface({ input: process.stdin, terminal: false });

// 长时间运行的方法列表（不阻塞 RPC 循环）
const longRunningMethods = new Set(["execute"]);

rl.on("line", (line) => {
  let msg;
  try {
    msg = JSON.parse(line.trim());
  } catch {
    log(`invalid JSON: ${line}`);
    return;
  }

  const { id, method, params } = msg;
  if (!id || !method) {
    log(`malformed RPC: missing id or method`);
    return;
  }

  const handler = handlers[method];
  if (!handler) {
    reply(id, false, { code: "UNKNOWN_METHOD", message: `unknown method: ${method}` });
    return;
  }

  // 长时间运行的方法在后台执行，不阻塞其他 RPC（如 start_screencast、list_sessions）
  const run = async () => {
    try {
      await handler(id, params || {});
    } catch (err) {
      reply(id, false, { code: "INTERNAL_ERROR", message: err.message });
    }
  };

  if (longRunningMethods.has(method)) {
    run(); // 不 await，放入后台
  } else {
    run(); // 同样不 await — readline 回调本身是同步的
  }
});

rl.on("close", () => {
  log("stdin closed, shutting down");
  process.exit(0);
});

// ---------------------------------------------------------------------------
// 心跳
// ---------------------------------------------------------------------------

setInterval(() => {
  log(`heartbeat sessions=${sessions.size} browser=${browser?.isConnected() ?? false}`);
}, 30000);

setInterval(() => {
  evictIdleSessions().catch((err) => log(`idle session sweep failed: ${err.message}`));
}, SESSION_SWEEP_INTERVAL_MS);

log("runner started, waiting for commands...");
