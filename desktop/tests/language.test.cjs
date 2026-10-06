'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { resolveLanguage, systemLanguage } = require('../language.cjs');

test('system languages support regional variants from macOS, Windows and Linux', () => {
  for (const locale of ['pt', 'pt-BR', 'pt-PT', 'PT_br', 'pt_BR.UTF-8', 'pt_PT@euro']) assert.equal(systemLanguage([locale]), 'pt-BR');
  for (const locale of ['es', 'es-ES', 'es-MX', 'es-419', 'es_MX.UTF-8', 'es.UTF-8']) assert.equal(systemLanguage([locale]), 'es');
  for (const locale of ['en', 'en-US', 'en-GB', 'en_AU', 'en_US.UTF-8']) assert.equal(systemLanguage([locale]), 'en');
});
test('the first supported preferred OS language is selected', () => {
  assert.equal(systemLanguage(['fr-CA', 'es-MX', 'en-US']), 'es');
  assert.equal(systemLanguage(['pt-PT', 'en-GB']), 'pt-BR');
});
test('unsupported or unavailable system languages fall back to English', () => {
  for (const preferences of [undefined, null, [], ['de-DE', 'ja'], [null, 123, '', 'invalid']]) assert.equal(systemLanguage(preferences), 'en');
});
test('first launch follows the OS without creating a manual override', () => {
  assert.deepEqual(resolveLanguage(undefined, ['es-MX']), { languagePreference: 'system', language: 'es' });
  assert.deepEqual(resolveLanguage('invalid', ['pt-PT']), { languagePreference: 'system', language: 'pt-BR' });
});
test('an explicit saved choice takes precedence across restarts', () => {
  assert.deepEqual(resolveLanguage('en', ['pt-BR']), { languagePreference: 'en', language: 'en' });
  assert.deepEqual(resolveLanguage('pt-BR', ['en-US']), { languagePreference: 'pt-BR', language: 'pt-BR' });
});
test('returning to automatic mode follows subsequent OS language changes', () => {
  assert.deepEqual(resolveLanguage('system', ['es-MX']), { languagePreference: 'system', language: 'es' });
  assert.deepEqual(resolveLanguage('system', ['pt-BR']), { languagePreference: 'system', language: 'pt-BR' });
});
