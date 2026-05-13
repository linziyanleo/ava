import fs from 'node:fs';
import path from 'node:path';

const REQUIRED_NANOBOT_FILES = [
  'pyproject.toml',
  path.join('nanobot', '__main__.py'),
  path.join('nanobot', 'cli', 'commands.py'),
];

export function desktopConfigPath(appDataPath) {
  if (typeof appDataPath !== 'string' || appDataPath.length === 0) {
    throw new Error('appDataPath is required');
  }
  return path.join(appDataPath, 'Ava', 'desktop.json');
}

export function readDesktopConfig(appDataPath) {
  const filePath = desktopConfigPath(appDataPath);
  if (!fs.existsSync(filePath)) {
    return {};
  }
  let parsed = null;
  try {
    parsed = JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return {};
  }
  return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
}

export function writeDesktopConfig(appDataPath, config) {
  const filePath = desktopConfigPath(appDataPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(config, null, 2)}\n`, 'utf8');
}

export function validateNanobotRoot(root) {
  if (typeof root !== 'string' || !path.isAbsolute(root)) {
    return { ok: false, error: 'nanobot root must be an absolute path' };
  }
  const missing = REQUIRED_NANOBOT_FILES.filter((relativePath) => !fs.existsSync(path.join(root, relativePath)));
  if (missing.length > 0) {
    return { ok: false, error: `missing ${missing.join(', ')}` };
  }
  return { ok: true };
}

export function resolveNanobotCandidate({ repoRoot, appDataPath, env = process.env }) {
  if (env.AVA_NANOBOT_ROOT) {
    return path.resolve(env.AVA_NANOBOT_ROOT);
  }
  const desktopConfig = readDesktopConfig(appDataPath);
  if (typeof desktopConfig.nanobotRoot === 'string' && desktopConfig.nanobotRoot) {
    return path.resolve(desktopConfig.nanobotRoot);
  }
  return path.resolve(repoRoot, '..', 'nanobot');
}

export function saveNanobotRoot(appDataPath, root, now = new Date().toISOString()) {
  if (typeof root !== 'string') {
    return { ok: false, error: 'nanobot root must be an absolute path' };
  }
  const resolved = path.resolve(root);
  const validation = validateNanobotRoot(resolved);
  if (!validation.ok) {
    return { ok: false, error: validation.error };
  }
  const previous = readDesktopConfig(appDataPath);
  writeDesktopConfig(appDataPath, {
    ...previous,
    nanobotRoot: resolved,
    createdAt: previous.createdAt || now,
    updatedAt: now,
  });
  return { ok: true, nanobotRoot: resolved };
}
