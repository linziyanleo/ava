import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..');
const setupPath = path.join(repoRoot, 'electron', 'setup.html');
const html = fs.readFileSync(setupPath, 'utf8');
const scriptMatch = html.match(/<script>([\s\S]*)<\/script>\s*<\/body>/);
if (!scriptMatch) {
  throw new Error('setup.html inline script not found');
}

class FakeElement {
  constructor(id) {
    this.id = id;
    this.textContent = '';
    this.hidden = false;
    this.listeners = new Map();
  }

  addEventListener(eventName, listener) {
    this.listeners.set(eventName, listener);
  }

  async click() {
    const listener = this.listeners.get('click');
    if (!listener) {
      throw new Error(`${this.id} has no click listener`);
    }
    await listener();
  }
}

const ids = [
  'stage',
  'message',
  'endpoint',
  'nanobot',
  'logs',
  'errorRow',
  'error',
  'tail',
  'pickNanobot',
  'retry',
  'cancel',
  'openLogs',
];
const elements = new Map(ids.map((id) => [id, new FakeElement(id)]));

function element(id) {
  const found = elements.get(id);
  if (!found) {
    throw new Error(`unexpected element lookup: ${id}`);
  }
  return found;
}

const calls = [];
let bootstrapCallback = null;
let selectedDirectory = '/valid/nanobot';
let setNanobotResult = { ok: true };

const context = vm.createContext({
  console,
  document: {
    getElementById: element,
  },
  window: {
    avaDesktop: {
      onBootstrapState(callback) {
        calls.push('onBootstrapState');
        bootstrapCallback = callback;
      },
      readDesktopConfig() {
        calls.push('readDesktopConfig');
        return Promise.resolve({ nanobotRoot: '/stored/nanobot' });
      },
      selectDirectory() {
        calls.push('selectDirectory');
        return Promise.resolve(selectedDirectory);
      },
      setNanobotRoot(root) {
        calls.push(`setNanobotRoot:${root}`);
        return Promise.resolve(setNanobotResult);
      },
      retryCore() {
        calls.push('retryCore');
        return Promise.resolve({ ok: true });
      },
      cancelBootstrap() {
        calls.push('cancelBootstrap');
        return Promise.resolve({ ok: true });
      },
      openLogs() {
        calls.push('openLogs');
        return Promise.resolve({ ok: true });
      },
    },
  },
});

vm.runInContext(scriptMatch[1], context, { filename: setupPath });
await Promise.resolve();

if (typeof bootstrapCallback !== 'function') {
  throw new Error('onBootstrapState did not register a callback');
}
if (element('nanobot').textContent !== '/stored/nanobot') {
  throw new Error('readDesktopConfig did not render stored nanobot root');
}

bootstrapCallback({
  stage: 'venv',
  message: 'Creating Ava Python environment',
  coreEndpoint: 'http://127.0.0.1:6688',
  nanobotRoot: '/stored/nanobot',
  logDir: '/tmp/logs',
  error: 'uv failed',
  stderrTail: 'tail text',
});
if (element('stage').textContent !== 'venv') {
  throw new Error('stage did not render');
}
if (element('message').textContent !== 'Creating Ava Python environment') {
  throw new Error('message did not render');
}
if (element('endpoint').textContent !== 'http://127.0.0.1:6688') {
  throw new Error('endpoint did not render');
}
if (element('errorRow').hidden !== false || element('tail').hidden !== false) {
  throw new Error('error or tail visibility did not render');
}

await element('pickNanobot').click();
if (!calls.includes('selectDirectory') || !calls.includes('setNanobotRoot:/valid/nanobot') || !calls.includes('retryCore')) {
  throw new Error('valid Select Nanobot flow did not call expected IPC methods');
}

setNanobotResult = { ok: false, error: 'missing pyproject.toml' };
selectedDirectory = '/invalid/nanobot';
await element('pickNanobot').click();
if (element('stage').textContent !== 'nanobot' || element('error').textContent !== 'missing pyproject.toml') {
  throw new Error('invalid Select Nanobot flow did not render validation error');
}

await element('retry').click();
await element('cancel').click();
await element('openLogs').click();
if (!calls.includes('retryCore') || !calls.includes('cancelBootstrap') || !calls.includes('openLogs')) {
  throw new Error('Retry, Cancel, or Open Logs did not call expected IPC methods');
}

bootstrapCallback({
  stage: 'canceled',
  message: 'Python environment bootstrap canceled',
  stderrTail: 'uv sync canceled',
});
if (element('stage').textContent !== 'canceled') {
  throw new Error('canceled state did not render');
}
if (element('message').textContent !== 'Python environment bootstrap canceled') {
  throw new Error('canceled message did not render');
}
if (element('tail').textContent !== 'uv sync canceled' || element('tail').hidden !== false) {
  throw new Error('canceled tail did not render');
}

console.log('Desktop setup DOM behavior verified');
