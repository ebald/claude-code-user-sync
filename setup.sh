#!/usr/bin/env bash
# Prepare a source checkout using official runtimes and native OS packages.
set -euo pipefail

SETUP_ROOT=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
NODE_VERSION=22.23.3
PYTHON_VERSION=3.14.8
SETUP_CHECK=0
SETUP_LAUNCH=1
SETUP_TEMP=''
SETUP_PYTHON=''

say() { printf '%s\n' "$*"; }
fail() { say "Setup could not finish: $*" >&2; return 1; }

help() {
  cat <<'HELP'
Claude Code User Sync — automatic source setup

Usage: bash setup.sh [--check] [--no-launch]

  --check      Check prerequisites without downloading, installing, preparing
               dependencies or opening the app. Exit 1 if something is missing.
  --no-launch  Install missing prerequisites and prepare the app without opening it.
  --help       Show this help.

Supports macOS 13+ and Ubuntu 22.04+/Debian 12+, on x64 and arm64.
Setup reuses suitable Node.js/npm and Python installations. If Node.js is
missing, a verified official Node.js binary is kept in this checkout's
.sandbox/setup directory; shell profiles and the global Node.js are unchanged.
Missing Python on macOS is installed from Python.org's signed installer.
Linux uses apt for Python, virtual-environment support and desktop libraries.
Administrator permission is requested only for missing system prerequisites.
On Linux with AppArmor restrictions on source Electron launches, default setup
builds and installs a Debian app package, then opens the installed app. This
also requests administrator permission and keeps Electron's sandbox enabled.
--no-launch prepares source dependencies without building or installing an app.

By default, setup installs locked project dependencies and opens the app.
It does not synchronize chats or install/sign in to Claude Desktop.
Internet access is needed for missing prerequisites and project dependencies.
Manual developer installation remains available in README.md.
HELP
}

parse_options() {
  while (($#)); do
    case "$1" in
      --check) SETUP_CHECK=1; SETUP_LAUNCH=0 ;;
      --no-launch) SETUP_LAUNCH=0 ;;
      --help|-h) help; return 2 ;;
      *) fail "Unknown option: $1. Use --help."; return 1 ;;
    esac
    shift
  done
}

read_linux_release() {
  local file=$1 key value
  LINUX_ID=''; LINUX_VERSION=''
  [[ -r "$file" ]] || { fail 'Linux distribution information is unavailable.'; return 1; }
  while IFS='=' read -r key value; do
    value=${value#\"}; value=${value%\"}
    case "$key" in ID) LINUX_ID=$value ;; VERSION_ID) LINUX_VERSION=$value ;; esac
  done < "$file"
  case "$LINUX_ID:$LINUX_VERSION" in
    ubuntu:*)
      [[ "$LINUX_VERSION" =~ ^([0-9]+)\.([0-9]+)$ ]] || { fail 'Could not read the Ubuntu version.'; return 1; }
      ((10#${BASH_REMATCH[1]} > 22 || (10#${BASH_REMATCH[1]} == 22 && 10#${BASH_REMATCH[2]} >= 4))) || { fail 'Ubuntu 22.04 or newer is required.'; return 1; }
      ;;
    debian:*)
      [[ "$LINUX_VERSION" =~ ^([0-9]+)(\.[0-9]+)?$ ]] || { fail 'Could not read the Debian version.'; return 1; }
      ((10#${BASH_REMATCH[1]} >= 12)) || { fail 'Debian 12 or newer is required.'; return 1; }
      ;;
    *) fail 'Automatic Linux setup supports Ubuntu 22.04+ and Debian 12+.'; return 1 ;;
  esac
}

detect_platform() {
  case "$(uname -s)" in
    Darwin)
      SETUP_PLATFORM=darwin
      local version
      version=$(sw_vers -productVersion)
      [[ "$version" =~ ^([0-9]+)\. ]] && ((10#${BASH_REMATCH[1]} >= 13)) || { fail 'macOS 13 or newer is required.'; return 1; }
      ;;
    Linux)
      SETUP_PLATFORM=linux
      case "$(uname -r)" in *[Mm]icrosoft*|*[Ww][Ss][Ll]*) fail 'Run the Windows setup.bat in native Windows, outside WSL.'; return 1 ;; esac
      read_linux_release /etc/os-release
      ;;
    *) fail 'Use setup.bat on Windows. This script supports macOS and Linux.'; return 1 ;;
  esac
  case "$(uname -m)" in
    x86_64|amd64) SETUP_ARCH=x64 ;;
    arm64|aarch64) SETUP_ARCH=arm64 ;;
    *) fail 'An x64 or arm64 computer is required.'; return 1 ;;
  esac
  SETUP_NODE_DIR="$SETUP_ROOT/.sandbox/setup/node-v$NODE_VERSION-$SETUP_PLATFORM-$SETUP_ARCH"
}

