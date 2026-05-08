import { app, BrowserWindow, Notification, dialog, ipcMain, shell } from 'electron';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_CONSOLE_PORT = 6688;
const CORE_HEALTH_TIMEOUT_MS = 45_000;

let mainWindow = null;
let avaCoreProcess = null;
let allowQuit = false;

function findRepoRoot() {
  if (process.env.AVA_REPO_ROOT) {
    return path.resolve(process.env.AVA_REPO_ROOT);
  }

  const starts = [__dirname, process.cwd(), app.getAppPath()];
  for (const start of starts) {
    let current = path.resolve(start);
    for (let depth = 0; depth < 10; depth += 1) {
      if (fs.existsSync(path.join(current, 'scripts', 'start-ava.sh'))) {
        return current;
      }
      const parent = path.dirname(current);
      if (parent === current) {
        break;
      }
      current = parent;
    }
  }
  return path.resolve(__dirname, '..');
}

function getAvaConfig() {
  const repoRoot = findRepoRoot();
  const port = Number(process.env.AVA_DESKTOP_CONSOLE_PORT || process.env.CAFE_CONSOLE_PORT || DEFAULT_CONSOLE_PORT);
  const host = process.env.AVA_DESKTOP_CONSOLE_HOST || '127.0.0.1';
  const coreEndpoint = `http://${host}:${port}`;
  return {
    repoRoot,
    port,
    host,
    coreEndpoint,
    healthEndpoint: `${coreEndpoint}/api/gateway/health`,
  };
}

function httpGetJson(url, timeoutMs = 2_000) {
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

async function waitForAvaCore(healthEndpoint) {
  const deadline = Date.now() + CORE_HEALTH_TIMEOUT_MS;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      return await httpGetJson(healthEndpoint);
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  throw lastError || new Error('ava-core healthcheck timed out');
}

function startAvaCore() {
  if (avaCoreProcess) {
    return;
  }
  const config = getAvaConfig();
  const wrapper = path.join(config.repoRoot, 'electron', 'bin', 'ava-core');
  avaCoreProcess = spawn('/bin/bash', [wrapper], {
    cwd: config.repoRoot,
    env: {
      ...process.env,
      AVA_DESKTOP: '1',
      AVA_REPO_ROOT: config.repoRoot,
      CAFE_CONSOLE_HOST: config.host,
      CAFE_CONSOLE_PORT: String(config.port),
    },
    stdio: 'inherit',
  });
  avaCoreProcess.once('exit', () => {
    avaCoreProcess = null;
  });
}

function stopAvaCore() {
  if (!avaCoreProcess) {
    return Promise.resolve();
  }
  const child = avaCoreProcess;
  return new Promise((resolve) => {
    const timeout = setTimeout(() => {
      if (!child.killed) {
        child.kill('SIGKILL');
      }
      resolve();
    }, 5_000);
    child.once('exit', () => {
      clearTimeout(timeout);
      resolve();
    });
    child.kill('SIGTERM');
  });
}

function createWindow() {
  const config = getAvaConfig();
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 680,
    title: 'Ava',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.loadURL(config.coreEndpoint);
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

ipcMain.handle('ava:getAppConfig', () => getAvaConfig());
ipcMain.handle('ava:getCoreEndpoint', () => getAvaConfig().coreEndpoint);
ipcMain.handle('ava:getAuthToken', () => null);
ipcMain.handle('ava:selectDirectory', async () => {
  const result = await dialog.showOpenDialog({ properties: ['openDirectory'] });
  return result.canceled ? null : result.filePaths[0] || null;
});
ipcMain.handle('ava:openPath', async (_event, targetPath) => {
  if (typeof targetPath !== 'string' || targetPath.length === 0) {
    return { ok: false, error: 'invalid path' };
  }
  const error = await shell.openPath(targetPath);
  return { ok: error.length === 0, error };
});
ipcMain.handle('ava:showNotification', (_event, payload) => {
  const title = typeof payload?.title === 'string' ? payload.title : 'Ava';
  const body = typeof payload?.body === 'string' ? payload.body : '';
  if (Notification.isSupported()) {
    new Notification({ title, body }).show();
  }
  return { ok: true };
});

app.whenReady().then(async () => {
  const config = getAvaConfig();
  startAvaCore();
  await waitForAvaCore(config.healthEndpoint);
  createWindow();
});

app.on('window-all-closed', () => {
  app.quit();
});

app.on('before-quit', async (event) => {
  if (allowQuit) {
    return;
  }
  event.preventDefault();
  allowQuit = true;
  await stopAvaCore();
  app.quit();
});
