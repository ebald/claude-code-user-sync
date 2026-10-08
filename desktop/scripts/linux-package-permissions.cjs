'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');
const { randomUUID } = require('node:crypto');

async function normalize(target, root = false) {
  const info = await fs.lstat(target);
  if (info.isSymbolicLink()) {
    if (root) throw new Error('The Linux packaged application directory must not be a symbolic link.');
    return;
  }
  if (root && !info.isDirectory()) throw new Error('The Linux packaged application must be a directory.');
  if (info.isDirectory()) {
    await fs.chmod(target, 0o755);
    for (const name of await fs.readdir(target)) await normalize(path.join(target, name));
    return;
  }
  if (!info.isFile()) return;
  // electron-builder's Linux installer manages the Chromium sandbox mode.
  if (path.basename(target) === 'chrome-sandbox') return;
  const mode = info.mode & 0o111 ? 0o755 : 0o644;
  if ((info.mode & 0o7777) === mode) return;
  if (info.nlink === 1) {
    await fs.chmod(target, mode);
    return;
  }
  // Detach shared files before changing permissions; never chmod build sources.
  const temporary = target + '.' + randomUUID() + '.tmp';
  try {
    await fs.copyFile(target, temporary, fs.constants.COPYFILE_EXCL);
    await fs.chmod(temporary, mode);
    await fs.rename(temporary, target);
  } finally {
    await fs.rm(temporary, { force: true });
  }
}

module.exports = async function linuxPackagePermissions(context) {
  if (context.electronPlatformName !== 'linux') return;
  await normalize(context.appOutDir, true);
  const resources = path.join(context.appOutDir, 'resources');
  const info = await fs.lstat(resources);
  if (!info.isDirectory() || info.isSymbolicLink()) throw new Error('The Linux packaged resources must be a directory, not a symbolic link.');
  const icon = path.join(resources, 'package-icon.png');
  try {
    if ((await fs.lstat(icon)).isSymbolicLink()) throw new Error('The Linux packaged icon must not be a symbolic link.');
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  const temporary = icon + '.' + randomUUID() + '.tmp';
  try {
    await fs.copyFile(path.resolve(context.packager.projectDir, context.packager.config.icon), temporary, fs.constants.COPYFILE_EXCL);
    await fs.chmod(temporary, 0o644);
    await fs.rename(temporary, icon);
  } finally {
    await fs.rm(temporary, { force: true });
  }
  // FPM resolves icons after afterPack, and uses existing PNG inputs directly.
  // Point it at a readable copy rather than changing the source icon's mode.
  context.packager.platformSpecificBuildOptions.icon = icon;
};
