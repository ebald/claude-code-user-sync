# Claude Code User Sync desktop app

A shared Electron interface for macOS and Windows, backed by the existing Python synchronization engine. The main [README](../README.md) explains the scope of synchronization and the command-line tool.

## Run from source

Use macOS 13 or newer or Windows 10/11. Install Node.js 22.12 or newer, npm and Python 3.10 or newer. For source launches on macOS, your Python installation must also support your macOS version. From the repository root:

```sh
npm ci
npm start
```

In Windows PowerShell, use `npm.cmd` in place of `npm` in the commands in this guide. On macOS, the app locates `python3`. On Windows, install the Python launcher and confirm `py -3 --version` in a new PowerShell window. Run the app in native Windows, outside WSL.

The setup downloads Electron and build dependencies. The app loads its interface, translations and synchronization engine locally; synchronization does not make model calls or upload your chats.

## Sync your chats

1. Initialize both accounts in Claude Desktop: sign in to each, open Code, select the Local environment and create a local conversation on this computer.
2. Finish active work in Claude before starting a sync.
3. Select **English**, **Español** or **Português** in the language selector.
4. Click **Sync and reopen Claude**.
5. After Claude reopens, sign out and sign in to the account you want to use.

The app requests a normal shutdown, waits up to 30 seconds and checks that Claude has stopped before writing catalogs. It does not force-kill Claude. Account switching remains manual. The same interface and workflow serve both platforms; the platform-specific backend handles Claude discovery and shutdown.

The account count comes from local account directories, rather than the number of organization profiles. A single account can contain more than one organization profile.

Successful synchronization uses a success status. Unavailable files, histories or unresolved differences are stated specifically and can be reviewed in diagnostics. The file and backup controls open the saved result in Finder or File Explorer. If automatic Claude discovery fails on Windows, select the Claude executable through the app.

Windows synchronization remains experimental until the authenticated Claude Desktop workflow is verified on a real Windows computer.

## Languages

**i18next** manages the interface translations using JSON dictionaries in `desktop/locales/`:

- `en`: English, the default.
- `es`: Spanish.
- `pt-BR`: Brazilian Portuguese.

Use the same keys and interpolation placeholders in all dictionaries. Translation coverage is checked by the JavaScript tests. Selecting a language updates the interface and saves the preference for future launches. Filenames, diagnostic details and paths remain as recorded by the backend.

## Storage

The app saves language and selected paths in `settings.json` in its own user-data directory. The platform-specific synchronization engine preserves the existing backup and history locations for compatibility:

| Data | macOS | Windows |
| --- | --- | --- |
| App preferences | `~/Library/Application Support/Claude Code User Sync/settings.json` | `%APPDATA%\Claude Code User Sync\settings.json` |
| Synchronization backups | `~/Library/Application Support/Claude Account Sync/Backups/` | `%LOCALAPPDATA%\Claude Code User Sync\Backups\` |
| Saved synchronization result | `~/Library/Application Support/Claude Account Sync/last-sync.json` | `%LOCALAPPDATA%\Claude Code User Sync\last-sync.json` |
| Claude catalog, standard install | `~/Library/Application Support/Claude/claude-code-sessions/` | `%APPDATA%\Claude\claude-code-sessions\` |
| Local conversation transcripts | `~/.claude/projects/` | `%USERPROFILE%\.claude\projects\` |

Windows MSIX installations can use a different Claude data directory, which the backend checks when present. If installations are ambiguous, select the Claude data directory and chat-history directory in the app settings. The [CLI data overrides](../README.md#windows-data-locations) allow an explicit data directory.

Backups and diagnostic files can contain private conversation data, paths and links. On macOS they use owner-only permissions; on Windows they inherit their parent directory's access permissions. Keep them inside your own user profile. The older macOS storage name is intentional so that existing backups remain available.

## Build packaged apps

Build on the target operating system. The Python runtime produced on macOS cannot run on Windows, or vice versa.

```sh
npm run build:backend
```

This runs `desktop/scripts/build_backend.py`, creates an isolated virtual environment under `.sandbox/electron-backend/venv/`, installs a pinned PyInstaller version and creates a self-contained backend under `desktop/backend-dist/claude-sync-backend/`. These generated directories are excluded from Git.

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

### Unpacked app

On either target platform:

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

GitHub Actions is configured to run synthetic Python tests on macOS and Windows, run the Electron tests, build a self-contained backend and package an unpacked app on each operating system. Automated and preview checks do not establish that every authenticated Claude Desktop workflow works.

## Architecture

- The Electron main process controls the app window, preferences and approved desktop actions.
- A narrow preload bridge exposes specific operations to the interface.
- The shared renderer uses local HTML, CSS, JavaScript and i18next dictionaries.
- The Python backend handles account discovery, catalog validation, normal Claude shutdown, backups, synchronization and reopening Claude.
- Packaged builds run the bundled backend executable; source launches use an installed Python interpreter.

The app interface runs with context isolation, sandboxing and Node integration disabled. It loads local resources with a restrictive content security policy and validates IPC requests. Conversation content is handled by the Python engine; the interface displays operation summaries and diagnostics.
