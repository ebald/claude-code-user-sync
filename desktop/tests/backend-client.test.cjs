'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { capture, BackendClient } = require('../backend-client.cjs');
test('the helper reader drains stdout and stderr concurrently', async () => {
  const output = await capture(process.execPath, ['-e', "process.stdout.write('a'.repeat(2e6)); process.stderr.write('b'.repeat(2e6));"]);
  assert.equal(output.code, 0);
  assert.equal(output.output.length, 2e6);
  assert.equal(output.error.length, 2e6);
});
test('only documented backend actions can be launched', async () => {
  const backend = new BackendClient();
  await assert.rejects(backend.run('arbitrary-program'), { code: 'BACKEND_FAILED' });
});
test('an unavailable interpreter fails as a rejected launch', async () => {
  await assert.rejects(capture('nonexistent-synthetic-executable-claude-sync', []), { code: 'ENOENT' });
});
