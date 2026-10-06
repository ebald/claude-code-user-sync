'use strict';

class WorkflowError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}

class SyncWorkflow {
  constructor(backend, notify = () => {}) {
    this.backend = backend;
    this.notify = notify;
    this.running = false;
  }

  async run() {
    if (this.running) throw new WorkflowError('SYNC_BUSY', 'Another synchronization is already running.');
    this.running = true;
    let closed = false;
    let saved = null;
    try {
      await this.backend.run('preflight');
      this.notify('closing');
      await this.backend.run('close');
      closed = true;
      this.notify('syncing');
      saved = await this.backend.run('sync');
      this.notify('reopening', saved);
      try {
        await this.backend.run('open');
        return { saved, error: null };
      } catch (error) {
        return { saved, error: new WorkflowError(error.code === 'SYNC_BUSY' ? 'SYNC_BUSY' : 'OPEN_FAILED', error.message) };
      }
    } catch (error) {
      // A busy backend may be writing. Leave Claude closed until it finishes.
      if (closed && error.code !== 'SYNC_BUSY') {
        this.notify('reopening');
        try { await this.backend.run('open'); } catch { /* Keep the original failure. */ }
      }
      throw error;
    } finally {
      this.running = false;
    }
  }
}

module.exports = { SyncWorkflow, WorkflowError };