node_usable() {
  command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 || return 1
  node -e 'const v=process.versions.node.split(".").map(Number); process.exit((v[0]>22 || (v[0]===22 && v[1]>=12)) && process.arch===process.argv[1] ? 0 : 1)' "$SETUP_ARCH" >/dev/null 2>&1 || return 1
  npm --version >/dev/null 2>&1
}

find_node() {
  node_usable && return 0
  if [[ -x "$SETUP_NODE_DIR/bin/node" && -x "$SETUP_NODE_DIR/bin/npm" ]]; then
    PATH="$SETUP_NODE_DIR/bin:$PATH"
    export PATH
  fi
  node_usable
}

find_python() {
  local candidate resolved
  for candidate in "${CLAUDE_SYNC_PYTHON:-}" python3 /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    [[ -n "$candidate" ]] || continue
    resolved=$(command -v "$candidate" 2>/dev/null) || continue
    # Apple's placeholder can open a developer-tools installer merely when run.
    if [[ ${SETUP_PLATFORM:-} == darwin && "$resolved" == /usr/bin/python3 ]]; then
      xcode-select -p >/dev/null 2>&1 || continue
    fi
    if "$resolved" -B -c 'import sys, venv, ensurepip; sys.exit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
      SETUP_PYTHON=$resolved
      return 0
    fi
  done
  return 1
}

package_installed() {
  [[ "$(dpkg-query -W -f='${db:Status-Status}' "$1" 2>/dev/null || true)" == installed ]]
}

linux_package_groups() {
  printf '%s\n' ca-certificates curl tar python3 python3-venv libnss3 libgbm1 libxss1 libx11-xcb1 libdrm2 libxcb-dri3-0 \
    'libgtk-3-0t64|libgtk-3-0' 'libasound2t64|libasound2' 'libatk-bridge2.0-0t64|libatk-bridge2.0-0'
}

group_installed() {
  local group=$1 candidate
  local candidates=()
  local old_ifs=$IFS
  IFS='|'; read -r -a candidates <<< "$group"; IFS=$old_ifs
  for candidate in "${candidates[@]}"; do package_installed "$candidate" && return 0; done
  return 1
}

linux_packages_missing() {
  local group
  while IFS= read -r group; do
    if ! group_installed "$group"; then return 0; fi
  done < <(linux_package_groups)
  return 1
}

