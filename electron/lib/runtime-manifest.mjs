import fs from 'node:fs';
import path from 'node:path';

export const RUNTIME_MANIFEST_NAME = 'ava-runtime-manifest.json';

export function isAvaRepoRoot(root) {
  return Boolean(
    root
    && typeof root === 'string'
    && fs.existsSync(path.join(path.resolve(root), 'scripts', 'start-ava.sh')),
  );
}

export function runtimeManifestPaths(moduleDir, env = process.env) {
  return [
    env.AVA_RUNTIME_MANIFEST,
    typeof process.resourcesPath === 'string'
      ? path.join(process.resourcesPath, RUNTIME_MANIFEST_NAME)
      : '',
    moduleDir ? path.join(moduleDir, RUNTIME_MANIFEST_NAME) : '',
  ].filter(Boolean);
}

export function readRuntimeManifestRepoRoot(paths) {
  for (const manifestPath of paths) {
    if (!fs.existsSync(manifestPath)) {
      continue;
    }
    try {
      const parsed = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
      const repoRoot = typeof parsed?.repoRoot === 'string' ? path.resolve(parsed.repoRoot) : '';
      if (isAvaRepoRoot(repoRoot)) {
        return repoRoot;
      }
    } catch {
      // Ignore bad manifests; startup will still fail visibly if no repo root is found.
    }
  }
  return null;
}
