(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SyncSummary = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function count(value) {
    return Number.isSafeInteger(value) && value >= 0 ? value : 0;
  }

  function summarize(result, detectedAccounts) {
    const data = result && typeof result === 'object' ? result : {};
    const assets = data.assets && typeof data.assets === 'object' ? data.assets : null;
    const classified = !!assets && count(assets.diagnostic_version) >= 2;
    const field = (key) => count(assets && assets[key]);
    const accountValue = Number.isSafeInteger(detectedAccounts) && detectedAccounts >= 0
      ? detectedAccounts
      : Array.isArray(data.accounts) ? data.accounts.length
        : Number.isSafeInteger(data.accounts) && data.accounts >= 0 ? data.accounts : null;
    const unavailableOutputs = assets && assets.unpreserved_output_files != null
      ? field('unpreserved_output_files') : field('missing_output_files');
    const histories = Math.max(count(data.missing_transcripts), classified ? field('missing_transcript_ids') : 0);
    const candidates = [
      ['chatReview', count(data.conflicts)],
      ['historyUnavailable', histories],
      ['fileUnavailable', classified ? unavailableOutputs : 0],
      ['imageUnavailable', classified ? field('missing_linked_images') : 0],
      ['historyCheck', classified ? field('unreadable_transcripts') : 0],
      ['imageCheck', field('invalid_images')],
      ['fileCheck', field('unreadable_files') + (classified ? field('unsafe_files') : 0)],
      ['artifactReview', field('artifact_conflicts')],
    ];
    const issues = candidates.filter(([, total]) => total > 0).map(([key, total]) => ({ key, count: total }));
    return {
      accounts: accountValue,
      chats: count(data.chats),
      projects: count(data.projects),
      assets,
      classified,
      issues,
      completionKey: issues.length ? 'syncWithIssues' : !assets ? 'syncWithoutAudit'
        : !classified ? 'syncLegacyAudit' : field('preserved_output_files') > 0 ? 'syncPreserved' : 'syncComplete',
      verification: {
        artifacts: field('artifact_references'), files: field('local_files'),
        images: field('local_images'), embedded: field('embedded_images'),
      },
      diagnostics: {
        missingOutputs: classified ? field('missing_output_files') : 0,
        preserved: classified ? field('preserved_output_files') : 0,
        previews: classified ? field('saved_read_images') : 0,
        missingReferences: classified ? field('missing_reference_links') : 0,
        unverifiedReferences: classified ? field('unverified_reference_links') : 0,
        failedSends: classified ? field('failed_file_sends') : 0,
        remote: field('remote_links'),
      },
    };
  }

  function completedButClosed(state) {
    return !!state && !!state.lastSync && state.phase === 'done'
      && !!state.error && ['OPEN_FAILED', 'SYNC_BUSY'].includes(state.error.code);
  }

  return { count, summarize, completedButClosed };
});
