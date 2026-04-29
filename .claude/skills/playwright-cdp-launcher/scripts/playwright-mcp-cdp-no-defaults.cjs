'use strict';

const fs = require('fs');
const Module = require('module');
const path = require('path');

const target = path.resolve(
  '/Users/fanghu/.local/share/mcp-runners/node_modules/playwright-core/lib/coreBundle.js',
);
const originalLoader = Module._extensions['.js'];

Module._extensions['.js'] = function loadWithCdpNoDefaults(module, filename) {
  if (path.resolve(filename) !== target) {
    return originalLoader(module, filename);
  }

  let source = fs.readFileSync(filename, 'utf8');
  const patched = source.replace(
    /(playwright\.chromium\.connectOverCDP\(config\.browser\.cdpEndpoint,\s*\{\s*headers: config\.browser\.cdpHeaders,\s*timeout: config\.browser\.cdpTimeout)(\s*\}\);)/,
    '$1,\n    noDefaults: true$2',
  );

  if (patched === source) {
    process.stderr.write('[playwright-cdp] noDefaults shim did not match coreBundle.js\n');
  } else {
    source = patched;
  }

  module._compile(source, filename);
};
