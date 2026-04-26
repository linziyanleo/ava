# Ava Runtime Quick Start

`ava/` 是当前仓库里的 Python 外挂层。

和旧的 sidecar 形态相比，现在最大的变化是：

- 当前仓库只维护 Ava 自己的代码
- 上游 `nanobot` 通过外部 checkout 提供
- 默认外部路径是仓库同级的 `../nanobot`
- 也可以通过 `AVA_NANOBOT_ROOT` 指向任意完整的 `nanobot` checkout

## 推荐入口

优先使用仓库根目录脚本：

```bash
./scripts/start-ava.sh gateway
```

它会自动：

1. 解析外部 `nanobot` checkout
2. 设置 `PYTHONPATH`
3. 选择可用 Python
4. 执行 `python -m ava ...`

如果你已经在正确环境中，也可以直接运行：

```bash
python -m ava gateway
python -m ava onboard
python -m ava agent -m "Hello"
```

## 依赖约束

当前运行需要两部分同时存在：

- 当前仓库的 Ava 代码与依赖
- 一个完整的外部 `nanobot` 源码 checkout

只装 Ava、不提供外部 `nanobot` checkout，不足以运行。

## 入口差异

| 入口 | 行为 |
| --- | --- |
| `nanobot ...` | 直接进入上游 CLI，不会应用 Ava patches |
| `python -m ava ...` | 先解析外部 nanobot checkout，再应用 `ava/patches/*`，最后进入上游 CLI |
| `./scripts/start-ava.sh ...` | 对 `python -m ava ...` 再包一层环境解析，适合作为本地开发默认入口 |

## Console / Mock 数据

- repo 内版本化数据仍在 `ava/console/mock_bundle/`
- Ava 运行时默认 home 已迁到 `~/.ava/`，可通过 `AVA_HOME=/custom/path` 覆盖
- 老用户如果仍只有 `~/.nanobot/`，首次启动会提示先执行 `ava migrate-home`
- 临时兼容旧 home 可用 `ava --legacy-home ...` 或设置 `AVA_LEGACY_HOME=1`
- Console 和 gateway 的联动行为保持原契约，不因为仓库抽取而改成双进程分叉实现

## Home 迁移

```bash
ava migrate-home --dry-run
ava migrate-home
```

- `--dry-run` 只预览迁移项，不落盘
- `--mode copy|move|symlink` 控制迁移策略，默认 `copy`
- `--rollback` 会把当前 `AVA_HOME` 下的数据迁回 legacy `~/.nanobot/`
