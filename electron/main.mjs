import {
  app,
  BrowserWindow,
  Tray,
  Menu,
  Notification,
  dialog,
  globalShortcut,
  ipcMain,
  nativeImage,
  session,
  shell,
} from 'electron';
import { spawn } from 'node:child_process';
import crypto from 'node:crypto';
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
  httpGetStatus,
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
import { prepareRuntimeMirror } from './lib/runtime-mirror.mjs';
import { checkForUpdate } from './lib/update-check.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DESKTOP_SESSION_TOKEN = crypto.randomBytes(32).toString('hex');
const DESKTOP_HANDSHAKE_TIMEOUT_MS = 5_000;
const DEFAULT_CONSOLE_PORT = 6688;
const DEFAULT_GATEWAY_PORT = 18790;
const DEFAULT_WEBSOCKET_PORT = 8765;
const CORE_HEALTH_TIMEOUT_MS = 120_000;
const TRAY_ICON_SIZE = 18;
const STARTUP_INTERFACE_TIMEOUT_MS = 2_000;
const SETUP_LOAD_TIMEOUT_MS = 5_000;
const LOG_ROTATE_BYTES = 1024 * 1024;
const RING_BUFFER_BYTES = 256 * 1024;
const UPDATE_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;
const UPDATE_CHECK_INITIAL_DELAY_MS = 5 * 1000;

let mainWindow = null;
let avaCoreProcess = null;
let activeBootstrapProcess = null;
let tray = null;
let allowQuit = false;
let launchConfigPromise = null;
let launchConfig = null;
let startupPromise = null;
let consoleLoadPromise = null;
let consoleLoaded = false;
let consoleReadyWatcher = null;
let updateCheckTimer = null;
let updateCheckInitialTimer = null;
let pendingDeepLink = null;
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

if (process.platform === 'darwin') {
  // Prevent Chromium Safe Storage from blocking launch with a login keychain prompt.
  app.commandLine.appendSwitch('use-mock-keychain');
}

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
    gatewayPort: null,
    websocketPort: null,
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

function deepLinkScheme() {
  return process.env.AVA_DEEP_LINK_SCHEME || (app.isPackaged ? 'ava' : 'ava-dev');
}

function registerDeepLinkProtocol() {
  const scheme = deepLinkScheme();
  if (app.isPackaged) {
    app.setAsDefaultProtocolClient(scheme);
    return;
  }
  const entry = process.argv[1] ? [path.resolve(process.argv[1])] : [];
  app.setAsDefaultProtocolClient(scheme, process.execPath, entry);
}

function routeDeepLink(rawUrl) {
  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch {
    return null;
  }
  if (parsed.protocol !== `${deepLinkScheme()}:`) {
    return null;
  }
  const segments = [parsed.hostname, ...parsed.pathname.split('/').filter(Boolean)].filter(Boolean);
  const [kind, value] = segments;
  if (!kind) return '/';

  const params = new URLSearchParams();
  if (kind === 'session' && value) {
    params.set('session_key', value);
    return `/?${params.toString()}`;
  }
  if (kind === 'task' && value) {
    params.set('view', 'tasks');
    params.set('task_id', value);
    return `/?${params.toString()}`;
  }
  if (kind === 'trace' && value) {
    params.set('view', 'tasks');
    params.set('trace_id', value);
    return `/?${params.toString()}`;
  }
  if (kind === 'chain' && value) {
    params.set('view', 'tasks');
    params.set('chain_id', value);
    return `/?${params.toString()}`;
  }
  if (kind === 'settings') {
    return `/settings/${segments.slice(1).join('/')}`;
  }
  return null;
}

function flushPendingDeepLink() {
  if (!pendingDeepLink || !mainWindow || mainWindow.isDestroyed() || !consoleLoaded) {
    return;
  }
  const pathToOpen = pendingDeepLink;
  pendingDeepLink = null;
  mainWindow.webContents.send('ava:deepLink', { path: pathToOpen });
}

async function handleDeepLink(rawUrl) {
  const pathToOpen = routeDeepLink(rawUrl);
  if (!pathToOpen) return;

  const canSendImmediately = consoleLoaded && mainWindow && !mainWindow.isDestroyed();
  pendingDeepLink = pathToOpen;
  await showMainWindow();
  if (canSendImmediately) {
    flushPendingDeepLink();
  }
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
  writeMainLog('Ava desktop launch');
  return logs;
}

