'use strict';
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const config = require(path.join(root, 'package.json')).build;
// Only the builder process uses this mask; generated Linux menu files must be readable.
if (process.platform === 'linux') process.umask(0o022);
config.afterPack = require('./linux-package-permissions.cjs');
const info = JSON.parse(fs.readFileSync(path.join(root, 'desktop/backend-dist/claude-sync-backend/build-info.json'), 'utf8'));
if (info.platform !== process.platform || info.arch !== process.arch) throw new Error('Rebuild the helper for the current operating system and architecture.');
if (process.platform === 'darwin') config.mac.minimumSystemVersion = info.minimumMacOS;
module.exports = config;
