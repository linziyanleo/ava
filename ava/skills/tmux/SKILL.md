---
name: tmux
description: >
  Remote-control tmux sessions for interactive TTY scenarios: sending keystrokes, scraping pane output, running interactive REPLs.
  Prefer BackgroundTaskStore-backed coding tools over tmux for agent orchestration.
metadata: {"nanobot":{"emoji":"🧵","os":["darwin","linux"],"requires":{"bins":["tmux"]}}}
---

# tmux Skill

Use tmux only when you need an interactive TTY or direct terminal control.
For coding tasks, prefer `claude_code` / `codex` tools via BackgroundTaskStore.
For non-interactive long-running tasks, prefer `exec` background mode.

## Quickstart (isolated socket, exec tool)

```bash
SOCKET_DIR="${NANOBOT_TMUX_SOCKET_DIR:-${TMPDIR:-/tmp}/nanobot-tmux-sockets}"
mkdir -p "$SOCKET_DIR"
SOCKET="$SOCKET_DIR/nanobot.sock"
SESSION=nanobot-python

tmux -S "$SOCKET" new -d -s "$SESSION" -n shell
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -- 'PYTHON_BASIC_REPL=1 python3 -q' Enter
tmux -S "$SOCKET" capture-pane -p -J -t "$SESSION":0.0 -S -200
```

After starting a session, always print monitor commands:

```
To monitor:
  tmux -S "$SOCKET" attach -t "$SESSION"
  tmux -S "$SOCKET" capture-pane -p -J -t "$SESSION":0.0 -S -200
```

## Socket convention

- Use `NANOBOT_TMUX_SOCKET_DIR` environment variable.
- Default socket path: `"$NANOBOT_TMUX_SOCKET_DIR/nanobot.sock"`.

## Targeting panes and naming

- Target format: `session:window.pane` (defaults to `:0.0`).
- Keep names short; avoid spaces.
- Inspect: `tmux -S "$SOCKET" list-sessions`, `tmux -S "$SOCKET" list-panes -a`.

## Finding sessions

- List sessions on your socket: `{baseDir}/scripts/find-sessions.sh -S "$SOCKET"`.
- Scan all sockets: `{baseDir}/scripts/find-sessions.sh --all` (uses `NANOBOT_TMUX_SOCKET_DIR`).

## Sending input safely

- Prefer literal sends: `tmux -S "$SOCKET" send-keys -t target -l -- "$cmd"`.
- Control keys: `tmux -S "$SOCKET" send-keys -t target C-c`.

## Watching output

- Capture recent history: `tmux -S "$SOCKET" capture-pane -p -J -t target -S -200`.
- Wait for prompts: `{baseDir}/scripts/wait-for-text.sh -t session:0.0 -p 'pattern'`.
- Attaching is OK; detach with `Ctrl+b d`.

## Spawning processes

- For python REPLs, set `PYTHON_BASIC_REPL=1` (non-basic REPL breaks send-keys flows).

## Windows / WSL

- tmux is supported on macOS/Linux. On Windows, use WSL and install tmux inside WSL.
- This skill is gated to `darwin`/`linux` and requires `tmux` on PATH.

## Coding Agent Boundary

Preferred path: use `claude_code` or `codex` directly. They already integrate with BackgroundTaskStore for lifecycle, result persistence, and status queries.

Use tmux for coding-agent orchestration only as a fallback when:

- BackgroundTaskStore is unavailable
- You need interactive control such as `Ctrl+C` or live pane inspection
- You explicitly need tmux multi-window visualization

Fallback example:

```bash
SOCKET="${TMPDIR:-/tmp}/codex-army.sock"

tmux -S "$SOCKET" new-session -d -s "agent-1"
tmux -S "$SOCKET" new-session -d -s "agent-2"

tmux -S "$SOCKET" send-keys -t agent-1 "cd /tmp/project1 && codex --full-auto 'Fix bug X'" Enter
tmux -S "$SOCKET" send-keys -t agent-2 "cd /tmp/project2 && codex --full-auto 'Fix bug Y'" Enter

# Poll for completion by checking whether the shell prompt returned.
for sess in agent-1 agent-2; do
  if tmux -S "$SOCKET" capture-pane -p -t "$sess" -S -3 | grep -q "❯"; then
    echo "$sess: DONE"
  else
    echo "$sess: Running..."
  fi
done
```

Tips:
- Use separate git worktrees to avoid branch conflicts
- Use `--full-auto` for non-interactive Codex runs
- Detect completion from the shell prompt (`❯` or `$`)

## Cleanup

- Kill a session: `tmux -S "$SOCKET" kill-session -t "$SESSION"`.
- Kill all sessions on a socket: `tmux -S "$SOCKET" list-sessions -F '#{session_name}' | xargs -r -n1 tmux -S "$SOCKET" kill-session -t`.
- Remove everything on the private socket: `tmux -S "$SOCKET" kill-server`.

## Helper: wait-for-text.sh

`{baseDir}/scripts/wait-for-text.sh` polls a pane for a regex (or fixed string) with a timeout.

```bash
{baseDir}/scripts/wait-for-text.sh -t session:0.0 -p 'pattern' [-F] [-T 20] [-i 0.5] [-l 2000]
```

- `-t`/`--target` pane target (required)
- `-p`/`--pattern` regex to match (required); add `-F` for fixed string
- `-T` timeout seconds (integer, default 15)
- `-i` poll interval seconds (default 0.5)
- `-l` history lines to search (integer, default 1000)