install_linux_packages() {
  local group candidate package policy
  local packages=()
  local candidates=()
  say 'Installing missing Ubuntu/Debian prerequisites. sudo may request your administrator password.'
  sudo apt-get update
  while IFS= read -r group; do
    group_installed "$group" && continue
    IFS='|' read -r -a candidates <<< "$group"
    candidate=''
    for package in "${candidates[@]}"; do
      policy=$(apt-cache policy "$package" 2>/dev/null || true)
      if [[ "$policy" =~ Candidate:[[:space:]]+([^[:space:]]+) ]] && [[ ${BASH_REMATCH[1]} != '(none)' ]]; then
        candidate=$package; break
      fi
    done
    [[ -n "$candidate" ]] || { fail "No installable package found for $group. Check your distribution's package sources."; return 1; }
    packages+=("$candidate")
  done < <(linux_package_groups)
  if ((${#packages[@]})); then sudo apt-get install -y -- "${packages[@]}"; fi
}

begin_download() {
  command -v curl >/dev/null 2>&1 || { fail 'curl is unavailable. Install curl and retry.'; return 1; }
  mkdir -p -- "$SETUP_ROOT/.sandbox/setup"
  SETUP_TEMP=$(mktemp -d "$SETUP_ROOT/.sandbox/setup/download.XXXXXX")
}

download_file() {
  curl --fail --show-error --location --proto '=https' --proto-redir '=https' --tlsv1.2 --retry 2 --connect-timeout 20 --output "$2" "$1"
}

verify_sha256() {
  local actual
  if command -v shasum >/dev/null 2>&1; then actual=$(shasum -a 256 "$1");
  elif command -v sha256sum >/dev/null 2>&1; then actual=$(sha256sum "$1");
  else fail 'A SHA-256 verification tool is unavailable.'; return 1; fi
  actual=${actual%% *}
  [[ "$actual" == "$2" ]] || { fail 'The downloaded file failed its SHA-256 check. Nothing from this download was installed.'; return 1; }
}

install_node() {
  local archive checksum
  archive="node-v$NODE_VERSION-$SETUP_PLATFORM-$SETUP_ARCH.tar.gz"
  # Pinned hashes from https://nodejs.org/dist/v22.23.3/SHASUMS256.txt.
  case "$SETUP_PLATFORM-$SETUP_ARCH" in
    darwin-arm64) checksum=23b25245dcfb9af7262f8ff142e9e2e0af025368117329e7a7458a51e5922f53 ;;
    darwin-x64) checksum=8a677b0219178efd6eb0e475457c4afb452b521a92f6e67845a73bd85727f2a8 ;;
    linux-arm64) checksum=5ced2d48d1d7198739b7f86804de0171aefb6823b684b12341d3321afc3cb0b2 ;;
    linux-x64) checksum=1084aa36196bba4c3a5e69a1ee388a6e4ff729dad09445fbcd434b28fe3c24af ;;
  esac
  say "Downloading official Node.js $NODE_VERSION for $SETUP_PLATFORM/$SETUP_ARCH."
  begin_download
  download_file "https://nodejs.org/dist/v$NODE_VERSION/$archive" "$SETUP_TEMP/$archive"
  verify_sha256 "$SETUP_TEMP/$archive" "$checksum"
  tar -xzf "$SETUP_TEMP/$archive" -C "$SETUP_TEMP"
  [[ -x "$SETUP_TEMP/${archive%.tar.gz}/bin/node" ]] || { fail 'The Node.js archive is incomplete.'; return 1; }
  if [[ -e "$SETUP_NODE_DIR" ]]; then
    fail "The existing private Node.js directory is unusable. Remove $SETUP_NODE_DIR and retry."; return 1
  fi
  mv -- "$SETUP_TEMP/${archive%.tar.gz}" "$SETUP_NODE_DIR"
  rm -rf -- "$SETUP_TEMP"; SETUP_TEMP=''
  find_node || { fail 'The downloaded Node.js runtime could not run on this computer.'; return 1; }
}

python_signature_trusted() {
  local signature=$1
  [[ "$signature" == *'Developer ID Installer: Python Software Foundation (BMM5U3QVKW)'* ]] && \
    { [[ "$signature" == *'Status: signed by a certificate trusted by'* ]] || \
      [[ "$signature" == *'Status: signed by a developer certificate issued by Apple for distribution'* && "$signature" == *'Notarization: trusted by the Apple notary service'* ]]; } || {
    fail 'The Python installer is not signed by a trusted Python Software Foundation certificate.'; return 1;
  }
}

