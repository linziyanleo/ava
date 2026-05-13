import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const electronRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(electronRoot, '..');
const dryRun = process.argv.includes('--dry-run');
const skipConsoleBuild = process.argv.includes('--skip-console-build');
const electronDownloadCacheRoot = process.env.ELECTRON_DOWNLOAD_CACHE_ROOT
  || path.join(os.tmpdir(), 'ava-electron-cache');
const runtimeManifestName = 'ava-runtime-manifest.json';
const urlScheme = process.env.AVA_DEEP_LINK_SCHEME || 'ava';

function assertPath(relativePath) {
  const absolutePath = path.join(repoRoot, relativePath);
  if (!fs.existsSync(absolutePath)) {
    throw new Error(`missing required path: ${relativePath}`);
  }
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: repoRoot,
    stdio: 'inherit',
    shell: false,
    ...options,
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(' ')} failed with exit ${result.status}`);
  }
}

function assertExecutable(filePath) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`missing executable: ${filePath}`);
  }
  fs.accessSync(filePath, fs.constants.X_OK);
}

function writeRuntimeManifest() {
  const manifestDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ava-electron-runtime-'));
  const manifestPath = path.join(manifestDir, runtimeManifestName);
  fs.writeFileSync(
    manifestPath,
    `${JSON.stringify({
      version: 1,
      repoRoot,
      createdAt: new Date().toISOString(),
    }, null, 2)}\n`,
    'utf8',
  );
  return { manifestDir, manifestPath };
}

function readPlistValue(plistPath, key) {
  const result = spawnSync('plutil', ['-extract', key, 'raw', '-o', '-', plistPath], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  if (result.status !== 0) {
    throw new Error(`failed to read ${key} from ${plistPath}: ${result.stderr}`);
  }
  return result.stdout.trim();
}

function readPlistJson(plistPath, key) {
  const result = spawnSync('plutil', ['-extract', key, 'json', '-o', '-', plistPath], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  if (result.status !== 0) {
    throw new Error(`failed to read ${key} from ${plistPath}: ${result.stderr}`);
  }
  return JSON.parse(result.stdout);
}

function plistBuddy(plistPath, command, options = {}) {
  const result = spawnSync('/usr/libexec/PlistBuddy', ['-c', command, plistPath], {
    encoding: 'utf8',
    stdio: options.ignoreFailure ? 'ignore' : ['ignore', 'pipe', 'pipe'],
  });
  if (result.status !== 0 && !options.ignoreFailure) {
    throw new Error(`PlistBuddy ${command} failed: ${result.stderr}`);
  }
}

function injectUrlScheme(appPath) {
  const infoPlist = path.join(appPath, 'Contents', 'Info.plist');
  plistBuddy(infoPlist, 'Delete :CFBundleURLTypes', { ignoreFailure: true });
  plistBuddy(infoPlist, 'Add :CFBundleURLTypes array');
  plistBuddy(infoPlist, 'Add :CFBundleURLTypes:0 dict');
  plistBuddy(infoPlist, 'Add :CFBundleURLTypes:0:CFBundleURLName string app.ava.desktop');
  plistBuddy(infoPlist, 'Add :CFBundleURLTypes:0:CFBundleURLSchemes array');
  plistBuddy(infoPlist, `Add :CFBundleURLTypes:0:CFBundleURLSchemes:0 string ${urlScheme}`);
}

function readInstalledElectronVersion() {
  const packagePath = path.join(electronRoot, 'node_modules', 'electron', 'package.json');
  const electronPackage = JSON.parse(fs.readFileSync(packagePath, 'utf8'));
  return electronPackage.version;
}

function findCachedElectronZipDir(cacheRoot, version, platform = 'darwin', arch = 'arm64') {
  const expectedName = `electron-v${version}-${platform}-${arch}.zip`;
  const stack = [cacheRoot];
  while (stack.length > 0) {
    const current = stack.pop();
    if (!current || !fs.existsSync(current)) {
      continue;
    }
    const entries = fs.readdirSync(current, { withFileTypes: true });
    for (const entry of entries) {
      const entryPath = path.join(current, entry.name);
      if (entry.isFile() && entry.name === expectedName) {
        return current;
      }
      if (entry.isDirectory()) {
        stack.push(entryPath);
      }
    }
  }
  return '';
}

function verifyPackagedApp(appPath) {
  const infoPlist = path.join(appPath, 'Contents', 'Info.plist');
  const frameworksDir = path.join(appPath, 'Contents', 'Frameworks');
  if (!fs.existsSync(infoPlist)) {
    throw new Error(`missing Info.plist: ${infoPlist}`);
  }
  const bundleExecutable = readPlistValue(infoPlist, 'CFBundleExecutable');
  if (!bundleExecutable) {
    throw new Error(`missing CFBundleExecutable in ${infoPlist}`);
  }
  const mainExecutable = path.join(appPath, 'Contents', 'MacOS', bundleExecutable);
  assertExecutable(mainExecutable);
  for (const helperName of ['Ava Helper.app', 'Ava Helper (GPU).app', 'Ava Helper (Plugin).app', 'Ava Helper (Renderer).app']) {
    const executableName = helperName.replace(/\.app$/, '');
    assertExecutable(path.join(frameworksDir, helperName, 'Contents', 'MacOS', executableName));
  }
  const manifestPath = path.join(appPath, 'Contents', 'Resources', runtimeManifestName);
  if (!fs.existsSync(manifestPath)) {
    throw new Error(`missing runtime manifest: ${manifestPath}`);
  }
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  if (manifest.repoRoot !== repoRoot || !fs.existsSync(path.join(manifest.repoRoot, 'scripts', 'start-ava.sh'))) {
    throw new Error(`invalid runtime manifest repoRoot: ${manifest.repoRoot}`);
  }
  const urlTypes = readPlistJson(infoPlist, 'CFBundleURLTypes');
  const schemes = urlTypes.flatMap((entry) => Array.isArray(entry.CFBundleURLSchemes) ? entry.CFBundleURLSchemes : []);
  if (!schemes.includes(urlScheme)) {
    throw new Error(`missing URL scheme ${urlScheme} in ${infoPlist}`);
  }
}

function verifyContract() {
  [
    'electron/main.mjs',
    'electron/preload.cjs',
    'electron/lib/core-health.mjs',
    'electron/lib/desktop-config.mjs',
    'electron/lib/launch-env.mjs',
    'electron/lib/ports.mjs',
    'electron/lib/runtime-manifest.mjs',
    'electron/bin/ava-core',
    'console-ui/package.json',
    'scripts/start-ava.sh',
    'package.json',
  ].forEach(assertPath);

  const rootPackage = JSON.parse(fs.readFileSync(path.join(repoRoot, 'package.json'), 'utf8'));
  const electronPackage = JSON.parse(fs.readFileSync(path.join(electronRoot, 'package.json'), 'utf8'));
  if (rootPackage.scripts?.['electron:build'] !== 'pnpm --dir electron install --frozen-lockfile && pnpm --dir electron build') {
    throw new Error('root package.json must install electron deps before pnpm electron:build');
  }
  if (electronPackage.main !== 'main.mjs') {
    throw new Error('electron package must use main.mjs');
  }
}

verifyContract();

if (dryRun) {
  console.log('AVA Electron dry-run passed');
  process.exit(0);
}

if (!skipConsoleBuild) {
  run('npm', ['run', 'build'], { cwd: path.join(repoRoot, 'console-ui') });
}

run('bash', ['scripts/fetch-cloudflared.sh', 'darwin-arm64']);

const electronVersion = readInstalledElectronVersion();
const cachedElectronZipDir = findCachedElectronZipDir(electronDownloadCacheRoot, electronVersion);
const downloadArgs = cachedElectronZipDir
  ? [`--electron-zip-dir=${cachedElectronZipDir}`]
  : [`--download.cacheRoot=${electronDownloadCacheRoot}`];
const { manifestDir, manifestPath } = writeRuntimeManifest();

try {
  run(
    'pnpm',
    [
      'exec',
      'electron-packager',
      '.',
      'Ava',
      '--platform=darwin',
      '--arch=arm64',
      '--out=dist',
      '--overwrite',
      `--extra-resource=${manifestPath}`,
      ...downloadArgs,
    ],
    { cwd: electronRoot },
  );
} finally {
  fs.rmSync(manifestDir, { recursive: true, force: true });
}

const packagedApp = path.join(electronRoot, 'dist', 'Ava-darwin-arm64', 'Ava.app');
injectUrlScheme(packagedApp);
verifyPackagedApp(packagedApp);
run('codesign', ['--force', '--deep', '--sign', '-', packagedApp]);
run('codesign', ['--verify', '--deep', '--strict', '--verbose=1', packagedApp]);
