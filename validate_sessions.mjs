// Reads only the cloned sandbox with the official SDK. Never launches Claude.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';
import childProcess from 'node:child_process';
import { syncBuiltinESMExports } from 'node:module';

const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, arg, i, all) => {
  if (arg.startsWith('--')) pairs.push([arg.slice(2), all[i + 1]]);
  return pairs;
}, []));
if (!args.sandbox || !args.profile || !args.out) throw new Error('Use --sandbox --profile --out');
const sandbox = path.resolve(args.sandbox);
const config = path.join(sandbox, 'config');
const registry = path.join(sandbox, 'registry', args.profile);
const relativeProfile = path.relative(path.join(sandbox, 'registry'), registry);
if (relativeProfile.startsWith('..') || path.isAbsolute(relativeProfile)) throw new Error('Invalid profile');

process.env.CLAUDE_CONFIG_DIR = config;
for (const key of ['ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_PROFILE']) {
  delete process.env[key];
}
let deniedOperations = 0;
const deny = () => { deniedOperations++; throw new Error('Network and subprocesses are disabled during validation'); };
globalThis.fetch = deny;
http.request = http.get = https.request = https.get = deny;
net.connect = net.createConnection = net.Socket.prototype.connect = deny;
for (const key of ['spawn', 'spawnSync', 'exec', 'execSync', 'execFile', 'execFileSync', 'fork']) childProcess[key] = deny;
syncBuiltinESMExports();

const { listSessions, getSessionMessages } = await import('@anthropic-ai/claude-agent-sdk');
const sessions = await listSessions({ includeWorktrees: false, includeProgrammatic: true });
const known = new Set(sessions.map(s => s.sessionId));
const records = [];
for (const name of await fs.readdir(registry)) {
  if (/^local_[0-9a-f-]{36}\.json$/i.test(name)) records.push(JSON.parse(await fs.readFile(path.join(registry, name), 'utf8')));
}
const report = {
  profile: args.profile, catalogRecords: records.length,
  sdkListedSessions: sessions.length, readableRecords: 0, missingRecords: 0,
  emptyRecords: 0, readErrors: 0, messageCount: 0, digests: {},
};
const cache = new Map();
for (const record of records) {
  const ids = [record.cliSessionId, ...(record.priorCliSessionIds ?? []).slice().reverse()];
  const sid = ids.find(id => known.has(id));
  if (!sid) { report.missingRecords++; continue; }
  if (!cache.has(sid)) {
    try {
      const messages = await getSessionMessages(sid, { includeSystemMessages: true });
      const digest = createHash('sha256').update(JSON.stringify(messages)).digest('hex');
      cache.set(sid, { count: messages.length, digest,
        user: messages.filter(m => m.type === 'user').length,
        assistant: messages.filter(m => m.type === 'assistant').length });
    } catch {
      cache.set(sid, null); // Do not print exception text or conversation contents.
    }
  }
  const info = cache.get(sid);
  if (!info) { report.readErrors++; continue; }
  if (!info.count) { report.emptyRecords++; continue; }
  report.readableRecords++;
  report.messageCount += info.count;
  report.digests[record.sessionId] = { transcriptId: sid, ...info };
}
report.deniedOperations = deniedOperations;
await fs.writeFile(path.resolve(args.out), JSON.stringify(report, null, 2) + '\n', { mode: 0o600 });
const { digests, ...summary } = report;
console.log(JSON.stringify(summary, null, 2));
if (report.readErrors || report.emptyRecords || deniedOperations) process.exitCode = 1;
