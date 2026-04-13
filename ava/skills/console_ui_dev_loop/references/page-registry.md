# Page Registry

## 页面注册表

| key | path | 权限要求 | 源文件 | 详细 reference |
|-----|------|----------|--------|---------------|
| `login` | `/login` | 无需登录 | `pages/LoginPage.tsx` | — |
| `dashboard` | `/` | 任意已登录 | `pages/DashboardPage.tsx` | `pages/dashboard.md` |
| `config` | `/config` | 任意已登录 | `pages/ConfigPage/index.tsx` | `pages/config.md` |
| `tasks` | `/tasks` | 任意已登录 | `pages/ScheduledTasksPage.tsx` | `pages/tasks.md` |
| `bg-tasks` | `/bg-tasks` | 非 viewer | `pages/BgTasksPage.tsx` | `pages/bg-tasks.md` |
| `memory` | `/memory` | 任意已登录 | `pages/MemoryPage.tsx` | `pages/memory.md` |
| `media` | `/media` | 任意已登录 | `pages/MediaPage.tsx` | `pages/media.md` |
| `persona` | `/persona` | 非 viewer | `pages/PersonaPage.tsx` | `pages/persona.md` |
| `skills` | `/skills` | 非 viewer | `pages/SkillsPage.tsx` | `pages/skills.md` |
| `chat` | `/chat` | 非 viewer | `pages/ChatPage/index.tsx` | `pages/chat.md` |
| `tokens` | `/tokens` | 任意已登录 | `pages/TokenStatsPage.tsx` | `pages/tokens.md` |
| `users` | `/users` | 仅 admin | `pages/UsersPage.tsx` | — |
| `browser` | `/browser` | 非 mock_tester | `pages/BrowserPage.tsx` | — |

> 源文件路径省略 `console-ui/src/` 前缀。

## 文件 -> 页面映射

当根据 `changed_files` 确定测试范围时使用：

| 文件路径模式 | 受影响页面 |
|-------------|-----------|
| `pages/DashboardPage*` | `dashboard` |
| `pages/ConfigPage*` | `config` |
| `pages/ScheduledTasksPage*` | `tasks` |
| `pages/BgTasksPage*` | `bg-tasks` |
| `pages/MemoryPage*` | `memory` |
| `pages/MediaPage*` | `media` |
| `pages/PersonaPage*` | `persona` |
| `pages/SkillsPage*` | `skills` |
| `pages/ChatPage*` | `chat` |
| `pages/TokenStatsPage*` | `tokens` |
| `pages/UsersPage*` | `users` |
| `pages/BrowserPage*` | `browser` |
| `components/layout/*` | 当前页面 + `dashboard`（Sidebar 共享） |
| `api/*` | `baseline_smoke`，必要时扩大 |
| `stores/*` | `baseline_smoke`，必要时扩大 |

## 页面选择优先级

页面范围按以下顺序确定：

1. **explicit_pages** — 用户直接指定的页面
2. **changed_files 映射** — 根据上表推导
3. **baseline_smoke** — `login` → `dashboard` → `config` → `chat` → `tokens`
4. **full_regression** — 全部页面

默认中间轮次只扩到 `baseline_smoke`，不要直接全量。

## 特殊规则

- `users` 仅 admin 可访问；mock_tester 角色应返回 `skipped(AUTH_REQUIRED)`
- `browser` 不对 mock_tester 开放，同理 skip
- 登录页与主应用页是不同边界；不要因为进入了 `/login` 就误判所有业务页失败
- 当 `changed_files` 只落在单页内部时，不要无条件扩大到全量回归
