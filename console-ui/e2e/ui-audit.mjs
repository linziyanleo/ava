#!/usr/bin/env node
/**
 * ui-audit.mjs
 *
 * 自动遍历 docs/UI_AUDIT.md §1-§3 的路由/浮层，按 desktop+mobile / dark+light
 * 截图到 console-ui/.audit/<slug>-<viewport>-<theme>.png，方便 agent 回头比对
 * DESIGN.md v0.4.3-B 的 6 条硬点位。
 *
 * 用法：
 *   node e2e/ui-audit.mjs                          # 默认 http://localhost:5173, dark+light
 *   node e2e/ui-audit.mjs --base=http://localhost:5173
 *   node e2e/ui-audit.mjs --theme=dark             # 仅 dark
 *   node e2e/ui-audit.mjs --route=/settings/statistics  # 只跑指定路由（精确匹配 path）
 *   node e2e/ui-audit.mjs --pass=xxx                # 自动登录（passphrase；否则需提前在共享 storage 中保留登录态）
 *   node e2e/ui-audit.mjs --storage=.audit/storage.json  # 复用登录态
 *
 * 不在脚本里做视觉断言；产出截图，由人/后续 agent 对照 docs/UI_AUDIT.md 第 0.4 节硬点位。
 */

import { mkdirSync, existsSync } from "node:fs";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..");
const OUT_DIR = resolve(REPO_ROOT, ".audit");

const args = parseArgs(process.argv.slice(2));
const BASE = args.base ?? "http://localhost:5173";
const THEMES = args.theme ? [args.theme] : ["dark", "light"];
const FILTER_ROUTE = args.route ?? null;
const STORAGE = args.storage ?? null;
const LOGIN_PASS = args.pass ?? null;

const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 800, deviceScaleFactor: 1 },
  { name: "mobile", width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
];

/**
 * 路由清单：与 docs/UI_AUDIT.md §2-§3 对齐。
 *
 * - path 直接 goto。
 * - waitFor 是渲染稳定后的 selector / text。可缺省。
 * - skipMobile / skipDesktop：某些页面只在某一档有意义。
 * - role: "anonymous" | "viewer"  —— anonymous 不要求登录；viewer 走 ProtectedRoute。
 */
const ROUTES = [
  // §2 一级路由
  { slug: "login", path: "/login", role: "anonymous", waitFor: 'input[type="password"]' },
  { slug: "chat-default", path: "/", role: "viewer" },
  { slug: "chat-tasks", path: "/?view=tasks", role: "viewer" },
  // /?view=media 需要带 task_id 才有意义；不在自动遍历范围，留给手动。

  // §2.4 settings — 普通用户可见路由
  { slug: "settings-agents-overview", path: "/settings/agents-config", role: "viewer" },
  { slug: "settings-agents-nanobot-config", path: "/settings/agents-config/nanobot/config", role: "viewer" },
  { slug: "settings-agents-nanobot-memory", path: "/settings/agents-config/nanobot/memory", role: "viewer" },
  { slug: "settings-agents-nanobot-persona", path: "/settings/agents-config/nanobot/persona", role: "viewer" },
  { slug: "settings-agents-codex-config", path: "/settings/agents-config/codex/config", role: "viewer" },
  { slug: "settings-agents-claude-code-config", path: "/settings/agents-config/claude-code/config", role: "viewer" },
  { slug: "settings-agents-image-gen-config", path: "/settings/agents-config/image-gen/config", role: "viewer" },
  { slug: "settings-statistics", path: "/settings/statistics", role: "viewer" },
  { slug: "settings-tools-skills", path: "/settings/tools/skills", role: "viewer" },
  { slug: "settings-system-gateway", path: "/settings/system/gateway", role: "viewer" },
  { slug: "settings-system-browser", path: "/settings/system/browser", role: "viewer" },
  { slug: "settings-system-console", path: "/settings/system/console", role: "viewer" },
  { slug: "settings-system-version", path: "/settings/system/version", role: "viewer" },

  // §4 legacy 路由 —— 截图应抓到「跳转后」的 URL，验证不闪烁
  { slug: "legacy-agents", path: "/agents", role: "viewer" },
  { slug: "legacy-config", path: "/config", role: "viewer" },
  { slug: "legacy-memory", path: "/memory", role: "viewer" },
  { slug: "legacy-persona", path: "/persona", role: "viewer" },
  { slug: "legacy-skills", path: "/skills", role: "viewer" },
  { slug: "legacy-chat", path: "/chat", role: "viewer" },
  { slug: "legacy-tasks", path: "/tasks", role: "viewer" },
  { slug: "legacy-bg-tasks", path: "/bg-tasks", role: "viewer" },
];

