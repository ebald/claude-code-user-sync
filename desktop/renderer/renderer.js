/* The renderer receives state and permitted actions through the preload bridge. */
(async function () {
  'use strict';
  const api = window.syncApi;
  const allowedLanguages = new Set(['en', 'es', 'pt-BR']);
  const phases = ['closing', 'syncing', 'reopening'];
  const $ = (id) => document.getElementById(id);
  let state = { preview: false, language: 'en', accounts: null, phase: 'ready', running: false, lastSync: null, error: null, notice: null };
  let pendingAction = null;

  await window.i18next.init({
    lng: 'en', fallbackLng: 'en', supportedLngs: [...allowedLanguages],
    resources: window.SYNC_TRANSLATIONS,
    interpolation: { escapeValue: false },
    returnNull: false,
  });
  const t = (key, options) => window.i18next.t(key, options);
  const setText = (id, value) => { $(id).textContent = value; };
  const visible = (id, show) => { $(id).hidden = !show; };
  const busy = () => state.running || pendingAction === 'sync';
  const errorText = (error) => error && window.i18next.exists(`errors.${error.code}`)
    ? t(`errors.${error.code}`) : t('errors.UNKNOWN');
  const noticeText = (code) => window.i18next.exists(`notices.${code}`) ? t(`notices.${code}`) : t('notices.UNKNOWN');

  function formattedDate(value) {
    if (value == null) return null;
    // Legacy Swift saved dates use seconds since Apple's 2001 reference date.
    const date = typeof value === 'number' ? new Date((value + 978307200) * 1000) : new Date(value);
    return Number.isNaN(date.getTime()) ? null
      : new Intl.DateTimeFormat(state.language, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
  }

  function issueText(issue) { return t(`issues.${issue.key}`, { count: issue.count }); }
  function completion(summary) {
    return summary.issues.length ? t('syncWithIssues', { issues: summary.issues.map(issueText).join(', ') })
      : t(summary.completionKey);
  }
  function totals(summary) {
    return [summary.accounts == null ? null : t('accountTotal', { count: summary.accounts }),
      t('chatTotal', { count: summary.chats }), t('projectTotal', { count: summary.projects })].filter(Boolean).join(' · ');
  }
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function renderDiagnostics() {
    const content = $('diagnostics-content');
    content.replaceChildren();
    if (!state.lastSync) return;
    const summary = window.SyncSummary.summarize(state.lastSync.result, state.accounts);
    content.append(element('p', completion(summary), 'diagnostic-summary'));
    const date = formattedDate(state.lastSync.date);
    if (date) content.append(element('p', t('lastSync', { date }), 'dialog-paragraph'));
    content.append(element('p', totals(summary), 'dialog-paragraph'));
    if (state.preview) content.append(element('p', t('previewHint'), 'dialog-paragraph'));

    if (summary.assets) {
      const grid = element('dl', null, 'diagnostic-grid');
      for (const [key, value] of Object.entries(summary.verification)) {
        const item = element('div', null, 'diagnostic-stat');
        item.append(element('dt', t(`stats.${key}`)), element('dd', String(value)));
        grid.append(item);
      }
      content.append(grid);
    }
    if (summary.issues.length) {
      content.append(element('h3', t('itemsToReview'), 'diagnostic-section-title'));
      const list = element('ul', null, 'diagnostic-issues');
      summary.issues.forEach((issue) => list.append(element('li', issueText(issue))));
      content.append(list);
    } else if (summary.classified) {
      content.append(element('p', t('verifiedAvailable'), 'dialog-paragraph'));
    }
    if (!summary.assets) {
      content.append(element('p', t('noAudit'), 'dialog-paragraph'));
    } else if (!summary.classified) {
      content.append(element('p', t('legacyAudit'), 'dialog-paragraph'));
    } else {
      const info = summary.diagnostics;
      if (info.missingOutputs > 0) content.append(element('p', t('preservedExplanation', {
        count: info.missingOutputs, preservedSummary: t('preservedCopies', { count: info.preserved }),
      }), 'dialog-paragraph'));
      if (info.previews > 0) content.append(element('p', t('previewsExplanation', { count: info.previews }), 'dialog-paragraph'));
      if (info.missingReferences || info.unverifiedReferences || info.failedSends) {
        content.append(element('h3', t('historicalInformation'), 'diagnostic-section-title'));
        content.append(element('p', t('historicalExplanation'), 'dialog-paragraph'));
        const list = element('ul', null, 'diagnostic-issues');
        for (const [key, total] of [['missingReferences', info.missingReferences], ['unverifiedReferences', info.unverifiedReferences], ['failedSends', info.failedSends]]) {
          if (total > 0) list.append(element('li', t(`historical.${key}`, { count: total })));
        }
        content.append(list);
      }
      if (info.remote > 0) content.append(element('p', t('remoteExplanation', { count: info.remote }), 'dialog-paragraph'));
      content.append(element('p', t('imagesExplanation'), 'dialog-paragraph'));
    }
    content.append(element('p', t('backupExplanation'), 'dialog-paragraph'));
    const details = element('details', null, 'technical-details');
    details.append(element('summary', t('technicalDetails')), element('pre', JSON.stringify(state.lastSync.result, null, 2)));
    content.append(details);
  }

  function renderError() {
    const error = state.error;
    setText('error-localized', errorText(error));
    setText('error-raw', error ? [error.code, error.message].filter(Boolean).join('\n\n') : '');
  }

  function render() {
    document.documentElement.lang = state.language;
    document.body.dataset.language = state.language;
    document.body.dataset.phase = state.phase;
    document.querySelectorAll('[data-i18n]').forEach((node) => { node.textContent = t(node.dataset.i18n); });
    document.querySelectorAll('.dialog-close').forEach((node) => { node.setAttribute('aria-label', t('close')); });
    document.querySelector('.workflow').setAttribute('aria-label', t('stepsLabel'));
    $('language-select').value = state.language;
    $('language-select').setAttribute('aria-label', t('language'));
    $('settings-button').title = t('settings');
    $('settings-button').setAttribute('aria-label', t('settings'));
    visible('preview-badge', state.preview);
    visible('settings-preview-hint', state.preview);
    setText('account-count', state.accounts == null ? t('allAccounts') : t('accountsDetected', { count: state.accounts }));
    setText('usage-hint-text', t(state.preview ? 'previewHint' : 'usageHint'));

    const active = phases.indexOf(state.phase);
    document.querySelectorAll('.step').forEach((node, index) => {
      node.classList.toggle('is-active', state.running && index === active);
      node.classList.toggle('is-complete', state.phase === 'done' || (state.running && index < active));
    });
    $('sync-button').disabled = !!pendingAction || state.running;
    const buttonKey = busy() ? ({ closing: 'closing', syncing: 'syncing', reopening: 'reopening' }[state.phase] || 'preparing') : 'syncButton';
    setText('sync-button-label', t(buttonKey));
    visible('sync-button-spinner', busy());
    visible('sync-button-icon', !busy());
    const saved = state.lastSync;
    const summary = saved ? window.SyncSummary.summarize(saved.result, state.accounts) : null;
    const error = state.error;
    const hasSuccessfulSync = window.SyncSummary.completedButClosed(state);
    $('status-card').classList.toggle('is-success', !busy() && (!!saved && !error || hasSuccessfulSync));
    $('status-card').classList.toggle('is-error', !!error && !hasSuccessfulSync);
    $('status-icon-use').setAttribute('href', error && !hasSuccessfulSync ? '#icon-alert' : saved && !busy() ? '#icon-check' : '#icon-chat');
    setText('status-title', busy() ? t('inProgress') : error ? t(hasSuccessfulSync ? 'syncedClaudeClosed' : 'couldNotFinish') : summary ? completion(summary) : t('readyTitle'));
    setText('status-description', busy() ? t('progressHint') : error ? errorText(error) : summary ? totals(summary) : t('readyDescription'));
    visible('verification-summary', !!summary && !!summary.assets && !busy() && !error);
    if (summary && summary.assets) setText('verification-summary', t('verificationSummary', summary.verification));
    visible('diagnostics-button', !!saved && !busy());
    visible('error-details-button', !!error && !busy());
    visible('files-button', !!saved && !state.preview && !busy());
    setText('last-sync-date', saved && formattedDate(saved.date) ? t('lastSync', { date: formattedDate(saved.date) }) : t('firstSync'));
    visible('notice', !!state.notice);
    setText('notice', state.notice ? noticeText(state.notice) : '');
    for (const id of ['open-claude-button', 'files-button', 'backup-button', 'choose-claude-button', 'choose-data-button', 'choose-projects-button']) {
      $(id).disabled = busy() || !!pendingAction || state.preview || (id === 'backup-button' && !saved);
    }
    $('settings-button').disabled = busy() || !!pendingAction;
    $('language-select').disabled = busy() || !!pendingAction;
    renderDiagnostics();
    renderError();
  }

  async function applyState(next) {
    if (!next || typeof next !== 'object' || !('phase' in next)) return;
    state = { ...state, ...next, language: allowedLanguages.has(next.language) ? next.language : state.language };
    if (window.i18next.language !== state.language) await window.i18next.changeLanguage(state.language);
    render();
  }

  async function invoke(method, argument) {
    if (pendingAction || state.running) return;
    pendingAction = method;
    render();
    try {
      const result = argument === undefined ? await api[method]() : await api[method](argument);
      await applyState(result);
    } catch (error) {
      state = { ...state, error: { code: 'UNKNOWN', message: error && error.message ? String(error.message) : String(error) } };
    } finally {
      pendingAction = null;
      render();
    }
  }

  $('sync-button').addEventListener('click', () => invoke('sync'));
  $('language-select').addEventListener('change', (event) => {
    if (event.target.value !== state.language) invoke('setLanguage', event.target.value);
  });
  for (const [id, method] of [['open-claude-button', 'openClaude'], ['files-button', 'showFiles'], ['backup-button', 'showBackup'], ['choose-claude-button', 'chooseClaude'], ['choose-data-button', 'chooseDataDirectory'], ['choose-projects-button', 'chooseProjectsDirectory']]) {
    $(id).addEventListener('click', () => invoke(method));
  }
  for (const [id, dialog] of [['diagnostics-button', 'diagnostics-dialog'], ['error-details-button', 'error-dialog'], ['settings-button', 'settings-dialog']]) {
    $(id).addEventListener('click', () => $(dialog).showModal());
  }
  document.querySelectorAll('[data-close]').forEach((node) => { node.addEventListener('click', () => $(node.dataset.close).close()); });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey) && !document.querySelector('dialog[open]')) {
      event.preventDefault();
      invoke('sync');
    }
  });
  render();
  if (!api) {
    state.error = { code: 'UNKNOWN', message: 'The application connection is unavailable.' };
    render();
    return;
  }
  const unsubscribe = api.onState((next) => { applyState(next).catch(() => {}); });
  window.addEventListener('beforeunload', () => { if (typeof unsubscribe === 'function') unsubscribe(); }, { once: true });
  try {
    await applyState(await api.getState());
    document.body.dataset.connected = 'true';
  }
  catch (error) { state.error = { code: 'UNKNOWN', message: String(error && error.message || error) }; render(); }
})();