function writeMainLog(message) {
  if (!logs?.mainLogPath) {
    return;
  }
  fs.appendFileSync(logs.mainLogPath, `[${new Date().toISOString()}] ${message}\n`);
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

function readPreferredPort(rawValue, fallback, label) {
  const value = Number(rawValue || fallback);
  if (!Number.isInteger(value) || value <= 0 || value > 65_535) {
    throw makeStartupError('invalid_desktop_port', `${label} must be an integer port between 1 and 65535`);
  }
  return value;
}

async function pickDistinctFreePort(preferred, usedPorts, host = '127.0.0.1') {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    const selected = await pickFreePort(attempt === 0 ? preferred : 0, host);
    if (!usedPorts.has(selected)) {
      usedPorts.add(selected);
      return selected;
    }
  }
  throw makeStartupError('port_selection_failed', 'Could not select distinct desktop runtime ports');
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
    const preferredPort = readPreferredPort(
      process.env.AVA_DESKTOP_CONSOLE_PORT || process.env.CAFE_CONSOLE_PORT,
      DEFAULT_CONSOLE_PORT,
      'Console port',
    );
    const existingCore = await resolveExistingAvaCore(host, preferredPort);
    const externalCore = Boolean(existingCore);
    const usedPorts = new Set();
    const port = existingCore?.port || await pickDistinctFreePort(preferredPort, usedPorts, host);
    const gatewayPort = externalCore ? null : await pickDistinctFreePort(
      readPreferredPort(process.env.AVA_DESKTOP_GATEWAY_PORT, DEFAULT_GATEWAY_PORT, 'Gateway port'),
      usedPorts,
      '0.0.0.0',
    );
    const websocketPort = externalCore ? null : await pickDistinctFreePort(
      readPreferredPort(process.env.AVA_DESKTOP_WEBSOCKET_PORT, DEFAULT_WEBSOCKET_PORT, 'WebSocket port'),
      usedPorts,
      '127.0.0.1',
    );
    const launchHost = existingCore?.host || host;
    const coreEndpoint = endpoint(launchHost, port);
    const config = {
      repoRoot,
      repoRootFound: Boolean(detectedRepoRoot),
      host: launchHost,
      port,
      gatewayPort,
      websocketPort,
      externalCore,
      coreEndpoint,
      healthEndpoint: `${coreEndpoint}/api/gateway/health`,
      logDir: logs.logDir,
      mainLogPath: logs.mainLogPath,
      coreLogPath: logs.coreLogPath,
      env: resolveLaunchPath(process.env),
    };
    writeMainLog(
      `launch config repoRootFound=${config.repoRootFound} externalCore=${config.externalCore} coreEndpoint=${config.coreEndpoint} gatewayPort=${config.gatewayPort ?? ''} websocketPort=${config.websocketPort ?? ''}`,
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

function ensureForegroundActivation() {
  if (process.platform !== 'darwin') {
    return;
  }
  try {
    app.setActivationPolicy('regular');
    app.dock?.show?.();
  } catch (error) {
    writeMainLog(`failed to ensure foreground activation: ${String(error)}`);
  }
}

function presentMainWindow(appWindow, reason) {
  if (!appWindow || appWindow.isDestroyed()) {
    return;
  }
  ensureForegroundActivation();
  if (appWindow.isMinimized()) {
    appWindow.restore();
  }
  appWindow.setSkipTaskbar(false);
  appWindow.show();
  appWindow.moveTop();
  appWindow.focus();
  if (process.platform === 'darwin') {
    app.focus({ steal: true });
  }
  writeMainLog(
    `presented main window (${reason}) visible=${appWindow.isVisible()} minimized=${appWindow.isMinimized()} focused=${appWindow.isFocused()}`,
  );
}

function createBootstrapWindow(config, { loadSetup = true } = {}) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    return mainWindow;
  }
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 680,
    title: 'Ava',
    show: false,
    focusable: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  if (!loadSetup) {
    return mainWindow;
  }
  const setupLoadTimeout = setTimeout(() => {
    writeMainLog(`setup surface did not finish loading within ${SETUP_LOAD_TIMEOUT_MS}ms`);
  }, SETUP_LOAD_TIMEOUT_MS);
  mainWindow.on('closed', () => {
    clearTimeout(setupLoadTimeout);
    mainWindow = null;
  });
  mainWindow.webContents.once('did-finish-load', () => {
    clearTimeout(setupLoadTimeout);
    presentMainWindow(mainWindow, 'setup loaded');
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

async function checkStartupInterfaces(config) {
  const health = await httpGetJson(config.healthEndpoint, STARTUP_INTERFACE_TIMEOUT_MS);
  if (!isHealthyCorePayload(health)) {
    throw makeStartupError(
      'core_health_unready',
      'Ava core health endpoint did not report ready',
      `${config.healthEndpoint} returned ${JSON.stringify(health)}`,
    );
  }

  const authStatus = await httpGetStatus(`${config.coreEndpoint}/api/auth/me`, STARTUP_INTERFACE_TIMEOUT_MS);
  if (authStatus !== 200 && authStatus !== 401) {
    throw makeStartupError(
      'auth_interface_unready',
      `Ava auth interface returned HTTP ${authStatus}`,
      `${config.coreEndpoint}/api/auth/me must return 200 for an existing session or 401 for a login-required session before Console loads.`,
    );
  }

  return { health, authStatus };
}

async function waitForStartupInterfaces(config) {
  const deadline = Date.now() + CORE_HEALTH_TIMEOUT_MS;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      return await checkStartupInterfaces(config);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw makeStartupError(
    'core_startup_timeout',
    `Ava core did not become reachable within ${Math.round(CORE_HEALTH_TIMEOUT_MS / 1000)} seconds`,
    lastError ? String(lastError.message || lastError) : '',
  );
}

function stopConsoleReadyWatcher() {
  if (consoleReadyWatcher) {
    clearTimeout(consoleReadyWatcher);
    consoleReadyWatcher = null;
  }
}

async function performDesktopHandshake(config) {
  if (config.externalCore) {
    writeMainLog('desktop handshake skipped: external core has no shared token');
    return false;
  }
  const handshakeUrl = `${config.coreEndpoint}/api/auth/desktop-session`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DESKTOP_HANDSHAKE_TIMEOUT_MS);
  let response;
  try {
    response = await fetch(handshakeUrl, {
      method: 'POST',
      headers: { 'X-Ava-Desktop-Token': DESKTOP_SESSION_TOKEN },
      signal: controller.signal,
    });
  } catch (error) {
    writeMainLog(`desktop handshake request failed: ${String(error)}`);
    return false;
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) {
    writeMainLog(`desktop handshake returned HTTP ${response.status}`);
    return false;
  }
  const setCookie = response.headers.get('set-cookie');
  if (!setCookie) {
    writeMainLog('desktop handshake response missing Set-Cookie');
    return false;
  }
  const match = setCookie.match(/^([^=]+)=([^;]+)/);
  if (!match) {
    writeMainLog('desktop handshake Set-Cookie not parseable');
    return false;
  }
  try {
    await session.defaultSession.cookies.set({
      url: config.coreEndpoint,
      name: match[1],
      value: match[2],
      httpOnly: true,
      sameSite: 'strict',
      path: '/',
    });
  } catch (error) {
    writeMainLog(`desktop handshake cookie injection failed: ${String(error)}`);
    return false;
  }
  writeMainLog('desktop handshake succeeded; owner session cookie injected');
  return true;
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
    await performDesktopHandshake(config);
    writeMainLog(`loading Console from ${config.coreEndpoint} (${reason})`);
    await mainWindow.loadURL(config.coreEndpoint);
    consoleLoaded = true;
    presentMainWindow(mainWindow, `console loaded: ${reason}`);
    writeMainLog(`Console loaded from ${config.coreEndpoint} (${reason})`);
    scheduleUpdateChecks();
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
      await checkStartupInterfaces(config);
      await loadConsole(config, 'health watcher');
      return;
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
  const venvPythonPath = path.join(config.repoRoot, '.venv', 'bin', 'python');
  if (!fs.existsSync(venvPythonPath)) {
    throw makeStartupError('python_not_found', `Ava Python interpreter not found: ${venvPythonPath}`);
  }
  const pythonPath = fs.realpathSync(venvPythonPath);
  const packagedRuntimeRoot = path.join(process.resourcesPath, 'ava-runtime');
  const runtimeSourceRoot = app.isPackaged && fs.existsSync(packagedRuntimeRoot)
    ? packagedRuntimeRoot
    : config.repoRoot;
  writeMainLog(`preparing ava runtime mirror from ${runtimeSourceRoot}`);
  const runtime = prepareRuntimeMirror({
    appDataPath: app.getPath('userData'),
    repoRoot: runtimeSourceRoot,
    nanobotRoot,
    pythonExecutable: pythonPath,
  });

  const env = buildCoreEnv(
    { ...config, repoRoot: runtime.repoRoot, pythonExecutable: pythonPath },
    runtime.nanobotRoot,
    DESKTOP_SESSION_TOKEN,
  );
  writeMainLog(`starting ava-core sidecar repoRoot=${runtime.repoRoot} nanobotRoot=${runtime.nanobotRoot}`);
  const child = spawn(pythonPath, ['-m', 'ava', 'gateway'], {
    cwd: runtime.repoRoot,
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
    waitForStartupInterfaces(config),
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

function readElectronAppVersion() {
  const packagePath = path.join(__dirname, 'package.json');
  const electronPackage = JSON.parse(fs.readFileSync(packagePath, 'utf8'));
  if (typeof electronPackage.version !== 'string') {
    throw new Error('electron package.json must define version');
  }
  return electronPackage.version;
}

function showUpdateNotification(update) {
  if (!Notification.isSupported()) {
    writeMainLog(`update notification unsupported for ${update.version}`);
    return false;
  }
  const notification = new Notification({
    title: `Ava ${update.version} is available`,
    body: 'Open the GitHub release to download the latest build.',
  });
  notification.on('click', () => {
    shell.openExternal(update.url).catch((error) => {
      writeMainLog(`failed to open update release: ${String(error)}`);
    });
  });
  notification.show();
  writeMainLog(`update notification shown for ${update.version}: ${update.url}`);
  return true;
}

async function runUpdateCheck() {
  try {
    const update = await checkForUpdate({ currentVersion: readElectronAppVersion() });
    if (update.available) {
      showUpdateNotification(update);
    } else {
      writeMainLog(`update check found no newer release: ${update.version}`);
    }
  } catch (error) {
    writeMainLog(`update check failed: ${String(error)}`);
  }
}

function scheduleUpdateChecks() {
  if (updateCheckTimer || updateCheckInitialTimer) {
    return;
  }
  updateCheckInitialTimer = setTimeout(() => {
    updateCheckInitialTimer = null;
    void runUpdateCheck();
  }, UPDATE_CHECK_INITIAL_DELAY_MS);
  updateCheckInitialTimer.unref?.();
  updateCheckTimer = setInterval(() => {
    void runUpdateCheck();
  }, UPDATE_CHECK_INTERVAL_MS);
  updateCheckTimer.unref?.();
}

function setDockBadgeCount(count) {
  if (!Number.isInteger(count) || count < 0) {
    return { ok: false, error: 'invalid badge count' };
  }
  if (process.platform === 'darwin') {
    app.dock.setBadge(count > 0 ? String(count) : '');
  }
  return { ok: true };
}

function installTray() {
  if (tray) {
    return;
  }
  const iconPath = path.join(__dirname, 'assets', 'tray-icon-Template.png');
  const image = nativeImage.createFromPath(iconPath);
  if (image.isEmpty()) {
    throw new Error(`missing tray icon: ${iconPath}`);
  }
  const trayImage = image.resize({ width: TRAY_ICON_SIZE, height: TRAY_ICON_SIZE });
  trayImage.setTemplateImage(true);
  tray = new Tray(trayImage);
  tray.setToolTip('Ava');
  tray.setContextMenu(Menu.buildFromTemplate([
    {
      label: 'Show Window',
      click: () => {
        showMainWindow().catch(showFatalStartupError);
      },
    },
    {
      label: 'Open Logs',
      click: () => {
        openLogs().catch(showFatalStartupError);
      },
    },
    {
      label: 'Retry Core',
      click: () => {
        retryCore().catch(showFatalStartupError);
      },
    },
    { type: 'separator' },
    { label: 'Quit', role: 'quit' },
  ]));
  tray.on('click', () => {
    showMainWindow().catch(showFatalStartupError);
  });
}

function installGlobalShortcut() {
  const registered = globalShortcut.register('Control+Shift+A', () => {
    showMainWindow().catch(showFatalStartupError);
  });
  if (!registered) {
    writeMainLog('failed to register global shortcut Control+Shift+A');
  }
}

function installDesktopIntegrations() {
  installTray();
  installGlobalShortcut();
}

function avaHome() {
  return path.resolve(process.env.AVA_HOME || path.join(os.homedir(), '.ava'));
}

function artifactRoots() {
  const mediaRoot = path.join(avaHome(), 'media');
  return [
    path.join(mediaRoot, 'generated'),
    path.join(mediaRoot, 'screenshots'),
    path.join(mediaRoot, 'chat-uploads'),
  ];
}

function assertPathInsideRoots(candidate, roots) {
  const resolved = path.resolve(candidate);
  for (const root of roots) {
    const resolvedRoot = path.resolve(root);
    const relative = path.relative(resolvedRoot, resolved);
    if (relative && !relative.startsWith('..') && !path.isAbsolute(relative)) {
      return resolved;
    }
    if (!relative) {
      return resolved;
    }
  }
  throw new Error('artifact path is outside allowed roots');
}

function resolveRevealArtifactPath(artifactId) {
  if (typeof artifactId !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(artifactId)) {
    throw new Error('invalid artifact id');
  }

  const roots = artifactRoots();
  const candidates = [];
  for (const root of roots) {
    candidates.push(path.join(root, artifactId));
    candidates.push(path.join(root, `${artifactId}_0.png`));
  }

  for (const candidate of candidates) {
    const resolved = assertPathInsideRoots(candidate, roots);
    if (fs.existsSync(resolved)) {
      return resolved;
    }
  }

  for (const root of roots) {
    if (!fs.existsSync(root)) continue;
    const match = fs.readdirSync(root).find((entry) => entry === artifactId || entry.startsWith(`${artifactId}_`));
    if (match) {
      const resolved = assertPathInsideRoots(path.join(root, match), roots);
      if (fs.existsSync(resolved)) {
        return resolved;
      }
    }
  }

  throw new Error('artifact not found');
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
  await stopAvaCore();
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
    sendBootstrapState({
      stage: 'interfaces',
      message: 'Checking Ava core interfaces',
      error: '',
    });
    await waitForStartupInterfaces(config);
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
  sendBootstrapState({
    stage: 'interfaces',
    message: 'Checking Ava core interfaces',
    error: '',
  });
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
  avaCoreProcess = null;
  return new Promise((resolve) => {
    let exited = false;
    const timeout = setTimeout(() => {
      if (!exited) {
        child.kill('SIGKILL');
      }
      resolve();
    }, 5_000);
    child.once('exit', () => {
      exited = true;
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
        { role: 'close' },
        { role: 'minimize' },
        { role: 'zoom' },
        ...(process.platform === 'darwin'
          ? [
            { type: 'separator' },
            { role: 'front' },
          ]
          : []),
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
  const appWindow = createBootstrapWindow(config, { loadSetup: !consoleLoaded });
  presentMainWindow(appWindow, 'show requested');

  if (consoleLoaded) {
    if (!hadWindow) {
      await appWindow.loadURL(config.coreEndpoint);
      presentMainWindow(appWindow, 'console reloaded');
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
ipcMain.handle('ava:rendererReady', () => {
  flushPendingDeepLink();
  return { ok: true };
});
ipcMain.handle('ava:selectDirectory', async () => {
  const result = await dialog.showOpenDialog({ properties: ['openDirectory'] });
  return result.canceled ? null : result.filePaths[0] || null;
});
ipcMain.handle('ava:revealArtifact', (_event, artifactId) => {
  const targetPath = resolveRevealArtifactPath(artifactId);
  shell.showItemInFolder(targetPath);
  return { ok: true };
});
ipcMain.handle('ava:setBadgeCount', (_event, count) => setDockBadgeCount(count));
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

app.on('open-url', (event, url) => {
  event.preventDefault();
  handleDeepLink(url).catch(showFatalStartupError);
});

app.on('second-instance', (_event, commandLine) => {
  const deepLinkUrl = commandLine.find((item) => item.startsWith(`${deepLinkScheme()}://`));
  if (deepLinkUrl) {
    handleDeepLink(deepLinkUrl).catch(showFatalStartupError);
    return;
  }
  if (mainWindow) {
    presentMainWindow(mainWindow, 'second instance');
  }
});

app.whenReady().then(async () => {
  const config = await createLaunchConfig();
  registerDeepLinkProtocol();
  installAppMenu();
  installDesktopIntegrations();
  ensureForegroundActivation();
  await showMainWindow();
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
  if (updateCheckTimer) {
    clearInterval(updateCheckTimer);
    updateCheckTimer = null;
  }
  if (updateCheckInitialTimer) {
    clearTimeout(updateCheckInitialTimer);
    updateCheckInitialTimer = null;
  }
  globalShortcut.unregisterAll();
  tray?.destroy();
  tray = null;
  setDockBadgeCount(0);
  await stopAvaCore();
  logs?.mainStream.end();
  logs?.coreStream.end();
  app.quit();
});
