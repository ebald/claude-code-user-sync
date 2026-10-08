'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { spawnSync } = require('node:child_process');
const { PlatformPackager } = require('app-builder-lib');
const { LinuxTargetHelper } = require('app-builder-lib/out/targets/LinuxTargetHelper');
const hook = require('../scripts/linux-package-permissions.cjs');
const unix = (name, run) => test(name, { skip: process.platform === 'win32' }, run);
const mode = target => fs.statSync(target).mode & 0o7777;

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-sync-permissions-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

function context(root, app) {
  const sourceIcon = path.join(root, 'source-icon.png');
  fs.copyFileSync(path.resolve(__dirname, '../assets/icon.png'), sourceIcon);
  fs.chmodSync(sourceIcon, 0o600);
  return { electronPlatformName: 'linux', appOutDir: app, packager: {
    projectDir: root, buildResourcesDir: root,
    config: { icon: sourceIcon, directories: { output: 'release' } },
    platformSpecificBuildOptions: {},
    getDefaultFrameworkIcon: () => null,
    expandMacro: value => value,
    resolveIcon: PlatformPackager.prototype.resolveIcon,
  } };
}

unix('Linux package remains accessible with restrictive build permissions without following symlinks', async t => {
  const root = fixture(t);
  const app = path.join(root, 'linux-arm64-unpacked');
  const backend = path.join(app, 'resources', 'backend');
  fs.mkdirSync(backend, { recursive: true, mode: 0o700 });
  for (const directory of [app, path.dirname(backend), backend]) fs.chmodSync(directory, 0o700);
  const data = path.join(backend, 'build-info.json');
  const executable = path.join(backend, 'claude-sync-backend');
  const electron = path.join(app, 'claude-code-user-sync');
  const sandbox = path.join(app, 'chrome-sandbox');
  fs.writeFileSync(data, '{"platform":"linux"}', { mode: 0o600 });
  fs.writeFileSync(executable, 'backend', { mode: 0o700 });
  fs.writeFileSync(electron, 'electron', { mode: 0o755 });
  fs.writeFileSync(sandbox, 'sandbox', { mode: 0o755 });
  fs.chmodSync(sandbox, 0o4755);
  const outside = path.join(root, 'private-source');
  fs.mkdirSync(outside, { mode: 0o700 });
  const privateFile = path.join(outside, 'private.json');
  fs.writeFileSync(privateFile, 'private', { mode: 0o600 });
  fs.symlinkSync(outside, path.join(app, 'outside-directory'));
  fs.symlinkSync(privateFile, path.join(backend, 'outside-file'));
  fs.symlinkSync('missing', path.join(app, 'broken-link'));
  const build = context(root, app);
  const helper = new LinuxTargetHelper(build.packager);

  await hook(build);

  for (const directory of [app, path.dirname(backend), backend]) assert.equal(mode(directory), 0o755);
  assert.equal(mode(data), 0o644);
  assert.equal(mode(executable), 0o755);
  assert.equal(mode(electron), 0o755);
  assert.equal(mode(sandbox), 0o4755);
  assert.equal(mode(outside), 0o700);
  assert.equal(mode(privateFile), 0o600);
  assert.equal(mode(root), 0o700);
  assert.equal(fs.readlinkSync(path.join(app, 'outside-directory')), outside);
  assert.equal(fs.readlinkSync(path.join(backend, 'outside-file')), privateFile);
  assert.equal(fs.readlinkSync(path.join(app, 'broken-link')), 'missing');
  assert.equal(fs.readFileSync(data, 'utf8'), '{"platform":"linux"}');
  assert.equal(mode(build.packager.config.icon), 0o600);
  const icons = await helper.icons;
  assert.equal(icons.length, 1);
  assert.equal(icons[0].file, path.join(app, 'resources', 'package-icon.png'));
  assert.equal(mode(icons[0].file), 0o644);
  assert.deepEqual(fs.readFileSync(icons[0].file), fs.readFileSync(build.packager.config.icon));
});

unix('Linux package detaches hard links before changing shared source permissions', async t => {
  const root = fixture(t);
  const app = path.join(root, 'linux-unpacked');
  fs.mkdirSync(path.join(app, 'resources'), { recursive: true, mode: 0o700 });
  const source = path.join(root, 'source.json');
  const output = path.join(app, 'output.json');
  fs.writeFileSync(source, 'shared content', { mode: 0o600 });
  fs.linkSync(source, output);

  await hook(context(root, app));

  assert.equal(mode(source), 0o600);
  assert.equal(mode(output), 0o644);
  assert.notEqual(fs.statSync(source).ino, fs.statSync(output).ino);
  assert.equal(fs.readFileSync(output, 'utf8'), 'shared content');
  assert.deepEqual(fs.readdirSync(app).sort(), ['output.json', 'resources']);
});

unix('Linux package refuses a linked application root without modifying its target', async t => {
  const root = fixture(t);
  const target = path.join(root, 'source');
  const linked = path.join(root, 'linux-unpacked');
  fs.mkdirSync(target, { mode: 0o700 });
  fs.symlinkSync(target, linked);
  await assert.rejects(hook({ electronPlatformName: 'linux', appOutDir: linked }), /must not be a symbolic link/);
  assert.equal(mode(target), 0o700);
});

