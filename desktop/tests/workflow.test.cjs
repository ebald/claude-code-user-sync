'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { SyncWorkflow, WorkflowError } = require('../workflow.cjs');

function fixture(fail = {}) {
  const calls = [];
  const saved = { result: { accounts: 2, chats: 3, backup: 'synthetic/backup' }, date: '2026-10-06T00:00:00Z', saveError: null };
  const backend = { async run(action) { calls.push(action); if (fail[action]) throw new WorkflowError(fail[action], 'Synthetic failure'); return action === 'sync' ? saved : {}; } };
  const phases = [];
  return { calls, saved, phases, workflow: new SyncWorkflow(backend, phase => phases.push(phase)) };
}
test('success closes, synchronizes, reopens, and retains the saved result', async () => {
  const f = fixture();
  const result = await f.workflow.run();
  assert.equal(result.saved, f.saved);
  assert.equal(result.error, null);
  assert.deepEqual(f.calls, ['preflight', 'close', 'sync', 'open']);
  assert.deepEqual(f.phases, ['closing', 'syncing', 'reopening']);
});
test('preflight failure leaves Claude and catalogs untouched', async () => {
  const f = fixture({ preflight: 'NO_CHATS' });
  await assert.rejects(f.workflow.run(), { code: 'NO_CHATS' });
  assert.deepEqual(f.calls, ['preflight']);
});
test('incomplete shutdown never invokes a write', async () => {
  const f = fixture({ close: 'CLOSE_FAILED' });
  await assert.rejects(f.workflow.run(), { code: 'CLOSE_FAILED' });
  assert.deepEqual(f.calls, ['preflight', 'close']);
});
test('sync failure attempts to reopen and preserves the primary error', async () => {
  const f = fixture({ sync: 'SYNC_FAILED', open: 'OPEN_FAILED' });
  await assert.rejects(f.workflow.run(), { code: 'SYNC_FAILED' });
  assert.deepEqual(f.calls, ['preflight', 'close', 'sync', 'open']);
  assert.equal(f.workflow.running, false);
});
test('busy shared backend leaves Claude closed', async () => {
  const f = fixture({ sync: 'SYNC_BUSY' });
  await assert.rejects(f.workflow.run(), { code: 'SYNC_BUSY' });
  assert.deepEqual(f.calls, ['preflight', 'close', 'sync']);
});
test('reopening failure retains completed sync and backup', async () => {
  const f = fixture({ open: 'OPEN_FAILED' });
  const result = await f.workflow.run();
  assert.equal(result.saved, f.saved);
  assert.equal(result.error.code, 'OPEN_FAILED');
  assert.equal(f.calls.filter(x => x === 'sync').length, 1);
});
test('another writer taking the lock before reopening retains the completed result', async () => {
  const f = fixture({ open: 'SYNC_BUSY' });
  const result = await f.workflow.run();
  assert.equal(result.saved, f.saved);
  assert.equal(result.error.code, 'SYNC_BUSY');
  assert.equal(f.calls.filter(x => x === 'sync').length, 1);
});
test('one workflow cannot start a second write concurrently', async () => {
  let release;
  const blocked = new Promise(resolve => { release = resolve; });
  const workflow = new SyncWorkflow({ async run(action) { if (action === 'preflight') await blocked; return { result: {}, date: 'now' }; } });
  const first = workflow.run();
  await assert.rejects(workflow.run(), { code: 'SYNC_BUSY' });
  release();
  await first;
});
