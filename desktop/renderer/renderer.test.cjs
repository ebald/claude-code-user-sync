'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const i18next = require('i18next');
const summary = require('./summary.js');

function rendererHarness() {
  const nodes = new Map();
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, { textContent: '', dataset: {}, listeners: {}, attributes: {},
      classList: { toggle() {} }, replaceChildren() {}, append() {},
      setAttribute(name, value) { this.attributes[name] = value; },
      addEventListener(name, callback) { this.listeners[name] = callback; },
    });
    return nodes.get(id);
  }
  const body = { dataset: { booting: 'true' } };
  const html = { lang: 'en' };
  const hero = node('hero');
  hero.dataset.i18n = 'hero';
  const systemOption = node('system-option');
  systemOption.dataset.i18n = 'systemLanguage';
  const steps = ['closing', 'syncing', 'reopening'].map((id) => node(`step-${id}`));
  const document = {
    body, documentElement: html, getElementById: node, addEventListener() {},
    querySelector(selector) { return selector === 'dialog[open]' ? null : node(selector); },
    querySelectorAll(selector) {
      return selector === '[data-i18n]' ? [hero, systemOption] : selector === '.step' ? steps : [];
    },
  };
  let resolveState;
  let rejectState;
  let subscriber;
  let currentState;
  const setLanguages = [];
  const initializedLanguages = [];
  const initialState = new Promise((resolve, reject) => { resolveState = resolve; rejectState = reject; });
  const instance = i18next.createInstance();
  const init = instance.init.bind(instance);
  instance.init = (options) => { initializedLanguages.push(options.lng); return init(options); };
  const resources = Object.fromEntries(['en', 'es', 'pt-BR'].map((language) => [language, {
    translation: JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'locales', `${language}.json`), 'utf8')),
  }]));
  const window = {
    i18next: instance, SYNC_TRANSLATIONS: resources, SyncSummary: summary, addEventListener() {},
    syncApi: {
      onState(callback) { subscriber = callback; return () => {}; },
      getState() { return initialState; },
      async setLanguage(preference) {
        setLanguages.push(preference);
        currentState = { ...currentState, languagePreference: preference };
        return currentState;
      },
    },
  };
  const completion = vm.runInNewContext(fs.readFileSync(path.join(__dirname, 'renderer.js'), 'utf8'), { window, document });
  return {
    body, html, nodes, initializedLanguages, setLanguages, completion,
    resolve(next) { currentState = next; resolveState(next); }, reject: rejectState,
    emit(next) { currentState = next; subscriber(next); },
    async select(preference) {
      nodes.get('language-select').listeners.change({ target: { value: preference } });
      await new Promise(setImmediate);
    },
  };
}

test('the first visible interface uses the resolved system locale without an English flash', async () => {
  const harness = rendererHarness();
  assert.equal(harness.body.dataset.booting, 'true');
  assert.deepEqual(harness.initializedLanguages, []);
  assert.equal(harness.nodes.get('hero').textContent, '');
  harness.resolve({ phase: 'ready', language: 'pt-BR', languagePreference: 'system', accounts: 2 });
  await harness.completion;
  assert.deepEqual(harness.initializedLanguages, ['pt-BR']);
  assert.equal(harness.body.dataset.booting, 'false');
  assert.equal(harness.html.lang, 'pt-BR');
  assert.equal(harness.nodes.get('language-select').value, 'system');
  assert.equal(harness.nodes.get('system-option').textContent, 'Idioma do sistema');
  assert.ok(harness.nodes.get('hero').textContent.startsWith('Troque de conta.'));
});

test('manual selection and returning to system language work when the resolved locale stays the same', async () => {
  const harness = rendererHarness();
  harness.resolve({ phase: 'ready', language: 'pt-BR', languagePreference: 'system', accounts: 2 });
  await harness.completion;
  await harness.select('pt-BR');
  assert.deepEqual(harness.setLanguages, ['pt-BR']);
  assert.equal(harness.nodes.get('language-select').value, 'pt-BR');
  await harness.select('system');
  assert.deepEqual(harness.setLanguages, ['pt-BR', 'system']);
  assert.equal(harness.nodes.get('language-select').value, 'system');
  assert.equal(harness.html.lang, 'pt-BR');
  await harness.select('system');
  assert.deepEqual(harness.setLanguages, ['pt-BR', 'system']);
});

test('state notifications received during startup are applied before revealing the interface', async () => {
  const harness = rendererHarness();
  harness.emit({ phase: 'ready', language: 'es', languagePreference: 'system', accounts: 2 });
  harness.resolve({ phase: 'ready', language: 'en', languagePreference: 'system', accounts: 2 });
  await harness.completion;
  assert.equal(harness.html.lang, 'es');
  assert.equal(harness.nodes.get('system-option').textContent, 'Idioma del sistema');
  assert.equal(harness.body.dataset.booting, 'false');
});

test('startup connection errors reveal an understandable error instead of leaving the app hidden', async () => {
  const harness = rendererHarness();
  harness.reject(new Error('Connection interrupted'));
  await harness.completion;
  assert.equal(harness.body.dataset.booting, 'false');
  assert.equal(harness.nodes.get('status-title').textContent, 'Could not finish');
  assert.ok(harness.nodes.get('error-raw').textContent.includes('Connection interrupted'));
});

test('Linux shutdown failures show a translated manual quit action in every language', async () => {
  const expected = {
    en: 'Claude is still running.',
    es: 'Claude sigue abierto.',
    'pt-BR': 'O Claude ainda está aberto.',
  };
  for (const [language, message] of Object.entries(expected)) {
    const harness = rendererHarness();
    harness.resolve({ platform: 'linux', phase: 'error', language, languagePreference: 'system',
      error: { code: 'CLAUDE_RUNNING', message: 'The backend requires a manual quit.' } });
    await harness.completion;
    assert.equal(harness.body.dataset.platform, 'linux');
    assert.ok(harness.nodes.get('status-description').textContent.startsWith(message));
    assert.ok(harness.nodes.get('error-localized').textContent.startsWith(message));
    assert.equal(harness.nodes.get('sync-button').disabled, false);
    assert.ok(harness.nodes.get('error-raw').textContent.includes('CLAUDE_RUNNING'));
  }
});
