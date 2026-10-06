'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const script = path.resolve(__dirname, '../../setup.sh');
const quote = value => `'${String(value).replaceAll("'", "'\\''")}'`;
const unix = (name, run) => test(name, { skip: process.platform === 'win32' }, run);

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-sync-setup-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.writeFileSync(path.join(root, 'package.json'), '{}');
  fs.writeFileSync(path.join(root, 'package-lock.json'), '{}');
  return root;
}

function bash(root, commands) {
  return spawnSync('bash', ['-c', `source ${quote(script)}
SETUP_ROOT=${quote(root)}
LOG=${quote(path.join(root, 'actions.log'))}
${commands}`], { encoding: 'utf8', env: { ...process.env, CLAUDE_SYNC_PYTHON: '', SSL_CERT_FILE: '' } });
}

const ready = `
detect_platform() { SETUP_PLATFORM=darwin; SETUP_ARCH=arm64; SETUP_NODE_DIR="$SETUP_ROOT/private-node"; }
find_node() { return 0; }
find_python() { SETUP_PYTHON=/mock/python3; return 0; }
id() { printf '1000\\n'; }
node() { printf 'v22.23.3\\n'; }
npm() { printf 'npm %s\\n' "$*" >> "$LOG"; }
sudo() { printf 'sudo %s\\n' "$*" >> "$LOG"; return 99; }
curl() { printf 'curl %s\\n' "$*" >> "$LOG"; return 99; }
`;

unix('setup --check does not install, download, prepare dependencies or launch', t => {
  const root = fixture(t);
  const result = bash(root, `${ready}\nmain --check`);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /No files were changed/);
  assert.deepEqual(fs.readdirSync(root).sort(), ['package-lock.json', 'package.json']);
});

unix('setup --check reports missing prerequisites without changing files', t => {
  const root = fixture(t);
  const result = bash(root, `${ready}
find_node() { return 1; }
find_python() { return 1; }
main --check`);
  assert.equal(result.status, 1);
  assert.match(result.stdout, /Node.js\/npm: missing/);
  assert.match(result.stdout, /Python 3.10\+ with virtual-environment support: missing/);
  assert.deepEqual(fs.readdirSync(root).sort(), ['package-lock.json', 'package.json']);
});

unix('setup --no-launch prepares existing prerequisites without privilege commands', t => {
  const root = fixture(t);
  const result = bash(root, `${ready}\nmain --no-launch`);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.readFileSync(path.join(root, 'actions.log'), 'utf8'), 'npm ci --include=dev\n');
  assert.match(result.stdout, /Rerun setup.sh/);
});

unix('default setup prepares and opens the app without synchronizing', t => {
  const root = fixture(t);
  const result = bash(root, `${ready}\nmain`);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.readFileSync(path.join(root, 'actions.log'), 'utf8'), 'npm ci --include=dev\nnpm start\n');
  assert.match(result.stdout, /only when you click its sync button/);
});

unix('failed dependency preparation never launches the app', t => {
  const root = fixture(t);
  const result = bash(root, `${ready}
npm() { printf 'npm %s\\n' "$*" >> "$LOG"; return 17; }
main`);
  assert.equal(result.status, 17);
  assert.equal(fs.readFileSync(path.join(root, 'actions.log'), 'utf8'), 'npm ci --include=dev\n');
});

unix('Node checksum mismatch prevents extraction and launch', t => {
  const root = fixture(t);
  const result = bash(root, `${ready}
find_node() { return 1; }
download_file() { printf 'untrusted archive' > "$2"; }
tar() { printf 'tar %s\\n' "$*" >> "$LOG"; }
main`);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /failed its SHA-256 check/);
  assert.equal(fs.existsSync(path.join(root, 'actions.log')), false);
  assert.deepEqual(fs.readdirSync(path.join(root, '.sandbox/setup')), []);
});