verify_python_signature() {
  local signature
  signature=$(LC_ALL=C /usr/sbin/pkgutil --check-signature "$1") || { fail 'Python installer signature verification failed.'; return 1; }
  python_signature_trusted "$signature"
}

install_mac_python() {
  local installer="python-$PYTHON_VERSION-macos11.pkg"
  say "Downloading Python $PYTHON_VERSION from Python.org."
  begin_download
  download_file "https://www.python.org/ftp/python/$PYTHON_VERSION/$installer" "$SETUP_TEMP/$installer"
  # https://www.python.org/downloads/release/python-3148/
  verify_sha256 "$SETUP_TEMP/$installer" 507fc086c5c006ff875d344a75b4e67b8fb3c401f1bc4908c6250adb673d4907
  verify_python_signature "$SETUP_TEMP/$installer"
  # Keep the user's shell profile and existing /usr/local/bin links intact.
  cat > "$SETUP_TEMP/python-choices.plist" <<'CHOICES'
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><array>
<dict><key>choiceIdentifier</key><string>org.python.Python.PythonProfileChanges-3.14</string><key>choiceAttribute</key><string>selected</string><key>attributeSetting</key><integer>0</integer></dict>
<dict><key>choiceIdentifier</key><string>org.python.Python.PythonUnixTools-3.14</string><key>choiceAttribute</key><string>selected</string><key>attributeSetting</key><integer>0</integer></dict>
</array></plist>
CHOICES
  say 'Installing the verified Python package. sudo may request your administrator password.'
  sudo /usr/sbin/installer -pkg "$SETUP_TEMP/$installer" -target / -applyChoiceChangesXML "$SETUP_TEMP/python-choices.plist"
  rm -rf -- "$SETUP_TEMP"; SETUP_TEMP=''
  find_python || { fail 'Python 3.10+ with virtual-environment support could not be found after installation.'; return 1; }
  # Use Apple's trusted system roots for this Python's isolated build environments.
  # This avoids a separate global pip installation to initialize certificates.
  local cert_dir="$SETUP_ROOT/.sandbox/setup"
  /usr/bin/security find-certificate -a -p /System/Library/Keychains/SystemRootCertificates.keychain > "$cert_dir/macos-ca.pem"
  if [[ -z ${SSL_CERT_FILE:-} ]]; then export SSL_CERT_FILE="$cert_dir/macos-ca.pem"; fi
}

cleanup_download() { if [[ -n "$SETUP_TEMP" && -d "$SETUP_TEMP" ]]; then rm -rf -- "$SETUP_TEMP"; fi; }

