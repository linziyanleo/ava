import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const electronRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(electronRoot, '..');
const dryRun = process.argv.includes('--dry-run');
const skipConsoleBuild = process.argv.includes('--skip-console-build');

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

function verifyContract() {
  [
    'electron/main.mjs',
    'electron/preload.cjs',
    'electron/bin/ava-core',
    'console-ui/package.json',
    'scripts/start-ava.sh',
    'package.json',
  ].forEach(assertPath);

  const rootPackage = JSON.parse(fs.readFileSync(path.join(repoRoot, 'package.json'), 'utf8'));
  const electronPackage = JSON.parse(fs.readFileSync(path.join(electronRoot, 'package.json'), 'utf8'));
  if (rootPackage.scripts?.['electron:build'] !== 'pnpm --dir electron build') {
    throw new Error('root package.json must expose pnpm electron:build');
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
    '--asar=false',
  ],
  { cwd: electronRoot },
);
