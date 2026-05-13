import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const SHELL_PATH_TIMEOUT_MS = 1_500;

export function splitPath(value) {
  return String(value || '')
    .split(path.delimiter)
    .map((segment) => segment.trim())
    .filter(Boolean);
}

export function readLoginShellPath(env, { timeoutMs = SHELL_PATH_TIMEOUT_MS } = {}) {
  const shellPath = env.SHELL || '/bin/zsh';
  if (!path.isAbsolute(shellPath) || !fs.existsSync(shellPath)) {
    return '';
  }
  const result = spawnSync(shellPath, ['-lc', 'printf %s "$PATH"'], {
    encoding: 'utf8',
    env,
    timeout: timeoutMs,
    stdio: ['ignore', 'pipe', 'ignore'],
  });
  if (result.status !== 0 || !result.stdout) {
    return '';
  }
  const lines = result.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  return lines[lines.length - 1] || '';
}

export function desktopPathDefaults(homeDir = os.homedir()) {
  return [
    '/opt/homebrew/bin',
    '/usr/local/bin',
    path.join(homeDir, '.local', 'bin'),
    path.join(homeDir, '.cargo', 'bin'),
    path.join(homeDir, '.pyenv', 'shims'),
    path.join(homeDir, '.real', '.bin'),
    '/usr/bin',
    '/bin',
    '/usr/sbin',
    '/sbin',
  ];
}

export function resolveLaunchPath(env = process.env, options = {}) {
  const homeDir = options.homeDir || os.homedir();
  const merged = [];
  for (const segment of [
    ...splitPath(readLoginShellPath(env, options)),
    ...splitPath(env.PATH),
    ...desktopPathDefaults(homeDir),
  ]) {
    if (!merged.includes(segment)) {
      merged.push(segment);
    }
  }
  return {
    ...env,
    PATH: merged.join(path.delimiter),
  };
}

export function findExecutable(command, env) {
  for (const dir of splitPath(env.PATH)) {
    const candidate = path.join(dir, command);
    if (fs.existsSync(candidate)) {
      try {
        fs.accessSync(candidate, fs.constants.X_OK);
        return candidate;
      } catch {
        continue;
      }
    }
  }
  return null;
}

export function venvSitePackages(repoRoot, pythonExecutable = '') {
  const match = path.basename(pythonExecutable).match(/^python(\d+\.\d+)$/);
  if (!match) {
    return '';
  }
  return path.join(repoRoot, '.venv', 'lib', `python${match[1]}`, 'site-packages');
}

export function buildCoreEnv(config, nanobotRoot) {
  const pythonPath = [config.repoRoot, nanobotRoot, venvSitePackages(config.repoRoot, config.pythonExecutable), config.env.PYTHONPATH]
    .filter(Boolean)
    .join(path.delimiter);
  const env = {
    ...config.env,
    AVA_DESKTOP: '1',
    AVA_REPO_ROOT: config.repoRoot,
    AVA_NANOBOT_ROOT: nanobotRoot,
    VIRTUAL_ENV: path.join(config.repoRoot, '.venv'),
    PYTHONPATH: pythonPath,
    CAFE_CONSOLE_HOST: config.host,
    CAFE_CONSOLE_PORT: String(config.port),
    AVA_DESKTOP_CONSOLE_HOST: config.host,
    AVA_DESKTOP_CONSOLE_PORT: String(config.port),
  };
  if (Number.isInteger(config.gatewayPort)) {
    env.AVA_DESKTOP_GATEWAY_PORT = String(config.gatewayPort);
  }
  if (Number.isInteger(config.websocketPort)) {
    env.AVA_DESKTOP_WEBSOCKET_PORT = String(config.websocketPort);
  }
  return env;
}
