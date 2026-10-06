'use strict';
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const target = path.join(root, 'desktop/renderer/vendor');
fs.mkdirSync(target, { recursive: true });
const packageRoot = path.dirname(require.resolve('i18next/package.json'));
fs.copyFileSync(path.join(packageRoot, 'dist/umd/i18next.js'), path.join(target, 'i18next.js'));
require('node:child_process').execFileSync(process.execPath, [path.join(root, 'desktop/renderer/build-translations.cjs')], { stdio: 'inherit' });