unix('Python checksum mismatch prevents signature execution and privileged installation', t => {
  const root = fixture(t);
  const result = bash(root, `${ready}
find_python() { return 1; }
download_file() { printf 'untrusted package' > "$2"; }
verify_python_signature() { printf 'signature\\n' >> "$LOG"; }
main --no-launch`);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /failed its SHA-256 check/);
  assert.equal(fs.existsSync(path.join(root, 'actions.log')), false);
});

unix('Python signature failure prevents privileged installation', t => {
  const root = fixture(t);
  const result = bash(root, `${ready}
find_python() { return 1; }
download_file() { printf 'package' > "$2"; }
verify_sha256() { return 0; }
verify_python_signature() { fail 'Python installer signature verification failed.'; }
main --no-launch`);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /signature verification failed/);
  assert.equal(fs.existsSync(path.join(root, 'actions.log')), false);
});

unix('verified macOS Python installation preserves profiles, global links and custom certificates', t => {
  const root = fixture(t);
  const result = bash(root, `${ready}
SSL_CERT_FILE=/mock/user-certificates.pem
find_python() { if [[ -f "$SETUP_ROOT/python-installed" ]]; then SETUP_PYTHON=/mock/python3; return 0; else return 1; fi; }
download_file() { printf 'verified package' > "$2"; }
verify_sha256() { return 0; }
verify_python_signature() { return 0; }
sudo() {
  [[ "$1" == /usr/sbin/installer && "$6" == -applyChoiceChangesXML ]] || return 99
  cp "$7" "$SETUP_ROOT/installer-choices.plist"
  touch "$SETUP_ROOT/python-installed"
}
/usr/bin/security() { printf 'PUBLIC CERTIFICATE\\n'; }
main --no-launch
[[ "$SSL_CERT_FILE" == /mock/user-certificates.pem ]]
`);
  assert.equal(result.status, 0, result.stderr);
  const choices = fs.readFileSync(path.join(root, 'installer-choices.plist'), 'utf8');
  assert.match(choices, /PythonProfileChanges-3\.14.*<integer>0<\/integer>/);
  assert.match(choices, /PythonUnixTools-3\.14.*<integer>0<\/integer>/);
  assert.equal(fs.readFileSync(path.join(root, '.sandbox/setup/macos-ca.pem'), 'utf8'), 'PUBLIC CERTIFICATE\n');
  assert.equal(fs.readFileSync(path.join(root, 'actions.log'), 'utf8'), 'npm ci --include=dev\n');
});

unix('Python signature validation requires the PSF team and a trusted Apple chain', t => {
  const root = fixture(t);
  const legacy = 'Status: signed by a certificate trusted by Mac OS X\nDeveloper ID Installer: Python Software Foundation (BMM5U3QVKW)';
  const current = 'Status: signed by a developer certificate issued by Apple for distribution\nNotarization: trusted by the Apple notary service\nDeveloper ID Installer: Python Software Foundation (BMM5U3QVKW)';
  for (const valid of [legacy, current]) {
    assert.equal(bash(root, `python_signature_trusted ${quote(valid)}`).status, 0);
  }
  for (const invalid of [current.replace('BMM5U3QVKW', 'WRONGTEAM'), current.replace('Python Software Foundation', 'Another Publisher'), current.replace('Notarization: trusted by the Apple notary service', 'Notarization: rejected')]) {
    assert.equal(bash(root, `python_signature_trusted ${quote(invalid)}`).status, 1);
  }
});

unix('macOS read-only Python checks skip the Apple placeholder without developer tools', t => {
  const root = fixture(t);
  const result = bash(root, `
SETUP_PLATFORM=darwin
command() { if [[ "$1" == -v && ( "$2" == python3 || "$2" == /usr/bin/python3 ) ]]; then printf '/usr/bin/python3\\n'; else return 1; fi; }
xcode-select() { printf 'developer-tools-check\\n' >> "$LOG"; return 1; }
if find_python; then exit 91; fi
`);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.readFileSync(path.join(root, 'actions.log'), 'utf8'), 'developer-tools-check\ndeveloper-tools-check\n');
});

