import {
  app,
  BrowserWindow,
  Menu,
  Notification,
  dialog,
  ipcMain,
  shell,
} from 'electron';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  readDesktopConfig as readStoredDesktopConfig,
  resolveNanobotCandidate as resolveStoredNanobotCandidate,
  saveNanobotRoot,
  validateNanobotRoot,
} from './lib/desktop-config.mjs';
import {
  endpoint,
  httpGetJson,
  isHealthyCorePayload,
  resolveExistingAvaCore,
} from './lib/core-health.mjs';
import {
  buildCoreEnv,
  findExecutable,
  resolveLaunchPath,
} from './lib/launch-env.mjs';
import { pickFreePort } from './lib/ports.mjs';
import {
  isAvaRepoRoot,
  readRuntimeManifestRepoRoot,
  runtimeManifestPaths,
} from './lib/runtime-manifest.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_CONSOLE_PORT = 6688;
const CORE_HEALTH_TIMEOUT_MS = 45_000;
const SETUP_LOAD_TIMEOUT_MS = 5_000;
const LOG_ROTATE_BYTES = 1024 * 1024;
const RING_BUFFER_BYTES = 256 * 1024;

let mainWindow = null;
let avaCoreProcess = null;
let activeBootstrapProcess = null;
let allowQuit = false;
let launchConfigPromise = null;
let launchConfig = null;
let startupPromise = null;
let consoleLoadPromise = null;
let consoleLoaded = false;
let consoleReadyWatcher = null;
let logs = null;
let stderrTail = '';
let bootstrapTail = '';
let bootstrapState = {
  stage: 'starting',
  message: 'Preparing Ava desktop runtime',
  error: '',
  stderrTail: '',
  logDir: '',
  nanobotRoot: '',
  coreEndpoint: '',
};

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
}

function makeStartupError(code, message, detail = '') {
  const error = new Error(message);
  error.code = code;
  error.detail = detail;
  return error;
}

function findRepoRoot() {
  if (process.env.AVA_REPO_ROOT) {
    const explicitRoot = path.resolve(process.env.AVA_REPO_ROOT);
    return isAvaRepoRoot(explicitRoot) ? explicitRoot : null;
  }

  const starts = [__dirname, process.cwd(), app.getAppPath()];
  for (const start of starts) {
    let current = path.resolve(start);
    for (let depth = 0; depth < 10; depth += 1) {
      if (isAvaRepoRoot(current)) {
        return current;
      }
      const parent = path.dirname(current);
      if (parent === current) {
        break;
      }
      current = parent;
    }
  }
  return readRuntimeManifestRepoRoot(runtimeManifestPaths(__dirname));
}

function publicConfig(config = launchConfig) {
  const current = config || {
    repoRoot: findRepoRoot() || path.resolve(__dirname, '..'),
    repoRootFound: Boolean(findRepoRoot()),
    host: process.env.AVA_DESKTOP_CONSOLE_HOST || '127.0.0.1',
    port: Number(process.env.AVA_DESKTOP_CONSOLE_PORT || process.env.CAFE_CONSOLE_PORT || DEFAULT_CONSOLE_PORT),
    logDir: logs?.logDir || '',
    externalCore: false,
  };
  const coreEndpoint = endpoint(current.host, current.port);
  return {
    repoRoot: current.repoRoot,
    repoRootFound: current.repoRootFound,
    host: current.host,
    port: current.port,
    coreEndpoint,
    healthEndpoint: `${coreEndpoint}/api/gateway/health`,
    logDir: current.logDir || '',
    externalCore: Boolean(current.externalCore),
  };
}

function getAvaConfig() {
  return publicConfig();
}

function rotateLogFile(logPath) {
  try {
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    if (fs.existsSync(logPath)) {
      const backupPath = `${logPath}.1`;
      const stat = fs.statSync(logPath);
      if (stat.size > LOG_ROTATE_BYTES) {
        if (fs.existsSync(backupPath)) {
          fs.unlinkSync(backupPath);
        }
        fs.renameSync(logPath, backupPath);
      } else {
        fs.unlinkSync(logPath);
      }
    }
  } catch (error) {
    throw makeStartupError('log_setup_failed', `Failed to prepare log file: ${logPath}`, String(error));
  }
}

