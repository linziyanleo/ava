# Ava

Ava 现在是一个独立仓库，承接从既有 sidecar 代码抽取出来的外挂层实现。

这个仓库不再内嵌 `nanobot/` 源码；运行时通过外部 checkout 接入上游 `nanobot`，默认指向同级目录 `../nanobot`，也支持用 `AVA_NANOBOT_ROOT` 覆盖。

## 目录

- `ava/`: Python 插件层，包含 patches、console、storage、tools、runtime 和 adapter bootstrap
- `console-ui/`: 当前迁移期保留的 Console 前端
- `bridge/`: 当前迁移期保留的 Node bridge
- `tests/`: 以外挂层为中心的单元测试
- `scripts/start-ava.sh`: 用当前仓库代码 + 外部 nanobot checkout 启动 Ava

## 启动

1. 准备外部 `nanobot` checkout
   建议放在当前仓库同级目录，或通过环境变量显式指定
2. 安装当前仓库依赖

```bash
uv sync
```

3. 安装前端依赖

```bash
cd console-ui && npm install
cd ../bridge && npm install
```

4. 启动 Ava

```bash
./scripts/start-ava.sh gateway
```

如果 `nanobot` 不在默认同级目录，先指定：

```bash
AVA_NANOBOT_ROOT=/path/to/nanobot ./scripts/start-ava.sh gateway
```

## 说明

- `python -m ava ...` 现在会先解析外部 `nanobot` checkout，再加载 patches。
- `./scripts/start-ava.sh` 会优先使用当前仓库 `.venv`，其次才回退到外部 `nanobot` 的 `.venv`。
- 当前 repo guardrail 明确禁止再次把 `nanobot` 源码直接放回本仓库根目录。
