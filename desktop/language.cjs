'use strict';

const SUPPORTED_LANGUAGES = new Set(['en', 'es', 'pt-BR']);
const LANGUAGE_PREFERENCES = new Set(['system', ...SUPPORTED_LANGUAGES]);

function systemLanguage(preferredLanguages) {
  for (const locale of Array.isArray(preferredLanguages) ? preferredLanguages : []) {
    if (typeof locale !== 'string') continue;
    const base = locale.trim().split(/[.@]/)[0].replaceAll('_', '-').toLowerCase().split('-')[0];
    if (base === 'pt') return 'pt-BR';
    if (base === 'en' || base === 'es') return base;
  }
  return 'en';
}

function resolveLanguage(preference, preferredLanguages) {
  const languagePreference = SUPPORTED_LANGUAGES.has(preference) ? preference : 'system';
  return { languagePreference, language: languagePreference === 'system' ? systemLanguage(preferredLanguages) : languagePreference };
}

module.exports = { SUPPORTED_LANGUAGES, LANGUAGE_PREFERENCES, systemLanguage, resolveLanguage };
