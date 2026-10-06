'use strict';

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { WorkflowError } = require('./workflow.cjs');
const ACTIONS = new Set(['inspect', 'preflight', 'close', 'sync', 'open']);

function capture(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const process = spawn(command, args, {
      windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'], shell: false,
      env: { ...global.process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
      ...options,
    });
    const output = [];
    const errors = [];
    let bytes = 0;
    let exceeded = false;
    let timedOut = false;
    const timer = options.timeout ? setTimeout(() => { timedOut = true; process.kill(); }, options.timeout) : null;
    const collect = target => chunk => {
      bytes += chunk.length;
      if (bytes > 16 * 1024 * 1024) { exceeded = true; process.kill(); }
      else target.push(chunk);
    };
    process.stdout.on('data', collect(output));
    process.stderr.on('data', collect(errors));
    process.once('error', error => { if (timer) clearTimeout(timer); reject(error); });
    process.once('close', code => {
      if (timer) clearTimeout(timer);
      if (exceeded || timedOut) return reject(new WorkflowError('BACKEND_FAILED', 'The synchronization helper did not return a valid response.'));
      resolve({ code, output: Buffer.concat(output).toString('utf8'), error: Buffer.concat(errors).toString('utf8') });
    });
  });
}

async function findPython(platform = process.platform) {
  const candidates = process.env.CLAUDE_SYNC_PYTHON
    ? [[process.env.CLAUDE_SYNC_PYTHON, []]]
    : platform === 'win32' ? [['py', ['-3']], ['python', []]]
      : [['python3', []], ['/opt/homebrew/bin/python3', []], ['/usr/local/bin/python3', []], ['/usr/bin/python3', []]];
  for (const [executable, args] of candidates) {
    try {
      const result = await capture(executable, [...args, '-c', 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'], { timeout: 10000 });
      if (result.code === 0) return { executable, args };
    } catch { /* Try the next installed interpreter. */ }
  }
  throw new WorkflowError('PYTHON_NOT_FOUND', 'Install Python 3.10 or newer to run the app from source.');
}

class BackendClient {
  constructor({ packaged = false, resourcesPath = '', root = path.resolve(__dirname, '..'), settings = {}, preview = false } = {}) {
    this.packaged = packaged;
    this.resourcesPath = resourcesPath;
    this.root = root;
    this.settings = settings;
    this.preview = preview;
    this.runtime = null;
  }
  async command() {
    if (this.packaged) {
      const executable = path.join(this.resourcesPath, 'backend', process.platform === 'win32' ? 'claude-sync-backend.exe' : 'claude-sync-backend');
      if (!fs.existsSync(executable)) throw new WorkflowError('BACKEND_FAILED', 'The application is incomplete. Rebuild Claude Code User Sync.');
      return { executable, args: [] };
    }
    this.runtime ||= await findPython();
    return { ...this.runtime, args: [...this.runtime.args, path.join(this.root, 'desktop', 'backend.py')] };
  }
  async run(action) {
    if (!ACTIONS.has(action)) throw new WorkflowError('BACKEND_FAILED', 'Unknown synchronization action.');
    const command = await this.command();
    const args = [...command.args, action];
    if (this.preview && action === 'inspect') args.push('--accounts-only');
    for (const [key, flag] of [['appData', '--app-data'], ['projectsDir', '--projects-dir'], ['claudeExecutable', '--claude-executable']]) {
      if (typeof this.settings[key] === 'string' && this.settings[key]) args.push(flag, this.settings[key]);
    }
    let response;
    try {
      // A live sync has no timeout: it must finish or roll back its own writes.
      const result = await capture(command.executable, args);
      response = JSON.parse(result.output);
      if (response.ok === false) throw new WorkflowError(response.error?.code || 'BACKEND_FAILED', response.error?.message || 'Synchronization could not complete.');
      if (result.code !== 0 || response.ok !== true || !Object.hasOwn(response, 'value')) throw new Error('Invalid response');
    } catch (error) {
      if (error instanceof WorkflowError) throw error;
      throw new WorkflowError('BACKEND_FAILED', 'The synchronization helper did not return a valid response.');
    }
    return response.value;
  }
}
module.exports = { BackendClient, capture, findPython };