function setupLogging() {
  if (logs) {
    return logs;
  }
  const logDir = path.join(os.homedir(), 'Library', 'Logs', 'Ava');
  const mainLogPath = path.join(logDir, 'main.log');
  const coreLogPath = path.join(logDir, 'core.log');
  for (const logPath of [mainLogPath, coreLogPath]) {
    rotateLogFile(logPath);
  }
  logs = {
    logDir,
    mainLogPath,
    coreLogPath,
    mainStream: fs.createWriteStream(mainLogPath, { flags: 'a' }),
    coreStream: fs.createWriteStream(coreLogPath, { flags: 'a' }),
  };
  logs.mainStream.write(`[${new Date().toISOString()}] Ava desktop launch\n`);
  return logs;
}

function writeMainLog(message) {
  logs?.mainStream.write(`[${new Date().toISOString()}] ${message}\n`);
}

function appendRingBuffer(buffer, chunk, maxBytes = RING_BUFFER_BYTES) {
  const next = Buffer.concat([Buffer.from(buffer || '', 'utf8'), Buffer.from(chunk)]);
  if (next.length <= maxBytes) {
    return next.toString('utf8');
  }
  return next.subarray(next.length - maxBytes).toString('utf8');
}

function readDesktopConfig() {
  return readStoredDesktopConfig(app.getPath('appData'));
}

function resolveNanobotCandidate(config) {
  return resolveStoredNanobotCandidate({
    repoRoot: config.repoRoot,
    appDataPath: app.getPath('appData'),
    env: process.env,
  });
}

function setNanobotRoot(root) {
  const saved = saveNanobotRoot(app.getPath('appData'), root);
  if (!saved.ok) {
    return { ok: false, error: saved.error };
  }
  sendBootstrapState({ nanobotRoot: saved.nanobotRoot, error: '' });
  return { ok: true };
}

function ensureNanobotRoot(config) {
  const nanobotRoot = resolveNanobotCandidate(config);
  const validation = validateNanobotRoot(nanobotRoot);
  if (!validation.ok) {
    sendBootstrapState({
      stage: 'nanobot',
      message: 'Select a nanobot checkout to continue.',
      nanobotRoot,
      error: validation.error,
    });
    throw makeStartupError(
      'nanobot_not_found',
      `nanobot checkout not found: ${nanobotRoot}`,
      validation.error,
    );
  }
  sendBootstrapState({ nanobotRoot, error: '' });
  return nanobotRoot;
}

async function createLaunchConfig() {
  if (launchConfigPromise) {
    return launchConfigPromise;
  }
  launchConfigPromise = (async () => {
    setupLogging();
    const detectedRepoRoot = findRepoRoot();
    const repoRoot = detectedRepoRoot || path.resolve(__dirname, '..');
    const host = process.env.AVA_DESKTOP_CONSOLE_HOST || '127.0.0.1';
    const preferredPort = Number(process.env.AVA_DESKTOP_CONSOLE_PORT || process.env.CAFE_CONSOLE_PORT || DEFAULT_CONSOLE_PORT);
    const existingCore = await resolveExistingAvaCore(host, preferredPort);
    const externalCore = Boolean(existingCore);
    const port = existingCore?.port || await pickFreePort(preferredPort);
    const launchHost = existingCore?.host || host;
    const coreEndpoint = endpoint(launchHost, port);
    const config = {
      repoRoot,
      repoRootFound: Boolean(detectedRepoRoot),
      host: launchHost,
      port,
      externalCore,
      coreEndpoint,
      healthEndpoint: `${coreEndpoint}/api/gateway/health`,
      logDir: logs.logDir,
      mainLogPath: logs.mainLogPath,
      coreLogPath: logs.coreLogPath,
      env: resolveLaunchPath(process.env),
    };
    writeMainLog(
      `launch config repoRootFound=${config.repoRootFound} externalCore=${config.externalCore} coreEndpoint=${config.coreEndpoint}`,
    );
    if (externalCore) {
      writeMainLog(`reusing existing Ava core at ${coreEndpoint}`);
    }
    launchConfig = Object.freeze(config);
    return launchConfig;
  })();
  return launchConfigPromise;
}