linux_apparmor_restricted() {
  local setting=${1:-/proc/sys/kernel/apparmor_restrict_unprivileged_userns}
  local value=''
  [[ ${SETUP_PLATFORM:-} == linux && -r "$setting" ]] || return 1
  value=$(< "$setting")
  [[ ${value//[[:space:]]/} == 1 ]]
}

installed_linux_app_available() { [[ -x /usr/bin/claude-code-user-sync ]]; }

build_install_linux_app() {
  local package=./release/setup-linux/claude-code-user-sync-setup.deb
  say 'Linux restricts launching Electron directly from source. Preparing the installed app with its normal sandbox support.'
  say 'Building the Linux Debian package and its bundled Python helper. This may take several minutes.'
  npm run build:backend -- --platform linux || { fail 'The Linux helper could not be built. The app was not installed or opened.'; return 1; }
  npm exec -- electron-builder --config desktop/scripts/builder-config.cjs --linux deb "--$SETUP_ARCH" --publish never \
    --config.directories.output=release/setup-linux --config.artifactName=claude-code-user-sync-setup.deb || {
      fail 'The Linux app package could not be built. The app was not installed or opened.'; return 1;
    }
  [[ -f "$package" && ! -L "$package" ]] || { fail 'The expected Linux app package is missing. The app was not installed or opened.'; return 1; }
  say 'Installing the locally built Debian app. sudo may request your administrator password.'
  # Reinstall the exact artifact so changes within the same app version are used.
  sudo apt-get install -y --reinstall -- "$package" || { fail 'The Linux app could not be installed. The app was not opened.'; return 1; }
  installed_linux_app_available || { fail 'The installed Linux app launcher could not be found.'; return 1; }
  say 'Opening the installed Claude Code User Sync app. Synchronization starts only when you click its sync button.'
  /usr/bin/claude-code-user-sync
}

main() {
  local status=0
  parse_options "$@" || { status=$?; [[ $status == 2 ]] && return 0; return "$status"; }
  [[ -f "$SETUP_ROOT/package.json" && -f "$SETUP_ROOT/package-lock.json" ]] || { fail 'Keep setup.sh in the complete project folder, alongside package.json and package-lock.json.'; return 1; }
  detect_platform
  say "Checking Claude Code User Sync prerequisites ($SETUP_PLATFORM/$SETUP_ARCH)."
  if find_node; then say "Node.js/npm: ready ($(node --version))."; else say 'Node.js/npm: missing or unsuitable; Node.js 22.12+ is required.'; status=1; fi
  if find_python; then say 'Python 3.10+ and virtual-environment support: ready.'; else say 'Python 3.10+ with virtual-environment support: missing.'; status=1; fi
  if [[ "$SETUP_PLATFORM" == linux ]] && linux_packages_missing; then say 'Linux desktop/system prerequisites: missing.'; status=1; fi
  if linux_apparmor_restricted; then
    say 'Linux source launch restriction detected: default setup will build/install a Debian app and open the installed app.'
    say '--no-launch prepares source dependencies only. --check does not build or install the app.'
  fi
  if ((SETUP_CHECK)); then
    if ((status)); then say 'Prerequisites are missing. Run setup.sh without --check to prepare the app.';
    else say 'All prerequisites are ready. No files were changed and the app was not opened.'; fi
    return "$status"
  fi
  [[ "$(id -u)" != 0 ]] || { fail 'Run setup as your normal desktop user. It requests sudo only when needed.'; return 1; }
  trap cleanup_download EXIT
  if [[ "$SETUP_PLATFORM" == linux ]] && linux_packages_missing; then install_linux_packages; fi
  if ! find_python; then
    if [[ "$SETUP_PLATFORM" == darwin ]]; then install_mac_python;
    else fail 'Python is still unavailable. Check python3 and python3-venv, then retry.'; return 1; fi
  fi
  if ! find_node; then install_node; fi
  export CLAUDE_SYNC_PYTHON="$SETUP_PYTHON"
  if [[ "$SETUP_PLATFORM" == darwin && -f "$SETUP_ROOT/.sandbox/setup/macos-ca.pem" && -z ${SSL_CERT_FILE:-} ]]; then
    export SSL_CERT_FILE="$SETUP_ROOT/.sandbox/setup/macos-ca.pem"
  fi
  cd -- "$SETUP_ROOT"
  say 'Installing the locked project dependencies and preparing the app.'
  npm ci --include=dev
  say 'Setup complete. Claude Desktop must be installed separately and signed in.'
  if ((SETUP_LAUNCH)); then
    if [[ "$SETUP_PLATFORM" == linux && -z ${DISPLAY:-} && -z ${WAYLAND_DISPLAY:-} ]]; then
      say 'No desktop session was detected. Open a desktop terminal and rerun setup.sh to open the app.'
      return 0
    fi
    if linux_apparmor_restricted; then build_install_linux_app;
    else
      say 'Opening Claude Code User Sync. Synchronization starts only when you click its sync button.'
      npm start
    fi
  else say 'The app was prepared without opening it. Rerun setup.sh when you want to open it.'; fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
