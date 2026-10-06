'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const shell = process.platform === 'win32' ? 'powershell.exe' : 'pwsh';
const available = spawnSync(shell, ['-NoLogo', '-NoProfile', '-Command', '$PSVersionTable.PSVersion.ToString()'], { encoding: 'utf8', timeout: 30000 });
test('Windows setup protects read-only checks and verifies automatic installation before launching', { skip: available.error ? 'PowerShell is not installed on this host.' : false }, () => {
  const file = path.resolve(__dirname, '../../scripts/tests/setup-windows.test.ps1');
  const args = ['-NoLogo', '-NoProfile'];
  if (process.platform === 'win32') args.push('-ExecutionPolicy', 'Bypass');
  args.push('-File', file);
  const result = spawnSync(shell, args, { encoding: 'utf8', timeout: 60000 });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stdout, /Windows setup regressions passed/);
});
