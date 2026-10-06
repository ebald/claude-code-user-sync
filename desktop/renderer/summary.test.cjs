'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { summarize, completedButClosed } = require('./summary.js');

test('count accounts, never organization profiles, and prefer the current account inventory', () => {
  assert.equal(summarize({ profiles: 3 }, 2).accounts, 2);
  assert.equal(summarize({ profiles: 3 }).accounts, null);
  assert.equal(summarize({ accounts: 2, profiles: 3 }).accounts, 2);
  assert.equal(summarize({ accounts: ['a', 'b'], profiles: 3 }).accounts, 2);
});

test('a successful sync reports the one unavailable delivered file calmly', () => {
  const data = summarize({ assets: { diagnostic_version: 2, missing_files: 122,
    missing_output_files: 2, unpreserved_output_files: 1, preserved_output_files: 1,
    missing_reference_links: 120, failed_file_sends: 9 } });
  assert.deepEqual(data.issues, [{ key: 'fileUnavailable', count: 1 }]);
  assert.equal(data.completionKey, 'syncWithIssues');
  assert.equal(data.diagnostics.preserved, 1);
  assert.equal(data.diagnostics.failedSends, 9);
});

test('available preserved copies and missing temporary references do not become warnings', () => {
  const data = summarize({ assets: { diagnostic_version: 2, missing_output_files: 5,
    unpreserved_output_files: 0, preserved_output_files: 5, missing_reference_links: 80 } });
  assert.deepEqual(data.issues, []);
  assert.equal(data.completionKey, 'syncPreserved');
});

test('missing chat histories are deduplicated across catalogue and asset audit', () => {
  const data = summarize({ missing_transcripts: 5, assets: { diagnostic_version: 2, missing_transcript_ids: 3 } });
  assert.deepEqual(data.issues, [{ key: 'historyUnavailable', count: 5 }]);
});

test('classified reports lacking the new unavailable counter fall back to missing outputs', () => {
  const data = summarize({ assets: { diagnostic_version: 2, missing_output_files: 2 } });
  assert.deepEqual(data.issues, [{ key: 'fileUnavailable', count: 2 }]);
  assert.deepEqual(summarize({ assets: { diagnostic_version: 2, missing_output_files: 2,
    unpreserved_output_files: null } }).issues, data.issues);
});

test('legacy audit counters do not falsely describe delivered content as missing', () => {
  const data = summarize({ assets: { missing_files: 200, missing_output_files: 100,
    unsafe_files: 12, unreadable_transcripts: 5, invalid_images: 1 } });
  assert.deepEqual(data.issues, [{ key: 'imageCheck', count: 1 }]);
  assert.equal(data.classified, false);
  assert.equal(summarize({ assets: { missing_files: 200 } }).completionKey, 'syncLegacyAudit');
});

test('all classified content issues remain visible and invalid counter values are ignored', () => {
  const data = summarize({ conflicts: 1, chats: -1, projects: '3', assets: {
    diagnostic_version: 2, missing_linked_images: 2, unreadable_transcripts: 3,
    invalid_images: 4, unreadable_files: 5, unsafe_files: 6, artifact_conflicts: 7,
  } });
  assert.deepEqual(data.issues, [
    { key: 'chatReview', count: 1 }, { key: 'imageUnavailable', count: 2 },
    { key: 'historyCheck', count: 3 }, { key: 'imageCheck', count: 4 },
    { key: 'fileCheck', count: 11 }, { key: 'artifactReview', count: 7 },
  ]);
  assert.equal(data.chats, 0);
  assert.equal(data.projects, 0);
  assert.equal(summarize(null).completionKey, 'syncWithoutAudit');
});

test('completed sync stays successful if reopening fails or another sync claims the lock', () => {
  const state = { phase: 'done', lastSync: { result: {} } };
  assert.equal(completedButClosed({ ...state, error: { code: 'OPEN_FAILED' } }), true);
  assert.equal(completedButClosed({ ...state, error: { code: 'SYNC_BUSY' } }), true);
  assert.equal(completedButClosed({ ...state, error: { code: 'PATH_OPEN_FAILED' } }), false);
  assert.equal(completedButClosed({ ...state, phase: 'error', error: { code: 'SYNC_BUSY' } }), false);
  assert.equal(completedButClosed({ ...state, phase: 'error', error: { code: 'OPEN_FAILED' } }), false);
  assert.equal(completedButClosed({ phase: 'done', error: { code: 'SYNC_BUSY' } }), false);
});

function leaves(object, prefix = '') {
  return Object.fromEntries(Object.entries(object).flatMap(([key, value]) => {
    const full = prefix ? `${prefix}.${key}` : key;
    return value && typeof value === 'object' ? Object.entries(leaves(value, full)) : [[full, value]];
  }));
}
const resources = Object.fromEntries(['en', 'es', 'pt-BR'].map((language) => [language,
  JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'locales', `${language}.json`), 'utf8'))]));