function sendBootstrapState(partial) {
  const nextTail = partial.stderrTail ?? (stderrTail || bootstrapTail);
  bootstrapState = {
    ...bootstrapState,
    ...partial,
    stderrTail: nextTail,
    logDir: logs?.logDir || bootstrapState.logDir,
    coreEndpoint: launchConfig?.coreEndpoint || bootstrapState.coreEndpoint,
  };
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('ava:bootstrapState', bootstrapState);
  }
}

function createBootstrapWindow(config) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    return mainWindow;
  }
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
  const setupLoadTimeout = setTimeout(() => {
    dialog.showErrorBox('Ava setup failed to load', `Setup surface did not finish loading.\nLogs: ${config.logDir}`);
  }, SETUP_LOAD_TIMEOUT_MS);
  mainWindow.on('closed', () => {
    clearTimeout(setupLoadTimeout);
    mainWindow = null;
  });
  mainWindow.webContents.once('did-finish-load', () => {
    clearTimeout(setupLoadTimeout);
  });
  mainWindow.webContents.once('did-fail-load', (_event, _errorCode, errorDescription) => {
    clearTimeout(setupLoadTimeout);
    dialog.showErrorBox('Ava setup failed to load', `${errorDescription}\nLogs: ${config.logDir}`);
  });
  mainWindow.loadFile(path.join(__dirname, 'setup.html')).catch((error) => {
    clearTimeout(setupLoadTimeout);
    dialog.showErrorBox('Ava setup failed to load', `${String(error)}\nLogs: ${config.logDir}`);
  });
  setTimeout(() => sendBootstrapState({}), 250);
  return mainWindow;
}

async function waitForAvaCore(healthEndpoint) {
  const deadline = Date.now() + CORE_HEALTH_TIMEOUT_MS;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const health = await httpGetJson(healthEndpoint);
      if (isHealthyCorePayload(health)) {
        return health;
      }
      lastError = new Error('ava-core healthcheck is not ready');
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw lastError || new Error('ava-core healthcheck timed out');
}

function stopConsoleReadyWatcher() {
  if (consoleReadyWatcher) {
    clearTimeout(consoleReadyWatcher);
    consoleReadyWatcher = null;
  }
}

async function loadConsole(config, reason) {
  if (consoleLoaded) {
    return;
  }
  if (consoleLoadPromise) {
    return consoleLoadPromise;
  }
  if (!mainWindow || mainWindow.isDestroyed()) {
    throw makeStartupError('console_window_missing', 'Ava window closed before Console could load');
  }

  consoleLoadPromise = (async () => {
    stopConsoleReadyWatcher();
    sendBootstrapState({
      stage: 'ready',
      message: 'Ava core is ready',
      error: '',
    });
    writeMainLog(`loading Console from ${config.coreEndpoint} (${reason})`);
    await mainWindow.loadURL(config.coreEndpoint);
    consoleLoaded = true;
    writeMainLog(`Console loaded from ${config.coreEndpoint} (${reason})`);
  })();

  try {
    await consoleLoadPromise;
  } finally {
    if (!consoleLoaded) {
      consoleLoadPromise = null;
    }
  }
}

function startConsoleReadyWatcher(config) {
  if (consoleReadyWatcher || consoleLoaded) {
    return;
  }

  const poll = async () => {
    consoleReadyWatcher = null;
    if (!mainWindow || mainWindow.isDestroyed() || consoleLoaded) {
      return;
    }
    try {
      const health = await httpGetJson(config.healthEndpoint, 1_000);
      if (isHealthyCorePayload(health)) {
        await loadConsole(config, 'health watcher');
        return;
      }
    } catch {
      // Keep waiting; the main startup path owns the visible failure after timeout.
    }
    if (!consoleLoaded) {
      consoleReadyWatcher = setTimeout(poll, 500);
      consoleReadyWatcher.unref?.();
    }
  };

  consoleReadyWatcher = setTimeout(poll, 500);
  consoleReadyWatcher.unref?.();
}

