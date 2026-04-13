import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { createHash } from 'crypto';
import { writeFileSync, readdirSync, readFileSync, statSync } from 'fs';
import { join } from 'path';

const apiTarget = `http://localhost:${process.env.NANOBOT_CONSOLE_PORT || 6688}`;

function versionJsonPlugin(): Plugin {
  return {
    name: 'version-json',
    apply: 'build',
    closeBundle() {
      const distDir = join(__dirname, 'dist');
      const assetsDir = join(distDir, 'assets');
      const h = createHash('sha256');
      try {
        const files = readdirSync(assetsDir).sort();
        for (const f of files) {
          const fp = join(assetsDir, f);
          if (statSync(fp).isFile()) {
            h.update(f);
            h.update(readFileSync(fp));
          }
        }
      } catch {
        h.update('no-assets');
      }
      const hash = h.digest('hex').slice(0, 16);
      const data = {
        hash,
        timestamp: Math.floor(Date.now() / 1000),
        built_at: new Date().toISOString(),
      };
      writeFileSync(join(distDir, 'version.json'), JSON.stringify(data, null, 2));
    },
  };
}

export default defineConfig({
  define: {
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
    __BUILD_VERSION__: JSON.stringify(process.env.npm_package_version || '0.0.0'),
  },
  plugins: [react(), tailwindcss(), versionJsonPlugin()],
  server: {
    proxy: {
      '/api': {
        target: apiTarget,
        ws: true,
      },
    },
  },
});
