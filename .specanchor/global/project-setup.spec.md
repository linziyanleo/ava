---
specanchor:
  level: global
  type: project-setup
  version: "0.1.0"
  author: "fanghu"
  reviewers: []
  last_synced: "2026-04-13"
  last_change: "收紧项目定位：仓库名统一为 ava，目标改为多 Agent 记忆系统适配，不预写 module spec"
  applies_to: "**/*"
---

# 项目设置约定

## 项目定位
- 本仓库名称为 `ava`
- Ava 的长期目标是适配多种 agent 的记忆管理系统，而不是绑定单一运行时
- 当前迁移来源是 `nanobot__ava`，但 `nanobot` 只是首个 reference adapter，不是 Ava 的唯一宿主

## 当前初始化状态
- Git 仓库已初始化
- SpecAnchor 已启用 full 模式
- 当前以 Global Spec + Task Spec 驱动迁移
- 实现级 Module Spec 暂缓，等待核心边界稳定后再补

## 目录约定
- `ava/`: Ava 代码主目录
- `console-ui/`: 当前迁移期保留的 Console 前端
- `bridge/`: 当前迁移期保留的桥接层
- `tests/`: 测试
- `.specanchor/`: SpecAnchor 规范体系
