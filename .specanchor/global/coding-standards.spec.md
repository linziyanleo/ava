---
specanchor:
  level: global
  type: coding-standards
  version: "0.1.0"
  author: "fanghu"
  reviewers: []
  last_synced: "2026-04-13"
  last_change: "补充迁移期规范：避免过早固化 module spec，先稳住 core 与 adapter 边界"
  applies_to: "**/*"
---

# 编码规范

## 通用要求
- 文档与注释优先使用中文
- 代码标识符保持英文
- 增量迁移时优先保行为稳定，再做抽象收口

## 迁移约束
- 旧路径迁移优先使用 compatibility shim，避免一次性搬迁导致入口与测试全部失效
- 任何涉及 prompt、memory、bootstrap、console 的改动，都需要明确说明是否影响当前行为契约
- 迁移期避免 repo-wide 噪音改动，优先小步、可验证的结构调整
- 在 `ava.core` 与 `ava.adapters` 边界未稳定前，不预写实现级 Module Spec

## 验证要求
- 新增或迁移代码优先补窄测试
- adapter 行为至少覆盖：
  - launcher / patch apply
  - console 启动
  - commands / skills / bootstrap
  - onboard 兼容
