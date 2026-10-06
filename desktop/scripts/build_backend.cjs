'use strict';
const path = require('node:path');
const { spawn } = require('node:child_process');
const { findPython } = require('../backend-client.cjs');
async function main() {
  const args = process.argv.slice(2);
  if (args.length && (args.length !== 2 || args[0] !== '--platform')) throw new Error('Usage: build_backend.cjs [--platform darwin|win32|linux]');
  const target = args[1] || process.platform;
  if (!['darwin', 'win32', 'linux'].includes(target) || target !== process.platform) throw new Error('Build each application on its target operating system.');
  if (!['arm64', 'x64'].includes(process.arch)) throw new Error('Build using x64 or arm64 Node.js and Python.');
  if (target === 'win32' && process.arch !== 'x64') throw new Error('Build the Windows x64 installer using x64 Node.js and Python.');
  const runtime = await findPython();
  const script = path.join(__dirname, 'build_backend.py');
  const child = spawn(runtime.executable, [...runtime.args, script, '--arch', process.arch], { stdio: 'inherit', shell: false });
  child.on('error', error => { console.error(error.message); process.exitCode = 1; });
  child.on('close', code => { process.exitCode = code ?? 1; });
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