async function main() {
  if (!existsSync(OUT_DIR)) mkdirSync(OUT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const failures = [];
  let total = 0;

  for (const viewport of VIEWPORTS) {
    for (const theme of THEMES) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        deviceScaleFactor: viewport.deviceScaleFactor,
        isMobile: viewport.isMobile ?? false,
        hasTouch: viewport.hasTouch ?? false,
        storageState: STORAGE && existsSync(STORAGE) ? STORAGE : undefined,
        colorScheme: theme === "light" ? "light" : "dark",
      });
      // 注入主题 class；index.css 的 :root.light 切换靠这里
      await context.addInitScript((t) => {
        const apply = () => {
          if (t === "light") document.documentElement.classList.add("light");
          else document.documentElement.classList.remove("light");
        };
        if (document.readyState === "loading") {
          document.addEventListener("DOMContentLoaded", apply);
        } else apply();
      }, theme);

      const page = await context.newPage();

      if (LOGIN_PASS && !STORAGE) {
        await ensureLoggedIn(page, BASE, LOGIN_PASS);
      }

      for (const route of ROUTES) {
        if (FILTER_ROUTE && route.path !== FILTER_ROUTE) continue;
        if (viewport.name === "mobile" && route.skipMobile) continue;
        if (viewport.name === "desktop" && route.skipDesktop) continue;

        total += 1;
        const url = BASE + route.path;
        const file = join(OUT_DIR, `${route.slug}-${viewport.name}-${theme}.png`);
        try {
          await page.goto(url, { waitUntil: "networkidle", timeout: 15000 });
          if (route.waitFor) {
            await page.waitForSelector(route.waitFor, { timeout: 5000 });
          } else {
            // 给字体/动画 200ms 稳态
            await page.waitForTimeout(200);
          }
          await page.screenshot({ path: file, fullPage: false });
          process.stdout.write(`[OK]   ${viewport.name}/${theme} ${route.path}\n`);
        } catch (err) {
          failures.push({ route: route.path, viewport: viewport.name, theme, error: String(err.message || err) });
          process.stdout.write(`[FAIL] ${viewport.name}/${theme} ${route.path} -- ${err.message || err}\n`);
        }
      }

      await context.close();
    }
  }

  await browser.close();

  process.stdout.write(`\n截图共 ${total} 张，输出目录：${OUT_DIR}\n`);
  if (failures.length > 0) {
    process.stdout.write(`失败 ${failures.length} 项：\n`);
    for (const f of failures) {
      process.stdout.write(`  - ${f.viewport}/${f.theme} ${f.route}: ${f.error}\n`);
    }
    process.exit(1);
  }
}

async function ensureLoggedIn(page, base, pass) {
  await page.goto(base + "/login", { waitUntil: "networkidle" });
  if (page.url().endsWith("/login")) {
    await page.fill('input[type="password"]', pass);
    await Promise.all([
      page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 10000 }),
      page.click('button[type="submit"]'),
    ]);
  }
}

function parseArgs(argv) {
  const out = {};
  for (const arg of argv) {
    const m = arg.match(/^--([^=]+)=(.*)$/);
    if (m) out[m[1]] = m[2];
    else if (arg.startsWith("--")) out[arg.slice(2)] = "true";
  }
  return out;
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