unix('Linux setup validates supported distributions without executing release data', t => {
  const root = fixture(t);
  for (const [id, version, status] of [['ubuntu', '22.04', 0], ['ubuntu', '24.04', 0], ['debian', '12', 0], ['debian', '13', 0], ['ubuntu', '20.04', 1], ['debian', '11', 1], ['fedora', '43', 1]]) {
    const file = path.join(root, 'os-release');
    fs.writeFileSync(file, `ID=${id}\nVERSION_ID="${version}"\nIGNORED=$(touch ${path.join(root, 'should-not-exist')})\n`);
    const result = bash(root, `read_linux_release ${quote(file)}`);
    assert.equal(result.status, status, `${id} ${version}: ${result.stderr}`);
    assert.equal(fs.existsSync(path.join(root, 'should-not-exist')), false);
  }
});

unix('Linux package preparation selects available time64 packages and installs only missing groups', t => {
  const root = fixture(t);
  const result = bash(root, `
package_installed() { [[ "$1" != libgtk* && "$1" != libasound* ]]; }
apt-cache() { case "$2" in libgtk-3-0t64|libasound2t64) printf 'Candidate: 1.0\\n' ;; *) printf 'Candidate: (none)\\n' ;; esac; }
sudo() { printf 'sudo %s\\n' "$*" >> "$LOG"; }
install_linux_packages
`);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.readFileSync(path.join(root, 'actions.log'), 'utf8'), 'sudo apt-get update\nsudo apt-get install -y -- libgtk-3-0t64 libasound2t64\n');
});

unix('headless Linux setup prepares without attempting to launch Electron', t => {
  const root = fixture(t);
  const result = bash(root, `${ready}
detect_platform() { SETUP_PLATFORM=linux; SETUP_ARCH=x64; SETUP_NODE_DIR="$SETUP_ROOT/private-node"; }
linux_packages_missing() { return 1; }
unset DISPLAY WAYLAND_DISPLAY
main`);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.readFileSync(path.join(root, 'actions.log'), 'utf8'), 'npm ci --include=dev\n');
  assert.match(result.stdout, /No desktop session was detected/);
});

const linuxReady = `${ready}
detect_platform() { SETUP_PLATFORM=linux; SETUP_ARCH=x64; SETUP_NODE_DIR="$SETUP_ROOT/private-node"; }
linux_packages_missing() { return 1; }
linux_apparmor_restricted() { return 0; }
DISPLAY=:mock
`;

unix('Linux AppArmor restriction detection is read-only and only accepts an enabled Linux setting', t => {
  const root = fixture(t);
  const setting = path.join(root, 'userns-setting');
  for (const [value, status] of [['1\n', 0], ['0\n', 1], ['\n', 1], ['unexpected\n', 1]]) {
    fs.writeFileSync(setting, value);
    assert.equal(bash(root, `SETUP_PLATFORM=linux\nlinux_apparmor_restricted ${quote(setting)}`).status, status);
  }
  fs.writeFileSync(setting, '1\n');
  assert.equal(bash(root, `SETUP_PLATFORM=darwin\nlinux_apparmor_restricted ${quote(setting)}`).status, 1);
  assert.equal(bash(root, `SETUP_PLATFORM=linux\nlinux_apparmor_restricted ${quote(path.join(root, 'missing'))}`).status, 1);
  assert.equal(fs.readFileSync(setting, 'utf8'), '1\n');
});

unix('Linux restricted --check reports the installed app route without building or installing', t => {
  const root = fixture(t);
  const result = bash(root, `${linuxReady}\nmain --check`);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /default setup will build\/install a Debian app/);
  assert.match(result.stdout, /--check does not build or install/);
  assert.deepEqual(fs.readdirSync(root).sort(), ['package-lock.json', 'package.json']);
});

