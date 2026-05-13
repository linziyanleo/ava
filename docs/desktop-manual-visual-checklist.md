# Desktop 人工视觉确认清单

日期：2026-05-13

这份指南用于普通 macOS 桌面会话。它只关闭自动脚本无法从 Codex sandbox
证明的人工视觉字段。

当前可用的 canonical 自动证据日志是：

- `docs/desktop-acceptance-happy.log`
- `docs/desktop-acceptance-port-conflict.log`

不要使用 `docs/desktop-acceptance-port-`；它来自一次被换行截断的非 canonical
命令，closeout guard 不接受它。

## 目标 App

canonical repo bundle：

```text
/Users/fanghu/Documents/Test/ava/electron/dist/Ava-darwin-arm64/Ava.app
```

`/Applications` / Launchpad 只作为可选同机检查。当前包内 runtime manifest 会指回
本机这个 repo checkout；这说明它能在同一台 Mac 上从应用抽屉启动，但不表示它是可拷到
另一台机器直接运行的分发包。

## 开始前

1. 从 Dock 或 app menu 退出所有正在运行的 `Ava.app`。
2. 确认 repo 路径：

```bash
cd /Users/fanghu/Documents/Test/ava
pwd
```

3. 先准备好 `.venv` 视觉测试的恢复命令：

```bash
cd /Users/fanghu/Documents/Test/ava
if [ -d .venv.visual-check.bak ]; then
  rm -rf .venv
  mv .venv.visual-check.bak .venv
fi
```

只在 `Ava.app` 已退出，或者 Cancel 已经明显停止 bootstrap 后，再执行这个恢复命令。

## 必填字段

每个字段填一句清楚的观察结论。相同内容必须同时写入
`docs/desktop-launch-acceptance.md` 和 active Task Spec 的两条 result record。

```text
Finder double-click, no Terminal:
Setup surface visible before Console:
Cancel stops uv sync, Retry starts again:
Help -> Open Logs opens ~/Library/Logs/Ava:
```

如果你的实际观察一致，可以直接使用下面这组值：

```text
Finder double-click, no Terminal: Confirmed in normal macOS desktop session: Finder double-click opened Ava.app without requiring Terminal, and Console loaded.
Setup surface visible before Console: Confirmed: with .venv temporarily moved aside, Ava Setup appeared before Console and showed bootstrap state plus log tail.
Cancel stops uv sync, Retry starts again: Confirmed: Cancel stopped the active bootstrap and showed canceled state; Retry started a new bootstrap attempt.
Help -> Open Logs opens ~/Library/Logs/Ava: Confirmed: Help -> Open Logs opened Finder at /Users/fanghu/Library/Logs/Ava.
```

## 1. Finder 双击启动

1. 打开 Finder。
2. 进入：

```text
/Users/fanghu/Documents/Test/ava/electron/dist/Ava-darwin-arm64/
```

3. 双击 `Ava.app`。
4. 确认没有 Terminal 窗口弹出，也不需要从 Terminal 启动。
5. 确认以下任一结果：
   - Console 直接加载。
   - `Ava Setup` 短暂出现，等待 sidecar 启动后自动切到 Console。

启动时看到 `Ava Setup` / `Starting Ava core sidecar` 是正常的，它表示正在等待
nanobot sidecar 或 Console health ready。只有在它长期停留并显示错误、且无法进入
Console 时，才不要把 happy-path 字段填为通过。

## 2. Setup Surface 出现在 Console 前

用临时移动 `.venv` 来触发 setup，这是比移动外部 nanobot checkout 更可逆的方式。

1. 退出 `Ava.app`。
2. 临时移走当前 virtualenv：

```bash
cd /Users/fanghu/Documents/Test/ava
if [ -d .venv ] && [ ! -d .venv.visual-check.bak ]; then
  mv .venv .venv.visual-check.bak
fi
```

3. 在 Finder 双击：

```text
/Users/fanghu/Documents/Test/ava/electron/dist/Ava-darwin-arm64/Ava.app
```

4. 确认 `Ava Setup` 先于 Console 出现。
5. 确认窗口上能看到有用状态，例如 stage、Console URL、Nanobot path、logs path、
按钮和 log tail。

短暂的 `Starting Ava core sidecar` 状态可以接受。它要么最终进入 Console，要么被你
故意停留在 setup 状态用于下一步 Cancel/Retry 检查。

## 3. Cancel / Retry

继续使用上一步 `.venv` 被临时移走后的 setup 状态。

1. 在 setup 正在 bootstrap 时点击 `Cancel`。
2. 确认 bootstrap 停止，UI 进入 canceled 或 stopped 状态。
3. 点击 `Retry`。
4. 确认新的 bootstrap attempt 开始，log tail 有更新。
5. 如果不想等 `uv sync` 完成，再点一次 `Cancel`。
6. 退出 `Ava.app`。
7. 恢复原来的 virtualenv：

```bash
cd /Users/fanghu/Documents/Test/ava
if [ -d .venv.visual-check.bak ]; then
  rm -rf .venv
  mv .venv.visual-check.bak .venv
fi
```

检查结束后不要留下 `.venv.visual-check.bak`。

## 4. Help 打开 Logs

1. 再次从 Finder 启动 `Ava.app`。
2. 在 macOS menu bar 选择 `Help -> Open Logs`。
3. 确认 Finder 打开：

```text
/Users/fanghu/Library/Logs/Ava
```

4. 确认目录里能看到 `main.log` 和 `core.log`。

## 可选：Applications / Launchpad

这个检查不是 closeout guard 的必填项，但可以回答“当前新 app 能否从应用抽屉启动”。

1. 通过 Finder 把 app 拷到 `/Applications`，或运行：

```bash
ditto /Users/fanghu/Documents/Test/ava/electron/dist/Ava-darwin-arm64/Ava.app /Applications/Ava.app
```

2. 从 Launchpad 或 `/Applications` 启动 `Ava`。
3. 确认行为和 repo bundle 一致：不需要 Terminal，能出现 setup 或 Console，日志仍写入
`~/Library/Logs/Ava`。

如果同一个包拷到另一台 Mac 后失败，这是预期边界；当前包是绑定本机 repo checkout 的
same-machine build。

## Closeout 回填

四个人工字段确认后：

1. 在下面文件的两条 result record 中填写四个人工字段：

```text
docs/desktop-launch-acceptance.md
```

2. 在 active Task Spec 的两条 result record 中填入完全相同的四个值：

```text
.specanchor/tasks/_cross-module/2026-05-12_electron-headless-launch.spec.md
```

3. 字段填完后，再把 Task Spec 的 pending closeout 文案替换为 accepted result。
4. 运行：

```bash
scripts/verify-desktop-closeout-records.sh
```

期望输出：

```text
Desktop closeout records verified
```
