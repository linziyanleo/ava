import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';

export function endpoint(host, port) {
  return `http://${host}:${port}`;
}

export function httpGetJson(url, timeoutMs = 2_000) {
  return new Promise((resolve, reject) => {
    const request = http.get(url, { timeout: timeoutMs }, (response) => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', (chunk) => {
        body += chunk;
      });
      response.on('end', () => {
        if (!response.statusCode || response.statusCode >= 400) {
          reject(new Error(`healthcheck ${response.statusCode || 'unknown'}`));
          return;
        }
        try {
          resolve(JSON.parse(body || '{}'));
        } catch (error) {
          reject(error);
        }
      });
    });
    request.on('timeout', () => {
      request.destroy(new Error('healthcheck timeout'));
    });
    request.on('error', reject);
  });
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