unix('Linux restricted --no-launch only prepares source dependencies', t => {
  const root = fixture(t);
  const result = bash(root, `${linuxReady}\nmain --no-launch`);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.readFileSync(path.join(root, 'actions.log'), 'utf8'), 'npm ci --include=dev\n');
  assert.equal(fs.existsSync(path.join(root, 'release')), false);
});

unix('Linux without the restriction still opens the source app without packaging', t => {
  const root = fixture(t);
  const result = bash(root, `${linuxReady}
linux_apparmor_restricted() { return 1; }
main`);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.readFileSync(path.join(root, 'actions.log'), 'utf8'), 'npm ci --include=dev\nnpm start\n');
  assert.equal(fs.existsSync(path.join(root, 'release')), false);
});

const mockLinuxPackage = `
npm() {
  printf 'npm %s\\n' "$*" >> "$LOG"
  if [[ "$1" == exec ]]; then
    mkdir -p release/setup-linux
    printf 'mock locally built package' > release/setup-linux/claude-code-user-sync-setup.deb
  fi
}
sudo() { printf 'sudo %s\\n' "$*" >> "$LOG"; }
installed_linux_app_available() { return 0; }
/usr/bin/claude-code-user-sync() { printf 'installed-app\\n' >> "$LOG"; }
`;

unix('Linux restriction builds and installs the exact local Debian artifact before normal-user launch', t => {
  const root = fixture(t);
  const result = bash(root, `${linuxReady}\n${mockLinuxPackage}\nmain`);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.readFileSync(path.join(root, 'actions.log'), 'utf8'),
    'npm ci --include=dev\n' +
    'npm run build:backend -- --platform linux\n' +
    'npm exec -- electron-builder --config desktop/scripts/builder-config.cjs --linux deb --x64 --publish never --config.directories.output=release/setup-linux --config.artifactName=claude-code-user-sync-setup.deb\n' +
    'sudo apt-get install -y --reinstall -- ./release/setup-linux/claude-code-user-sync-setup.deb\n' +
    'installed-app\n');
  assert.match(result.stdout, /Opening the installed Claude Code User Sync app/);
});

unix('Linux backend or Debian package build failure blocks package installation and launch', t => {
  for (const failingStep of ['run', 'exec']) {
    const root = fixture(t);
    const result = bash(root, `${linuxReady}
${mockLinuxPackage}
npm() { printf 'npm %s\\n' "$*" >> "$LOG"; if [[ "$1" == ${quote(failingStep)} ]]; then return 17; fi; }
main`);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /could not be built/);
    const actions = fs.readFileSync(path.join(root, 'actions.log'), 'utf8');
    assert.doesNotMatch(actions, /sudo|installed-app|npm start/);
    if (failingStep === 'run') assert.doesNotMatch(actions, /npm exec/);
  }
});

unix('failed Linux Debian installation blocks launch', t => {
  const root = fixture(t);
  const result = bash(root, `${linuxReady}
${mockLinuxPackage}
sudo() { printf 'sudo %s\\n' "$*" >> "$LOG"; return 19; }
main`);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /could not be installed/);
  assert.doesNotMatch(fs.readFileSync(path.join(root, 'actions.log'), 'utf8'), /installed-app|npm start/);
});

unix('missing or symlinked Linux artifact cannot reach the privileged installer', t => {
  for (const artifact of ['missing', 'symlink']) {
    const root = fixture(t);
    if (artifact === 'symlink') {
      fs.mkdirSync(path.join(root, 'release/setup-linux'), { recursive: true });
      fs.writeFileSync(path.join(root, 'other.deb'), 'other package');
      fs.symlinkSync(path.join(root, 'other.deb'), path.join(root, 'release/setup-linux/claude-code-user-sync-setup.deb'));
    }
    const result = bash(root, `${linuxReady}
${mockLinuxPackage}
npm() { printf 'npm %s\\n' "$*" >> "$LOG"; }
main`);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /expected Linux app package is missing/);
    assert.doesNotMatch(fs.readFileSync(path.join(root, 'actions.log'), 'utf8'), /sudo|installed-app|npm start/);
  }
});
