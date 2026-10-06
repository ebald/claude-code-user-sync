'use strict';

const { app, BrowserWindow, Menu, ipcMain, dialog, shell, screen, nativeImage } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { pathToFileURL } = require('node:url');
const { BackendClient } = require('./backend-client.cjs');
const { SyncWorkflow, WorkflowError } = require('./workflow.cjs');

app.setName('Claude Code User Sync');
app.setPath('userData', path.join(app.getPath('appData'), app.name));
const preview = process.argv.includes('--preview');
const smoke = process.argv.includes('--smoke-test');
if (smoke && !preview) app.exit(2);
const languages = new Set(['en', 'es', 'pt-BR']);
const entry = path.join(__dirname, 'renderer', 'index.html');
const entryURL = pathToFileURL(entry).href;
const settingsFile = path.join(app.getPath('userData'), 'settings.json');
let settings = {};
let window;
let backend;
let operationBusy = false;
let storageDir = null;
const state = { preview, language: 'en', accounts: null, phase: 'ready', running: false,
  lastSync: null, error: null, notice: null };

function checkNoLinks(target) {
  let current = path.resolve(target);
  for (;;) {
    try { if (fs.lstatSync(current).isSymbolicLink()) throw new Error('Linked path'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    const parent = path.dirname(current);
    if (parent === current) return;
    current = parent;
  }
}

function loadSettings() {
  if (preview) return;
  try {
    checkNoLinks(settingsFile);
    const value = JSON.parse(fs.readFileSync(settingsFile, 'utf8'));
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      for (const key of ['language', 'appData', 'projectsDir', 'claudeExecutable']) {
        if (typeof value[key] === 'string') settings[key] = value[key];
      }
    }
  } catch { /* Fresh or unreadable preferences use the defaults. */ }
  state.language = languages.has(settings.language) ? settings.language : 'en';
}

function saveSettings() {
  if (preview) return;
  let temporary;
  try {
    checkNoLinks(settingsFile);
    fs.mkdirSync(path.dirname(settingsFile), { recursive: true, mode: 0o700 });
    temporary = settingsFile + '.' + crypto.randomUUID() + '.tmp';
    fs.writeFileSync(temporary, JSON.stringify(settings, null, 2) + '\n', { mode: 0o600, flag: 'wx' });
    fs.renameSync(temporary, settingsFile);
  } catch {
    state.notice = 'SETTINGS_FAILED';
  } finally {
    if (temporary) { try { fs.unlinkSync(temporary); } catch { /* Already moved. */ } }
  }
}

function publish() {
  if (window && !window.isDestroyed()) window.webContents.send('sync:changed', state);
  return structuredClone(state);
}

function errorState(error) {
  state.error = { code: error.code || 'BACKEND_FAILED', message: error.message || 'The operation could not complete.' };
  state.phase = 'error';
  return publish();
}

async function refresh() {
  const value = await backend.run('inspect');
  storageDir = value.storageDir;
  state.accounts = Number.isSafeInteger(value.accounts) && value.accounts >= 0 ? value.accounts : null;
  if (!preview) {
    state.lastSync = value.lastSync;
    state.phase = state.lastSync ? 'done' : 'ready';
  }
}

function menu() {
  const locale = JSON.parse(fs.readFileSync(path.join(__dirname, 'locales', state.language + '.json'), 'utf8'));
  const labels = locale.menu || {};
  const item = (role, key) => ({ role, label: labels[key] || key });
  const template = [];
  if (process.platform === 'darwin') template.push({ label: app.name, submenu: [item('about', 'about'), { type: 'separator' }, item('quit', 'quit')] });
  template.push({ label: labels.edit || 'Edit', submenu: [item('undo', 'undo'), item('redo', 'redo'), { type: 'separator' },
    item('cut', 'cut'), item('copy', 'copy'), item('paste', 'paste'), item('selectAll', 'selectAll')] });
  template.push({ label: labels.window || 'Window', submenu: [item('minimize', 'minimize'), item('close', 'close'),
    ...(process.platform === 'darwin' ? [] : [{ type: 'separator' }, item('quit', 'quit')])] });
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function authorized(event) {
  if (!window || event.sender !== window.webContents || event.senderFrame !== event.sender.mainFrame || event.senderFrame.url !== entryURL) {
    throw new Error('Untrusted application frame');
  }
}

function handle(channel, action, { idle = false } = {}) {
  ipcMain.handle(channel, async (event, ...args) => {
    authorized(event);
    if (idle && operationBusy) return publish();
    try { return await action(...args); }
    catch (error) { return errorState(error); }
  });
}

function sampleBackend() {
  return { async run(action) {
    await new Promise(resolve => setTimeout(resolve, smoke ? 10 : 550));
    if (action === 'sync') return { date: new Date().toISOString(), saveError: null, result: {
      accounts: state.accounts ?? 0, chats: 70, projects: 15, conflicts: 0, missing_transcripts: 0,
      assets: { diagnostic_version: 2, artifact_references: 8, local_files: 12, local_images: 3, embedded_images: 2,
        missing_output_files: 1, unpreserved_output_files: 1, preserved_output_files: 0 }, backup: '' } };
    return {};
  } };
}

async function sync() {
  if (operationBusy) return publish();
  operationBusy = true;
  state.running = true;
  state.error = null;
  state.notice = null;
  publish();
  const workflow = new SyncWorkflow(preview ? sampleBackend() : backend, (phase, saved) => {
    state.phase = phase;
    if (saved) state.lastSync = { date: saved.date, result: saved.result };
    publish();
  });
  try {
    const outcome = await workflow.run();
    state.lastSync = { date: outcome.saved.date, result: outcome.saved.result };
    state.accounts = outcome.saved.result.accounts;
    state.phase = 'done';
    state.error = outcome.error ? { code: outcome.error.code, message: outcome.error.message } : null;
    if (outcome.saved.saveError) state.notice = 'SAVE_FAILED';
  } catch (error) { errorState(error); }
  finally {
    operationBusy = false;
    state.running = false;
  }
  return publish();
}

async function openClaude() {
  if (preview) return publish();
  // Recheck the shared lock when opening manually: another app may be syncing.
  operationBusy = true;
  state.running = true;
  publish();
  try { await backend.run('open'); state.error = null; state.phase = state.lastSync ? 'done' : 'ready'; }
  finally { operationBusy = false; state.running = false; }
  return publish();
}

async function reveal(files) {
  if (preview || !state.lastSync?.result?.backup || !storageDir) return publish();
  const backup = path.resolve(state.lastSync.result.backup);
  const base = path.resolve(storageDir, 'Backups');
  const relative = path.relative(base, backup);
  if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) throw new WorkflowError('PATH_OPEN_FAILED', 'The latest backup is no longer available.');
  const target = files ? path.join(path.dirname(backup), 'asset-snapshot', 'output-files') : backup;
  try {
    checkNoLinks(target);
    if (!fs.statSync(target).isDirectory()) throw new Error('Missing folder');
    const failure = await shell.openPath(target);
    if (failure) throw new Error('Cannot open');
  } catch { throw new WorkflowError('PATH_OPEN_FAILED', 'The latest backup is no longer available.'); }
  return publish();
}

async function choose(kind) {
  if (preview) return publish();
  const executable = kind === 'claudeExecutable';
  const result = await dialog.showOpenDialog(window, {
    properties: [executable ? 'openFile' : 'openDirectory'],
    ...(executable ? { filters: [{ name: 'Claude', extensions: [process.platform === 'darwin' ? 'app' : 'exe'] }] } : {}),
  });
  if (result.canceled || !result.filePaths.length) return publish();
  const selected = result.filePaths[0];
  if (executable && !selected.toLowerCase().endsWith(process.platform === 'darwin' ? '.app' : '.exe')) throw new WorkflowError('PATH_INVALID', 'Choose the installed Claude application.');
  settings[kind] = selected;
  saveSettings();
  if (!executable) {
    state.error = null;
    await refresh();
  }
  return publish();
}

function createWindow() {
  const area = screen.getPrimaryDisplay().workAreaSize;
  window = new BrowserWindow({
    title: app.name, width: Math.min(680, area.width), height: Math.min(900, area.height - 24),
    minWidth: 480, minHeight: 600, show: false, backgroundColor: '#f7f8fc',
    icon: path.join(__dirname, 'assets/icon.png'),
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), nodeIntegration: false,
      contextIsolation: true, sandbox: true, webSecurity: true, spellcheck: false },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', event => event.preventDefault());
  window.webContents.on('will-attach-webview', event => event.preventDefault());
  window.webContents.session.setPermissionRequestHandler((_content, _permission, callback) => callback(false));
  window.webContents.session.setPermissionCheckHandler(() => false);
  window.webContents.session.webRequest.onBeforeRequest({ urls: ['http://*/*', 'https://*/*', 'ws://*/*', 'wss://*/*'] }, (_request, callback) => callback({ cancel: true }));
  window.webContents.session.on('will-download', event => event.preventDefault());
  window.on('close', event => { if (operationBusy) event.preventDefault(); });
  window.once('ready-to-show', () => window.show());
  window.loadFile(entry);
  if (smoke) window.webContents.once('did-finish-load', runSmoke);
}

async function runSmoke() {
  try {
    const result = await window.webContents.executeJavaScript(`(async () => {
      const pause = () => new Promise(resolve => setTimeout(resolve, 15));
      for (let attempt = 0; attempt < 200 && document.body.dataset.connected !== 'true'; attempt++) await pause();
      if (document.body.dataset.connected !== 'true') throw new Error('Renderer did not connect');
      const languages = ['en', 'es', 'pt-BR'];
      for (const language of languages) {
        const select = document.getElementById('language-select');
        if (!select) throw new Error('No language selector');
        select.value = language;
        select.dispatchEvent(new Event('change', { bubbles: true }));
        for (let attempt = 0; attempt < 200 && (document.body.dataset.language !== language || select.disabled); attempt++) await pause();
        if (document.body.dataset.language !== language || select.disabled) throw new Error('Language did not change');
      }
      document.getElementById('sync-button').click();
      const syncButton = document.getElementById('sync-button');
      for (let attempt = 0; attempt < 400 && (document.body.dataset.phase !== 'done' || syncButton.disabled); attempt++) await pause();
      if (document.body.dataset.phase !== 'done' || syncButton.disabled) throw new Error('Preview workflow did not complete');
      const title = document.getElementById('status-title').textContent;
      if (!title.includes('1') || !title.toLowerCase().includes('conclu')) throw new Error('Missing localized success result');
      const state = await window.syncApi.getState();
      if (!state.preview || state.lastSync.result.accounts !== state.accounts) throw new Error('Preview account count is inconsistent');
      if (typeof window.require !== 'undefined' || typeof window.process !== 'undefined') throw new Error('Renderer exposed Node');
      return { languages, phase: document.body.dataset.phase, localizedSuccess: true, actualAccountCount: true, isolatedRenderer: true };
    })()`);
    console.log(JSON.stringify({ smoke: 'passed', packaged: app.isPackaged, ...result }));
    app.exit(0);
  } catch (error) { console.error('Electron preview check failed: ' + error.message); app.exit(1); }
}

if (!preview && !app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => { if (window) { if (window.isMinimized()) window.restore(); window.show(); window.focus(); } });
  app.on('before-quit', event => { if (operationBusy) event.preventDefault(); });
  app.on('window-all-closed', () => app.quit());
  app.whenReady().then(async () => {
    loadSettings();
    if (process.platform === 'darwin') app.dock.setIcon(nativeImage.createFromPath(path.join(__dirname, 'assets/icon.png')));
    backend = new BackendClient({ packaged: app.isPackaged, resourcesPath: process.resourcesPath, settings, preview });
    try { await refresh(); } catch (error) { state.error = { code: error.code, message: error.message }; }
    menu();
    handle('sync:state', () => publish());
    handle('sync:start', sync, { idle: true });
    handle('sync:language', language => {
      if (!languages.has(language)) throw new WorkflowError('SETTINGS_FAILED', 'Choose a supported language.');
      state.language = language; settings.language = language; saveSettings(); menu(); return publish();
    }, { idle: true });
    handle('sync:open', openClaude, { idle: true });
    handle('sync:files', () => reveal(true), { idle: true });
    handle('sync:backup', () => reveal(false), { idle: true });
    handle('sync:choose-claude', () => choose('claudeExecutable'), { idle: true });
    handle('sync:choose-data', () => choose('appData'), { idle: true });
    handle('sync:choose-projects', () => choose('projectsDir'), { idle: true });
    createWindow();
  }).catch(error => { console.error('Could not start Claude Code User Sync: ' + error.message); app.exit(1); });
}
