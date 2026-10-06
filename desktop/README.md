# Claude Code User Sync desktop app

English · [Español](README.es.md) · [Português](README.pt-BR.md)

A shared Electron interface for macOS, Windows and Linux, backed by the existing Python synchronization engine. The main [README](../README.md) explains the scope of synchronization and the command-line tool.

## Run from source

Use macOS 13 or newer, Windows 10/11, or Ubuntu 22.04+/Debian 12+ with the official [Claude Desktop Linux beta](https://code.claude.com/docs/en/desktop-linux). Linux supports x64 and arm64. Run the app in native Windows, outside WSL. Packaged apps already include Electron and Python; the following setup is for a downloaded or cloned source tree.

### Automatic setup

From the repository root, run `bash ./setup.sh` on macOS or Linux, or `.\setup.bat` in PowerShell on native Windows x64. On macOS you can also double-click `setup.command`; on Windows, double-click `setup.bat`.

The scripts check installed tools, install missing prerequisites, run `npm ci --include=dev` and open the Electron app. Installation requires an internet connection. Opening the app does not synchronize Claude data. Compatible existing Node.js, npm and Python installations are reused.

On Linux where AppArmor restricts launching Electron from source, default setup builds and installs the `.deb` package, then opens the installed app as your normal user. Installation may request your administrator password. After installation, open the app directly from your application menu on later launches. This covers the restrictions used by Ubuntu 24.04 and newer. `--no-launch` prepares source dependencies without building or installing the app package; `--check` reports the required launch route without changing anything.

```sh
# macOS / Linux: read-only prerequisite check
bash ./setup.sh --check
# Prepare without opening the app
bash ./setup.sh --no-launch
```

```powershell
# Windows
.\setup.bat --check
.\setup.bat --no-launch
```

`--check` exits successfully when the prerequisites are ready, or reports missing prerequisites and exits with status 1. Add `--help` to either launcher to see its available options.

The console messages are in English; the app follows its operating system language preference. For source launches, run the setup script again to open the app later. See the [automatic setup guide](../README.md#automatic-setup) for platform installation details.

### Manual setup for developers

If automatic setup used a project-local runtime, launch the app later through the setup script. Manual `npm` commands require Node.js and npm on your normal PATH.

Install Node.js 22.12 or newer, npm and Python 3.10 or newer. For source launches on macOS, your Python installation must also support your macOS version. From the repository root:

```sh
npm ci
npm start
```

In Windows PowerShell, use `npm.cmd` in place of `npm` in the commands in this guide. On macOS and Linux, the app locates `python3`. On Windows, install the Python launcher and confirm `py -3 --version` in a new PowerShell window.

Setup downloads Electron and build dependencies. The app loads its interface, translations and synchronization engine locally; synchronization does not make model calls or upload your chats.

## Sync your chats

1. Initialize both accounts in Claude Desktop: sign in to each, open Code, select the Local environment and create a local conversation on this computer.
2. Finish active work in Claude before starting a sync.
3. Keep **System language** selected to follow your operating system’s language, or choose **English**, **Español** or **Português**.
4. Click **Sync and reopen Claude**.
5. After Claude reopens, sign out and sign in to the account you want to use.

The app requests a normal shutdown, waits up to 30 seconds and checks that Claude has stopped before writing catalogs. On Linux, automatic shutdown is available for the verified official Claude Desktop installation; finish active Claude Code terminals too. If shutdown cannot be requested safely or processes remain active, quit Claude completely and try again. It does not force-kill Claude. Account switching remains manual. The same interface and workflow serve all three platforms; the platform-specific backend handles Claude discovery and shutdown.

The account count comes from local account directories, rather than the number of organization profiles. A single account can contain more than one organization profile.

Successful synchronization uses a success status. Unavailable files, histories or unresolved differences are stated specifically and can be reviewed in diagnostics. The file and backup controls open the saved result in your operating system’s file manager. If automatic Claude discovery fails, select the Claude application or executable through the app.

Windows and Linux synchronization remain experimental until the authenticated Claude Desktop workflow is verified on real computers running those systems.

## Languages

**i18next** manages the interface translations using JSON dictionaries in `desktop/locales/`:

- `en`: English.
- `es`: Spanish.
- `pt-BR`: Brazilian Portuguese.

The app starts with **System language** selected and uses the operating system’s preferred supported language. Regional English and Spanish variants use the matching translation; every Portuguese variant uses Brazilian Portuguese. If none of the preferred languages is supported, the app falls back to English. Choosing a language manually updates the interface and saves the preference for future launches. Select **System language** to follow the operating system again.

Use the same keys and interpolation placeholders in all dictionaries. Translation coverage is checked by the JavaScript tests. Filenames, diagnostic details and paths remain as recorded by the backend.

## Storage

The app saves language and selected paths in `settings.json` in its own user-data directory. The platform-specific synchronization engine preserves the existing backup and history locations for compatibility:

| Data | macOS | Windows | Linux default |
| --- | --- | --- | --- |
| App preferences | `~/Library/Application Support/Claude Code User Sync/settings.json` | `%APPDATA%\Claude Code User Sync\settings.json` | `~/.config/Claude Code User Sync/settings.json` |
| Synchronization backups | `~/Library/Application Support/Claude Account Sync/Backups/` | `%LOCALAPPDATA%\Claude Code User Sync\Backups\` | `~/.local/share/Claude Code User Sync/Backups/` |
| Saved synchronization result | `~/Library/Application Support/Claude Account Sync/last-sync.json` | `%LOCALAPPDATA%\Claude Code User Sync\last-sync.json` | `~/.local/share/Claude Code User Sync/last-sync.json` |
| Claude catalog, standard install | `~/Library/Application Support/Claude/claude-code-sessions/` | `%APPDATA%\Claude\claude-code-sessions\` | `~/.config/Claude/claude-code-sessions/` |
| Local conversation transcripts | `~/.claude/projects/` | `%USERPROFILE%\.claude\projects\` | `~/.claude/projects/` |

Linux honors absolute `XDG_CONFIG_HOME` and `XDG_DATA_HOME` for its configuration and application data; the table shows their defaults. The official Linux command `claude-desktop` resolves to the executable under `/usr/lib/claude-desktop/`.

Windows MSIX installations can use a different Claude data directory, which the backend checks when present. If installations are ambiguous, select the Claude data directory and chat-history directory in the app settings. The [CLI data overrides](../README.md#windows-data-locations) allow an explicit data directory.

Backups and diagnostic files can contain private conversation data, paths and links. On macOS and Linux they use owner-only permissions; on Windows they inherit their parent directory's access permissions. Keep them inside your own user profile. The older macOS storage name is intentional so that existing backups remain available.

## Build packaged apps

Build on the target operating system and architecture. Each package includes a Python executable built for that platform.

```sh
npm run build:backend
```

This runs `desktop/scripts/build_backend.py`, creates an isolated virtual environment under `.sandbox/electron-backend/<platform>-<arch>/venv/`, installs a pinned PyInstaller version and creates a self-contained backend under `desktop/backend-dist/claude-sync-backend/`. These generated directories are excluded from Git.

### macOS

On a Mac:

```sh
npm run build:mac
```

The command bundles the backend and builds a DMG and ZIP in `release/` for the current Mac architecture. The app includes Electron and Python, so the destination Mac does not need a separate Node.js or Python installation. The required macOS version is the newer of Electron’s minimum and the minimum required by the bundled Python runtime. The build records that requirement in the app, so a packaged build can require a macOS version newer than 13. The local build receives an ad hoc signature and is not notarized.

### Windows

On Windows x64 with x64 Node.js and Python, in PowerShell:

```powershell
npm.cmd run build:win
```

The command bundles the backend and builds an NSIS installer in `release/`. The installed app includes Electron, Python and translations. The destination computer does not need Node.js or Python separately. The installer is unsigned.

### Linux

On native Ubuntu 22.04+/Debian 12+, use x64 or arm64 Node.js and Python for the current computer. Build on the oldest supported distribution you intend to target (Ubuntu 22.04 is the baseline); packages built on a newer system or with a newer Python runtime may require newer Linux libraries.

```sh
npm run build:linux
```

On Ubuntu 24.04 and newer, AppArmor may block Electron startup from source or from the portable archive. If startup fails with a sandbox error, install the `.deb` package, which includes an AppArmor profile for this app. You can create it with `npm run build:linux` without launching the source app first. See [Ubuntu’s release notes](https://documentation.ubuntu.com/release-notes/24.04/).

Install `python3-venv` if your distribution does not provide Python’s virtual-environment support by default. The build includes the Python backend and creates a Debian `.deb` installer and portable `.tar.gz` archive in `release/`. The destination computer does not need Node.js or Python installed separately. Open the `.deb` with your software installer, or extract the portable archive and run `claude-code-user-sync` as your normal user. Use the official [Claude Desktop Linux beta guide](https://code.claude.com/docs/en/desktop-linux) to install Claude itself.

### Unpacked app

On any target platform:

```sh
npm run pack
```

This builds the bundled backend and produces an unpacked app directory in `release/` for local validation. Building does not install the app or synchronize Claude data.

## Tests and preview

From the repository root:

```sh
npm test
python3 -m unittest discover
npm run preview
```

On Windows, use `py -3 -m unittest discover` for the Python suite.

Preview uses example synchronization results. Its account count is read from local directories; other figures are clearly labeled as example data. It does not close Claude, write catalogs, create synchronization backups or save preferences.

```sh
npm run smoke
# After npm run pack:
npm run smoke:packaged
```

The smoke checks launch the source or packaged Electron app in preview mode, exercise all three languages and the simulated synchronization workflow, and check the success status.

GitHub Actions is configured to run synthetic Python tests on macOS, Windows and Linux, run the Electron tests, build a self-contained backend and package an unpacked app on each operating system. Automated and preview checks do not establish that every authenticated Claude Desktop workflow works.

## Architecture

- The Electron main process controls the app window, preferences and approved desktop actions.
- A narrow preload bridge exposes specific operations to the interface.
- The shared renderer uses local HTML, CSS, JavaScript and i18next dictionaries.
- The Python backend handles account discovery, catalog validation, normal Claude shutdown, backups, synchronization and reopening Claude.
- Packaged builds run the bundled backend executable; source launches use an installed Python interpreter.

The app interface runs with context isolation, sandboxing and Node integration disabled. It loads local resources with a restrictive content security policy and validates IPC requests. Conversation content is handled by the Python engine; the interface displays operation summaries and diagnostics.
