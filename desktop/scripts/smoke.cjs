'use strict';
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
let executable;
let args;
if (process.argv.includes('--packaged')) {
  const directory = process.platform === 'win32' ? 'win-unpacked' : process.arch === 'arm64' ? 'mac-arm64' : 'mac';
  executable = process.platform === 'win32'
    ? path.join(root, 'release', directory, 'Claude Code User Sync.exe')
    : path.join(root, 'release', directory, 'Claude Code User Sync.app/Contents/MacOS/Claude Code User Sync');
  args = ['--preview', '--smoke-test'];
} else {
  executable = require('electron');
  args = [root, '--preview', '--smoke-test'];
}
if (!fs.existsSync(executable)) { console.error('Build the application before checking it.'); process.exit(1); }
const child = spawn(executable, args, { stdio: ['ignore', 'pipe', 'pipe'], windowsHide: false, shell: false });
let passed = false;
child.stdout.on('data', chunk => { const text = chunk.toString(); process.stdout.write(text); if (text.includes('"smoke":"passed"')) passed = true; });
child.stderr.on('data', chunk => process.stderr.write(chunk));
const timer = setTimeout(() => { child.kill(); console.error('Preview check timed out.'); process.exitCode = 1; }, 60000);
child.on('error', error => { clearTimeout(timer); console.error(error.message); process.exitCode = 1; });
child.on('close', code => { clearTimeout(timer); process.exitCode = code === 0 && passed ? 0 : 1; });
