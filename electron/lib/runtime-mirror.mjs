import fs from 'node:fs';
import path from 'node:path';

const MIRROR_DIR_NAME = 'runtime-mirror';
const MIRROR_VERSION = 2;
const SITE_PACKAGES_EXCLUDES = new Set(['bridge', 'console-ui']);

function removePath(target) {
  if (!fs.existsSync(target)) {
    return;
  }
  fs.rmSync(target, { recursive: true, force: true });
}

function copyEntry(source, target) {
  const stat = fs.lstatSync(source);
  if (stat.isSymbolicLink()) {
    fs.mkdirSync(path.dirname(target), { recursive: true });
    removePath(target);
    fs.symlinkSync(fs.readlinkSync(source), target);
    return;
  }
  if (stat.isDirectory()) {
    fs.mkdirSync(target, { recursive: true });
    fs.chmodSync(target, stat.mode);
    for (const entry of fs.readdirSync(source)) {
      copyEntry(path.join(source, entry), path.join(target, entry));
    }
    return;
  }
  if (stat.isFile()) {
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, fs.readFileSync(source));
    fs.chmodSync(target, stat.mode);
  }
}

function copyTree(source, target) {
  if (!fs.existsSync(source)) {
    throw new Error(`runtime mirror source not found: ${source}`);
  }
  removePath(target);
  copyEntry(source, target);
}

function copyOptionalTree(source, target) {
  if (!fs.existsSync(source)) {
    return;
  }
  copyTree(source, target);
}

function copyFile(source, target) {
  if (!fs.existsSync(source)) {
    throw new Error(`runtime mirror source not found: ${source}`);
  }
  removePath(target);
  copyEntry(source, target);
}

function copySitePackages(source, target) {
  if (!fs.existsSync(source)) {
    throw new Error(`runtime mirror source not found: ${source}`);
  }
  removePath(target);
  fs.mkdirSync(target, { recursive: true });
  for (const entry of fs.readdirSync(source)) {
    if (SITE_PACKAGES_EXCLUDES.has(entry)) {
      continue;
    }
    copyTree(path.join(source, entry), path.join(target, entry));
  }
}

function pythonVersion(pythonExecutable) {
  const match = path.basename(pythonExecutable).match(/^python(\d+\.\d+)$/);
  if (!match) {
    throw new Error(`cannot derive Python version from executable: ${pythonExecutable}`);
  }
  return match[1];
}

function sourceStamp(source) {
  const stat = fs.statSync(source);
  return {
    source: path.resolve(source),
    mtimeMs: stat.mtimeMs,
    size: stat.size,
  };
}

function sameStamp(left, right) {
  return Boolean(
    left
    && left.source === right.source
    && left.mtimeMs === right.mtimeMs
    && left.size === right.size,
  );
}

function readMeta(metaPath) {
  try {
    const parsed = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

export function runtimeMirrorPaths(appDataPath, pythonExecutable) {
  const root = path.join(appDataPath, MIRROR_DIR_NAME, 'current');
  const pythonMinor = pythonVersion(pythonExecutable);
  return {
    root,
    nanobotRoot: path.join(root, 'nanobot-checkout'),
    sitePackages: path.join(root, '.venv', 'lib', `python${pythonMinor}`, 'site-packages'),
    metaPath: path.join(root, '.runtime-mirror.json'),
  };
}

export function prepareRuntimeMirror({ appDataPath, repoRoot, nanobotRoot, pythonExecutable }) {
  const paths = runtimeMirrorPaths(appDataPath, pythonExecutable);
  const meta = readMeta(paths.metaPath);
  const effectiveNanobotRoot = path.basename(repoRoot) === 'ava-runtime'
    ? path.join(repoRoot, 'nanobot-checkout')
    : nanobotRoot;
  const sourceSitePackages = path.join(
    repoRoot,
    '.venv',
    'lib',
    `python${pythonVersion(pythonExecutable)}`,
    'site-packages',
  );
  const siteStamp = sourceStamp(sourceSitePackages);

  fs.mkdirSync(paths.root, { recursive: true });
  copyTree(path.join(repoRoot, 'ava'), path.join(paths.root, 'ava'));
  copyTree(path.join(effectiveNanobotRoot, 'nanobot'), path.join(paths.nanobotRoot, 'nanobot'));
  copyFile(path.join(effectiveNanobotRoot, 'pyproject.toml'), path.join(paths.nanobotRoot, 'pyproject.toml'));
  copyOptionalTree(path.join(repoRoot, 'console-ui', 'dist'), path.join(paths.root, 'console-ui', 'dist'));
  copyOptionalTree(path.join(repoRoot, 'vendor', 'cloudflared'), path.join(paths.root, 'vendor', 'cloudflared'));

  if (meta.version !== MIRROR_VERSION || !sameStamp(meta.sitePackages, siteStamp) || !fs.existsSync(paths.sitePackages)) {
    copySitePackages(sourceSitePackages, paths.sitePackages);
  }

  fs.writeFileSync(
    paths.metaPath,
    JSON.stringify({
      version: MIRROR_VERSION,
      sourceRepoRoot: path.resolve(repoRoot),
      sourceNanobotRoot: path.resolve(nanobotRoot),
      sitePackages: siteStamp,
      updatedAt: new Date().toISOString(),
    }, null, 2),
  );

  return {
    repoRoot: paths.root,
    nanobotRoot: paths.nanobotRoot,
    sitePackages: paths.sitePackages,
  };
}