test('each language has the same keys and interpolation variables', () => {
  const baseline = leaves(resources.en);
  const placeholders = (text) => [...text.matchAll(/\{\{(\w+)\}\}/g)].map((match) => match[1]).sort();
  for (const [language, data] of Object.entries(resources)) {
    const translations = leaves(data);
    assert.deepEqual(Object.keys(translations).sort(), Object.keys(baseline).sort(), language);
    for (const [key, text] of Object.entries(translations)) {
      assert.equal(typeof text, 'string', `${language} ${key}`);
      assert.ok(text.trim(), `${language} ${key}`);
      assert.deepEqual(placeholders(text), placeholders(baseline[key]), `${language} ${key}`);
    }
  }
});

test('bundled translations match the editable JSON resources', () => {
  const context = { window: {} };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, 'translations.js'), 'utf8'), context);
  const bundled = JSON.parse(JSON.stringify(context.window.SYNC_TRANSLATIONS));
  assert.deepEqual(bundled, Object.fromEntries(Object.entries(resources).map(([language, data]) => [language, { translation: data }])));
});

test('static renderer text has translations in every language', () => {
  const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
  const keys = [...html.matchAll(/data-i18n="([^"]+)"/g)].map((match) => match[1]);
  for (const [language, resource] of Object.entries(resources)) {
    const translations = leaves(resource);
    for (const key of keys) assert.ok(translations[key], `${language}: ${key}`);
  }
  assert.ok(html.includes("script-src 'self'"));
  assert.ok(!html.includes('onclick='));
});

test('i18next resolves each locale and plural completion text without leaking translation keys', async () => {
  const i18next = require('i18next').createInstance();
  await i18next.init({ lng: 'en', fallbackLng: 'en', supportedLngs: ['en', 'es', 'pt-BR'],
    resources: Object.fromEntries(Object.entries(resources).map(([language, data]) => [language, { translation: data }])),
    interpolation: { escapeValue: false } });
  const expected = {
    en: ['1 file unavailable', '2 files unavailable', 'No accounts detected'],
    es: ['1 archivo no disponible', '2 archivos no disponibles', 'No se detectaron cuentas'],
    'pt-BR': ['1 arquivo indisponível', '2 arquivos indisponíveis', 'Nenhuma conta detectada'],
  };
  for (const [language, text] of Object.entries(expected)) {
    await i18next.changeLanguage(language);
    assert.equal(i18next.t('issues.fileUnavailable', { count: 1 }), text[0]);
    assert.equal(i18next.t('issues.fileUnavailable', { count: 2 }), text[1]);
    assert.equal(i18next.t('accountsDetected', { count: 0 }), text[2]);
    assert.ok(!i18next.t('verificationSummary', { artifacts: 8, files: 12, images: 3, embedded: 2 }).includes('{{'));
  }
});

test('diagnostic sentences pluralize missing files and recovered copies independently', async () => {
  const i18next = require('i18next').createInstance();
  await i18next.init({ lng: 'en', fallbackLng: 'en', resources: Object.fromEntries(Object.entries(resources)
    .map(([language, data]) => [language, { translation: data }])), interpolation: { escapeValue: false } });
  const expected = {
    en: ['1 original delivered file is missing', '2 original delivered files are missing',
      '1 preserved copy is available', '2 preserved copies are available', '1 image preview was recovered', '1 remote link was found'],
    es: ['1 archivo entregado no está', '2 archivos entregados no están',
      '1 copia conservada está disponible', '2 copias conservadas están disponibles', 'Se recuperó 1 vista previa', 'Se encontró 1 enlace remoto'],
    'pt-BR': ['1 arquivo entregue não está', '2 arquivos entregues não estão',
      '1 cópia preservada está disponível', '2 cópias preservadas estão disponíveis', '1 prévia de imagem foi recuperada', '1 link remoto foi encontrado'],
  };
  for (const [language, text] of Object.entries(expected)) {
    await i18next.changeLanguage(language);
    for (const count of [1, 2]) {
      const preservedSummary = i18next.t('preservedCopies', { count: count === 1 ? 2 : 1 });
      const phrase = i18next.t('preservedExplanation', { count, preservedSummary });
      assert.ok(phrase.startsWith(text[count - 1]), `${language}: ${phrase}`);
      assert.ok(phrase.includes(text[count === 1 ? 3 : 2]), `${language}: ${phrase}`);
      assert.ok(!phrase.includes('{{'));
    }
    assert.ok(i18next.t('previewsExplanation', { count: 1 }).startsWith(text[4]));
    assert.ok(i18next.t('remoteExplanation', { count: 1 }).startsWith(text[5]));
    assert.ok(!i18next.t('preservedCopies', { count: 0 }).includes('preservedCopies'));
    assert.ok(!i18next.t('previewsExplanation', { count: 2 }).includes('previewsExplanation'));
    assert.ok(!i18next.t('remoteExplanation', { count: 2 }).includes('remoteExplanation'));
  }
});