async function ensureVenvBootstrapped(config) {
  const pythonPath = path.join(config.repoRoot, '.venv', 'bin', 'python');
  if (fs.existsSync(pythonPath)) {
    return;
  }
  const uvPath = findExecutable('uv', config.env);
  if (!uvPath) {
    throw makeStartupError('uv_not_found', 'uv not found in desktop launch PATH', config.env.PATH);
  }

  sendBootstrapState({
    stage: 'venv',
    message: 'Creating Ava Python environment',
    error: '',
    stderrTail: '',
  });

  await new Promise((resolve, reject) => {
    const child = spawn(uvPath, ['sync', '--extra', 'dev'], {
      cwd: config.repoRoot,
      env: config.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    activeBootstrapProcess = { child, cancelRequested: false };

    const onData = (chunk) => {
      bootstrapTail = appendRingBuffer(bootstrapTail, chunk);
      logs.mainStream.write(chunk);
      sendBootstrapState({ stderrTail: bootstrapTail });
    };
    child.stdout.on('data', onData);
    child.stderr.on('data', onData);
    child.once('error', (error) => {
      activeBootstrapProcess = null;
      reject(makeStartupError('venv_bootstrap_spawn_failed', 'Failed to start uv sync', String(error)));
    });
    child.once('exit', (code, signal) => {
      const wasCanceled = activeBootstrapProcess?.cancelRequested;
      activeBootstrapProcess = null;
      if (wasCanceled) {
        reject(makeStartupError('bootstrap_canceled', 'Python environment bootstrap canceled'));
        return;
      }
      if (code === 0) {
        resolve();
        return;
      }
      reject(makeStartupError('venv_bootstrap_failed', `uv sync failed with ${signal || `exit ${code}`}`, bootstrapTail));
    });
  });
  if (!fs.existsSync(pythonPath)) {
    throw makeStartupError('venv_bootstrap_incomplete', 'uv sync finished but .venv/bin/python was not created', bootstrapTail);
  }
}

function startAvaCore(config, nanobotRoot) {
  if (avaCoreProcess) {
    return avaCoreProcess;
  }
  const wrapper = path.join(config.repoRoot, 'electron', 'bin', 'ava-core');
  if (!fs.existsSync(wrapper)) {
    throw makeStartupError('wrapper_not_found', `ava-core wrapper not found: ${wrapper}`);
  }

  const env = buildCoreEnv(config, nanobotRoot);
  const child = spawn('/bin/bash', [wrapper], {
    cwd: config.repoRoot,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  avaCoreProcess = child;
  child.stdout.on('data', (chunk) => {
    logs.coreStream.write(chunk);
  });
  child.stderr.on('data', (chunk) => {
    stderrTail = appendRingBuffer(stderrTail, chunk);
    logs.coreStream.write(chunk);
    sendBootstrapState({ stderrTail });
  });
  child.once('exit', (code, signal) => {
    writeMainLog(`ava-core exited code=${code ?? ''} signal=${signal ?? ''}`);
    if (avaCoreProcess === child) {
      avaCoreProcess = null;
    }
  });
  return child;
}

function parseStructuredStartupError(output) {
  const firstLine = String(output || '').split(/\r?\n/).find((line) => line.trim().startsWith('{'));
  if (!firstLine) {
    return null;
  }
  try {
    const parsed = JSON.parse(firstLine);
    if (!parsed || typeof parsed !== 'object' || typeof parsed.error !== 'string') {
      return null;
    }
    return makeStartupError(
      parsed.error,
      typeof parsed.message === 'string' ? parsed.message : parsed.error,
      output,
    );
  } catch {
    return null;
  }
}

function waitForAvaCoreOrExit(child, config) {
  return Promise.race([
    waitForAvaCore(config.healthEndpoint),
    new Promise((_, reject) => {
      child.once('error', (error) => {
        reject(makeStartupError('sidecar_spawn_failed', 'Failed to start ava-core sidecar', String(error)));
      });
      child.once('exit', (code, signal) => {
        reject(
          parseStructuredStartupError(stderrTail)
          || makeStartupError('sidecar_exited', `ava-core exited before becoming healthy (${signal || `exit ${code}`})`, stderrTail),
        );
      });
    }),
  ]);
}

async function openLogs() {
  setupLogging();
  const error = await shell.openPath(logs.logDir);
  return { ok: error.length === 0, error };
}

async function showStartupError(reason, logPath, tail) {
  const detailParts = [];
  if (reason.detail) {
    detailParts.push(String(reason.detail));
  }
  if (tail) {
    detailParts.push(tail);
  }
  detailParts.push(`Logs: ${logPath}`);
  const options = {
    type: 'error',
    title: 'Ava startup failed',
    message: reason.message,
    detail: detailParts.join('\n\n').slice(0, RING_BUFFER_BYTES),
    buttons: ['Retry', 'Pick nanobot', 'Open logs', 'Quit'],
    defaultId: 0,
    cancelId: 3,
    noLink: true,
  };
  const result = mainWindow
    ? await dialog.showMessageBox(mainWindow, options)
    : await dialog.showMessageBox(options);
  return ['retry', 'pickNanobot', 'openLogs', 'quit'][result.response] || 'quit';
}

function showFatalStartupError(error) {
  const reason = error instanceof Error ? error : makeStartupError('startup_failed', String(error));
  let loggingDetail = '';
  try {
    setupLogging();
    writeMainLog(`fatal startup failed ${reason.code || ''}: ${reason.message}`);
  } catch (loggingError) {
    loggingDetail = `Log setup also failed: ${String(loggingError)}`;
  }

  const logPath = logs?.mainLogPath || path.join(os.homedir(), 'Library', 'Logs', 'Ava', 'main.log');
  const detail = [reason.detail, loggingDetail, `Logs: ${logPath}`].filter(Boolean).join('\n\n');
  dialog.showErrorBox('Ava startup failed', `${reason.message}\n\n${detail}`.slice(0, RING_BUFFER_BYTES));
  app.quit();
}

async function pickNanobotRootFromDialog() {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: 'Select nanobot checkout',
  });
  if (result.canceled || !result.filePaths[0]) {
    return null;
  }
  const saved = setNanobotRoot(result.filePaths[0]);
  if (!saved.ok) {
    throw makeStartupError('invalid_nanobot_root', saved.error);
  }
  return result.filePaths[0];
}

async function handleStartupFailure(error, config) {
  stopConsoleReadyWatcher();
  if (error?.code === 'bootstrap_canceled') {
    sendBootstrapState({
      stage: 'canceled',
      message: 'Python environment bootstrap canceled',
      error: '',
      stderrTail: bootstrapTail,
    });
    return;
  }

  const reason = error instanceof Error ? error : makeStartupError('startup_failed', String(error));
  writeMainLog(`startup failed ${reason.code || ''}: ${reason.message}`);
  sendBootstrapState({
    stage: reason.code === 'nanobot_not_found' ? 'nanobot' : 'error',
    message: 'Ava startup failed',
    error: reason.message,
    stderrTail: stderrTail || bootstrapTail || reason.detail || '',
  });

  const action = await showStartupError(reason, config.coreLogPath, stderrTail || bootstrapTail || '');
  if (action === 'retry') {
    startupPromise = null;
    await bootstrapAndStart(config);
  } else if (action === 'pickNanobot') {
    await pickNanobotRootFromDialog();
    startupPromise = null;
    await bootstrapAndStart(config);
  } else if (action === 'openLogs') {
    await openLogs();
  } else {
    app.quit();
  }
}

async function runStartup(config) {
  sendBootstrapState({
    stage: 'checking',
    message: 'Checking desktop launch prerequisites',
    error: '',
    coreEndpoint: config.coreEndpoint,
  });
  if (!config.repoRootFound) {
    throw makeStartupError(
      'repo_root_not_found',
      'Ava.app is still repo-coupled and must be launched from an Ava checkout.',
      `Could not find scripts/start-ava.sh from ${__dirname}`,
    );
  }
  if (config.externalCore) {
    await loadConsole(config, 'existing core');
    return;
  }
  const nanobotRoot = ensureNanobotRoot(config);
  await ensureVenvBootstrapped(config);
  sendBootstrapState({
    stage: 'sidecar',
    message: 'Starting Ava core sidecar',
    error: '',
  });
  const child = startAvaCore(config, nanobotRoot);
  startConsoleReadyWatcher(config);
  await waitForAvaCoreOrExit(child, config);
  await loadConsole(config, 'startup');
}

async function bootstrapAndStart(config) {
  if (startupPromise) {
    return startupPromise;
  }
  startupPromise = (async () => {
    try {
      await runStartup(config);
    } catch (error) {
      await handleStartupFailure(error, config);
    } finally {
      startupPromise = null;
    }
  })();
  return startupPromise;
}

function cancelBootstrap() {
  if (!activeBootstrapProcess) {
    return { ok: false, error: 'no bootstrap process is running' };
  }
  const active = activeBootstrapProcess;
  let exited = false;
  const killTimeout = setTimeout(() => {
    if (!exited) {
      active.child.kill('SIGKILL');
    }
  }, 5_000);
  killTimeout.unref?.();
  active.child.once('exit', () => {
    exited = true;
    clearTimeout(killTimeout);
  });
  active.cancelRequested = true;
  active.child.kill('SIGTERM');
  return { ok: true };
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

function installAppMenu() {
  const menu = Menu.buildFromTemplate([
    ...(process.platform === 'darwin'
      ? [
        {
          label: app.name,
          submenu: [
            { role: 'about' },
            { type: 'separator' },
            { role: 'services' },
            { type: 'separator' },
            { role: 'hide' },
            { role: 'hideOthers' },
            { role: 'unhide' },
            { type: 'separator' },
            { role: 'quit' },
          ],
        },
      ]
      : []),
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
    {
      label: 'Window',
      submenu: [
        { role: 'minimize' },
        { role: 'zoom' },
        ...(process.platform === 'darwin'
          ? [
            { type: 'separator' },
            { role: 'front' },
          ]
          : [
            { role: 'close' },
          ]),
      ],
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'Retry Core',
          click: () => {
            retryCore().catch(showFatalStartupError);
          },
        },
        {
          label: 'Open Logs',
          click: () => {
            openLogs();
          },
        },
      ],
    },
  ]);
  Menu.setApplicationMenu(menu);
}

async function showMainWindow() {
  const config = await createLaunchConfig();
  const hadWindow = mainWindow && !mainWindow.isDestroyed();
  const appWindow = createBootstrapWindow(config);
  if (appWindow.isMinimized()) {
    appWindow.restore();
  }
  appWindow.show();
  appWindow.focus();

  if (consoleLoaded) {
    if (!hadWindow) {
      await appWindow.loadURL(config.coreEndpoint);
    }
    return;
  }

  await bootstrapAndStart(config);
}

async function retryCore() {
  const config = await createLaunchConfig();
  await bootstrapAndStart(config);
  return { ok: true };
}

ipcMain.handle('ava:getAppConfig', () => getAvaConfig());
ipcMain.handle('ava:getCoreEndpoint', () => getAvaConfig().coreEndpoint);
ipcMain.handle('ava:getAuthToken', () => null);
ipcMain.handle('ava:getBootstrapState', () => bootstrapState);
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
ipcMain.handle('ava:openLogs', () => openLogs());
ipcMain.handle('ava:readDesktopConfig', () => readDesktopConfig());
ipcMain.handle('ava:setNanobotRoot', (_event, root) => {
  if (typeof root !== 'string') {
    return { ok: false, error: 'invalid nanobot root' };
  }
  return setNanobotRoot(root);
});
ipcMain.handle('ava:retryCore', async () => {
  return retryCore();
});
ipcMain.handle('ava:cancelBootstrap', () => cancelBootstrap());
ipcMain.handle('ava:showNotification', (_event, payload) => {
  const title = typeof payload?.title === 'string' ? payload.title : 'Ava';
  const body = typeof payload?.body === 'string' ? payload.body : '';
  const taskId = typeof payload?.taskId === 'string' ? payload.taskId : null;
  if (Notification.isSupported()) {
    const notification = new Notification({ title, body });
    notification.on('click', () => {
      showMainWindow()
        .then(() => {
          mainWindow?.webContents.send('ava:openTaskFloater', { taskId });
        })
        .catch(showFatalStartupError);
    });
    notification.show();
  }
  return { ok: true };
});

app.on('second-instance', () => {
  if (!mainWindow) {
    return;
  }
  if (mainWindow.isMinimized()) {
    mainWindow.restore();
  }
  mainWindow.focus();
});

app.whenReady().then(async () => {
  const config = await createLaunchConfig();
  installAppMenu();
  createBootstrapWindow(config);
  await bootstrapAndStart(config);
}).catch(showFatalStartupError);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  showMainWindow().catch(showFatalStartupError);
});

app.on('before-quit', async (event) => {
  if (allowQuit) {
    return;
  }
  event.preventDefault();
  allowQuit = true;
  await stopAvaCore();
  logs?.mainStream.end();
  logs?.coreStream.end();
  app.quit();
});
