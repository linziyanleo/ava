# Console Mock Data Contract

## Purpose

This bundle is the repo-backed source of truth for the `mock_tester` runtime.
It is copied into `~/.nanobot/console/mock_data/` and becomes writable there.

## Storage split

- Repo template:
  - `ava/console/mock_bundle/`
- Runtime writable copy:
  - `~/.nanobot/console/mock_data/`
- Local plaintext passwords:
  - `~/.nanobot/console/local-secrets/`

## Entity coverage

### Filesystem-backed

- `config.json`
  - consumer pages: Config, Scheduled Tasks
  - storage: `mock_data/config.json`
- `extra_config.json`
  - consumer pages: future config extension
  - storage: `mock_data/extra_config.json`
- `cron/jobs.json`
  - consumer pages: Scheduled Tasks
  - storage: `mock_data/cron/jobs.json`
- `workspace/memory/**`
  - consumer pages: Memory
  - storage: `mock_data/workspace/memory/**`
- `workspace/diary/**`
  - consumer pages: Memory diary tab
  - storage: `mock_data/workspace/diary/**`
- `workspace/AGENTS.md`, `SOUL.md`, `TOOLS.md`, `USER.md`
  - consumer pages: Persona, Skills docs
  - storage: `mock_data/workspace/*.md`

### Database-backed

- `mock.nanobot.db`
  - schema: same SQLite schema family as `nanobot.db`
  - consumer pages: Media, Token Stats, chat read-only mock coverage

### Media assets

- `media/generated/*.png`
  - consumer pages: Media gallery and image modal
  - storage: `mock_data/media/generated/*.png`

## Required sample states

- Non-empty config sections
- At least 2 cron jobs
- Global memory plus 2 person memories
- At least 2 diary files
- At least 2 media records with different prompt shapes
- At least 2 token usage rows across different model roles
- At least 1 audit row
- At least 3 chat sessions covering plain text, tool-call turn, and subagent summary blocks
- At least 2 active background tasks (`queued` + `running`) and 3 history tasks across different terminal statuses

## Mutation rules

- Repo template is read-only at runtime
- `mock_tester` writes only to `~/.nanobot/console/mock_data/`
- No mock write may touch:
  - real `~/.nanobot/config.json`
  - real `~/.nanobot/nanobot.db`
  - real workspace
  - real media directory

## UI coverage notes

- `Background Tasks` is exposed to `mock_tester` as a mock-safe observation page.
  - It should include seeded `queued` / `running` cards and history rows with different terminal statuses.
- `Chat` is exposed with mock session records from `mock.nanobot.db`.
  - No live agent execution runs under `mock_tester`.
  - Seeded conversations should exercise user media blocks, assistant thinking, `page_agent` / `vision` / `transcribe` / generic / `image_gen` / `claude_code` tool call-result blocks, and subagent summary rendering.
  - Session header and per-turn token entry should be able to drill down into `Token Stats` with `session_key` and `conversation_id`.
