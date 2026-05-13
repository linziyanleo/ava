import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const CURL = '/usr/bin/curl';

export function endpoint(host, port) {
  return `http://${host}:${port}`;
}

function curlMaxTime(timeoutMs) {
  return String(Math.max(timeoutMs / 1000, 0.001));
}

function runCurl(args, timeoutMs) {
  return new Promise((resolve, reject) => {
    const result = spawnSync(CURL, args, {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
      timeout: timeoutMs + 500,
    });
    if (result.error) {
      reject(result.error);
      return;
    }
    if (result.status === 0) {
      resolve(result.stdout || '');
      return;
    }
    reject(new Error(`curl failed with ${result.signal || `exit ${result.status}`}: ${result.stderr || result.stdout || ''}`));
  });
}

export async function httpGetJson(url, timeoutMs = 2_000) {
  const body = await runCurl(['-fsS', '--max-time', curlMaxTime(timeoutMs), url], timeoutMs);
  return JSON.parse(body || '{}');
}

export function httpGetStatus(url, timeoutMs = 2_000) {
  return runCurl(['-sS', '-o', '/dev/null', '-w', '%{http_code}', '--max-time', curlMaxTime(timeoutMs), url], timeoutMs)
    .then((status) => Number(status.trim() || 0));
}

export function isHealthyCorePayload(health) {
  return Boolean(
    health
    && typeof health === 'object'
    && health.ready === true
    && health.shutting_down === false
    && Number.isFinite(Number(health.boot_generation)),
  );
}

export async function detectExistingAvaCore(host, port, timeoutMs = 500) {
  const coreEndpoint = endpoint(host, port);
  try {
    const health = await httpGetJson(`${coreEndpoint}/api/gateway/health`, timeoutMs);
    return isHealthyCorePayload(health);
  } catch {
    return false;
  }
}

export function normalizeClientHost(host) {
  return host === '0.0.0.0' || host === '::' ? '127.0.0.1' : host;
}

export function consoleMetaPath({ env = process.env, homeDir = os.homedir() } = {}) {
  const avaHome = env.AVA_HOME || path.join(homeDir, '.ava');
  return path.join(avaHome, 'console.json');
}

export function readConsoleMetaCandidate(options = {}) {
  const metaPath = consoleMetaPath(options);
  if (!fs.existsSync(metaPath)) {
    return null;
  }
  let parsed = null;
  try {
    parsed = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
  } catch {
    return null;
  }
  const port = Number(parsed?.console_port);
  if (!Number.isInteger(port) || port <= 0) {
    return null;
  }
  const host = typeof parsed?.console_host === 'string' && parsed.console_host
    ? normalizeClientHost(parsed.console_host)
    : '127.0.0.1';
  return { host, port };
}

export async function resolveExistingAvaCore(preferredHost, preferredPort, options = {}) {
  const candidates = [
    { host: preferredHost, port: preferredPort },
    readConsoleMetaCandidate(options),
  ].filter(Boolean);
  const seen = new Set();
  for (const candidate of candidates) {
    const key = `${candidate.host}:${candidate.port}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    if (await detectExistingAvaCore(candidate.host, candidate.port, options.timeoutMs ?? 500)) {
      return candidate;
    }
  }
  return null;
}