unix('Linux package preserves linked resource and icon paths without modifying external files', async t => {
  const root = fixture(t);
  const app = path.join(root, 'linux-unpacked');
  const outside = path.join(root, 'private');
  fs.mkdirSync(app, { mode: 0o700 });
  fs.mkdirSync(outside, { mode: 0o700 });
  const privateIcon = path.join(outside, 'icon.png');
  fs.writeFileSync(privateIcon, 'private', { mode: 0o600 });
  const resources = path.join(app, 'resources');
  fs.symlinkSync(outside, resources);
  await assert.rejects(hook(context(root, app)), /resources must be a directory/);
  assert.equal(fs.readlinkSync(resources), outside);
  assert.equal(mode(outside), 0o700);
  assert.equal(mode(privateIcon), 0o600);
  fs.unlinkSync(resources);
  fs.mkdirSync(resources, { mode: 0o700 });
  const copiedIcon = path.join(resources, 'package-icon.png');
  fs.symlinkSync(privateIcon, copiedIcon);
  await assert.rejects(hook(context(root, app)), /icon must not be a symbolic link/);
  assert.equal(fs.readlinkSync(copiedIcon), privateIcon);
  assert.equal(mode(privateIcon), 0o600);
});

test('the permissions hook leaves macOS and Windows builds untouched', async () => {
  // A non-Linux invocation must return without even inspecting the output path.
  for (const electronPlatformName of ['darwin', 'win32']) {
    await hook({ electronPlatformName, appOutDir: path.join(os.tmpdir(), 'does-not-exist', 'app') });
  }
});

test('electron-builder configuration wires the output permissions hook', () => {
  const scriptDir = path.resolve(__dirname, '../scripts');
  const source = fs.readFileSync(path.join(scriptDir, 'builder-config.cjs'), 'utf8');
  const metadataPath = path.resolve(scriptDir, '../backend-dist/claude-sync-backend/build-info.json');
  const packagePath = path.resolve(scriptDir, '../../package.json');
  for (const platform of ['linux', 'darwin', 'win32']) {
    const config = { linux: { executableName: 'claude-code-user-sync' }, mac: {} };
    const module = { exports: {} };
    const masks = [];
    vm.runInNewContext(source, {
      __dirname: scriptDir, module, process: { platform, arch: 'arm64', umask: value => masks.push(value) },
      require(name) {
        if (name === 'node:path') return path;
        if (name === 'node:fs') return { readFileSync(target) {
          assert.equal(target, metadataPath);
          return JSON.stringify({ platform, arch: 'arm64', minimumMacOS: '13.0' });
        } };
        if (name === packagePath) return { build: config };
        if (name === './linux-package-permissions.cjs') return hook;
        throw new Error('Unexpected build dependency: ' + name);
      },
    });
    assert.equal(module.exports.afterPack, hook);
    assert.equal(module.exports.linux.executableName, 'claude-code-user-sync');
    assert.deepEqual(masks, platform === 'linux' ? [0o022] : []);
  }
});

unix('Linux builder generates readable menu metadata without changing the caller mask', t => {
  const root = fixture(t);
  const configPath = path.resolve(__dirname, '../scripts/builder-config.cjs');
  const originalMask = process.umask();
  const child = spawnSync(process.execPath, ['-e', `
    const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
    process.umask(0o077);
    const configPath = process.argv[1], output = process.argv[2];
    const scriptDir = path.dirname(configPath);
    const metadataPath = path.resolve(scriptDir, '../backend-dist/claude-sync-backend/build-info.json');
    const packagePath = path.resolve(scriptDir, '../../package.json');
    vm.runInNewContext(fs.readFileSync(configPath, 'utf8'), {
      __dirname: scriptDir, module: { exports: {} },
      process: { platform: 'linux', arch: 'arm64', umask: process.umask.bind(process) },
      require(name) {
        if (name === 'node:path') return path;
        if (name === 'node:fs') return { readFileSync(target) {
          if (target !== metadataPath) throw new Error('Unexpected metadata path');
          return JSON.stringify({ platform: 'linux', arch: 'arm64' });
        } };
        if (name === packagePath) return { build: { linux: {} } };
        if (name === './linux-package-permissions.cjs') return () => {};
        throw new Error('Unexpected dependency');
      },
    });
    fs.mkdirSync(path.join(output, 'applications'));
    fs.writeFileSync(path.join(output, 'applications', 'app.desktop'), '[Desktop Entry]');
    console.log(JSON.stringify({ directory: fs.statSync(path.join(output, 'applications')).mode & 0o777,
      desktop: fs.statSync(path.join(output, 'applications', 'app.desktop')).mode & 0o777 }));
  `, configPath, root], { encoding: 'utf8' });
  assert.equal(child.status, 0, child.stderr);
  assert.deepEqual(JSON.parse(child.stdout), { directory: 0o755, desktop: 0o644 });
  assert.equal(process.umask(), originalMask);
});
