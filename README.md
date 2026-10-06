# Claude Code User Sync

**Keep your local Claude Code chats available when switching Claude user accounts on the same computer.**

English · [Español](docs/README.es.md) · [Português](docs/README.pt-BR.md)

Claude Code User Sync synchronizes the chat catalogs used by the **Code tab in Claude Desktop** across locally detected accounts. It includes one Electron desktop app for macOS and Windows, plus a Python command-line tool, with automatic backups and a way to undo changes. The app offers English, Spanish and Portuguese.

For example, if you started a local Code conversation while signed in to account A, syncing makes its catalog entry available to account B too. The conversation history remains in the shared local storage; the tool updates the records that make it appear in each account's chat list.

This is a local utility. It does not transfer chats between cloud accounts or computers, and it does not synchronize the regular web chat history on claude.ai. It is an independent project, unaffiliated with Anthropic.

## Features

- Discover local account profiles automatically, including more than two accounts.
- Synchronize local Code chats across all detected profiles and projects.
- Preserve titles, conversation identifiers, archive state, stars and history references.
- Use the most recent activity to resolve catalog differences; keep conflicting versions with the same timestamp for review.
- Respect deletion markers and exclude automation, SSH, WSL and remote sessions.
- Preserve artifact references, check embedded images and back up available linked local files.
- Recover previously backed-up files when their original temporary files are gone.
- Create private backups before applying catalog changes and refuse to undo over newer changes.
- Run the synchronization and asset checks locally, without model calls or network requests.

## Requirements and platform support

- **macOS 13 or newer, or Windows 10/11**, with [Claude Desktop](https://support.claude.com/en/articles/10065433-install-claude-desktop) installed and local conversations in its Code tab.
- At least two locally initialized Claude account profiles. Sign in to each account, open the Code tab, select the Local environment and create a conversation on that computer before syncing.
- To run from source: **Node.js 22.12 or newer**, npm and **Python 3.10 or newer**. The Python synchronization engine uses only the standard library. On macOS, use a Python installation compatible with your macOS version.
- Packaged builds include Electron and the Python engine; destination computers do not need Node.js or Python installed separately. A packaged macOS build may require a version newer than macOS 13, depending on the Python runtime used to build it.

| Platform | Desktop app | Validation status |
| --- | --- | --- |
| macOS | Electron app, built for the Mac's current architecture | Local automated tests and preview checks; authenticated workflows depend on Claude Desktop's internal format |
| Windows | The same Electron interface; Windows x64 installer | Experimental; authenticated Claude Desktop synchronization has not yet been verified on a Windows machine |

Run Windows commands in regular Windows PowerShell, outside WSL. WSL, SSH and cloud sessions are excluded. Build the packaged app on its target operating system so it includes the correct Python executable.

## Get the source

Install [Git](https://git-scm.com/downloads), [Node.js](https://nodejs.org/en/download) and [Python](https://www.python.org/downloads/) if needed. Open Terminal on macOS or PowerShell on Windows:

```sh
git clone https://github.com/ebald/claude-code-user-sync.git
cd claude-code-user-sync
npm ci
```

In Windows PowerShell, use `npm.cmd ci` for the installation command above. You can also use **Code → Download ZIP** on GitHub, extract it and open a terminal in the extracted folder. All commands below run from that folder. The build dependencies and Electron runtime are downloaded during setup; synchronization itself runs locally.

## macOS instructions

Confirm the prerequisites, then start the Electron app:

```sh
node --version
python3 --version
npm start
```

### Use the app

1. Finish any running work in Claude.
2. Choose **English**, **Español** or **Português** in the language selector. The app saves your choice between launches.
3. Click **Sync and reopen Claude**.
4. Wait for Claude to close, the catalogs to synchronize and Claude to reopen.
5. Sign out and sign in to the other account in Claude.

The app requests a normal shutdown and waits up to 30 seconds; it does not force Claude to quit. Account switching remains manual. The file, diagnostics and backup controls let you inspect the result. A successful sync stays a success even if a linked file is unavailable; the status states the specific missing content and diagnostics provide details.

To try the interface with example results:

```sh
npm run preview
```

Preview does not synchronize live catalogs, close Claude or save app preferences. It detects the account count from local directories and clearly labels its other figures as example data.

### Build a macOS app

```sh
npm run build:mac
```

This creates a DMG and ZIP in `release/` for the current Mac architecture. The build first creates an isolated Python build environment and bundles the synchronization engine with PyInstaller. It records the app’s required macOS version from Electron and the bundled Python runtime, using whichever minimum is newer. The app uses a local ad hoc signature and is not notarized. For an unpacked app directory instead of installers:

```sh
npm run pack
```

See the [Electron app guide](desktop/README.md) for build details, storage locations and tests.

### Terminal or Finder launcher

Quit Claude completely with **Cmd+Q** and finish any running Claude Code processes, then run:

```sh
python3 claude_sync.py sync --live
```

Alternatively, open `sync.command` from Finder. After synchronization, reopen Claude and sign in to the account you want to use.

`sync --live` synchronizes all detected local profiles and projects. It reports counts, unresolved differences, unavailable histories and asset issues, along with the backup location. It can mirror a catalog entry even when the transcript is missing, but it cannot recreate missing conversation content.

## Windows instructions

1. Install Node.js 22.12 or newer and Python 3.10 or newer from their official sites, including the Python launcher. Open a new PowerShell window after installation.
2. Download or clone this project, open PowerShell in its folder and run `npm.cmd ci` if you have not already done so.
3. Confirm the prerequisites and start the same Electron app used on macOS:

   ```powershell
   node --version
   py -3 --version
   npm.cmd start
   ```

Choose your language, finish active Claude tasks and click **Sync and reopen Claude**. The app requests a normal shutdown, checks that Claude has stopped, synchronizes and tries to reopen Claude. It does not force-kill Claude. Switch accounts manually after Claude reopens. The app can use a selected Claude executable if the installed app is not discovered automatically.

To try the interface without changing Claude data:

```powershell
npm.cmd run preview
```

### Build a Windows installer

Run on a Windows x64 computer with x64 Node.js and Python:

```powershell
npm.cmd run build:win
```

The build creates an isolated Python build environment, bundles the synchronization engine with PyInstaller and creates an NSIS installer in `release/`. The installed app includes Electron, Python, the backend and translations; the destination computer does not need Node.js or Python separately. The installer is unsigned. The build does not install the app or change Claude data.

Use `npm.cmd run pack` on Windows for an unpacked application directory instead of an installer. Building from source requires the prerequisites above; running the packaged app does not.

### PowerShell or File Explorer launcher

1. Finish any running Claude tasks. Quit Claude using its menu or system tray; closing its window may leave it running. Close active Claude Code terminals too. The synchronizer checks for Claude processes and refuses to write while they are running.
2. Run:

   ```powershell
   py -3 claude_sync.py sync --live
   ```

3. Reopen Claude from the Start menu, then sign out and sign in to your other account.

You can also double-click `sync.cmd` in File Explorer after quitting Claude. If `py` is unavailable but Python is on your PATH, use `python` instead of `py -3` in the commands below. No administrator privileges are needed for normal synchronization of your own user data.

### Windows data locations

The tool looks for the catalog under `%APPDATA%\Claude\claude-code-sessions`, and also checks Claude's MSIX user-data locations when present. Transcripts normally live in `%USERPROFILE%\.claude\projects`.

If the catalog is missing or more than one installation is detected, choose the correct Claude data and chat-history folders in the app settings, or pass the directories explicitly to the CLI. `--app-data` takes the **parent** of `claude-code-sessions`; both global options go before the command:

```powershell
py -3 claude_sync.py --app-data "C:\path\to\Claude" --projects-dir "C:\path\to\.claude\projects" sync --live
```

Use the native Windows paths for the profiles you intend to synchronize. The tool does not copy conversations between Windows and macOS machines or between Windows user logins.

Windows asset checks currently support ordinary files on local drives. Network shares, junctions, symbolic links and cloud placeholder reparse points are refused. Make any needed cloud file available as a regular local file before syncing.

## Backups and undo

The command-line tool saves each operation under `.sandbox/sync-<id>/` in the project directory. To choose another private storage directory:

```sh
python3 claude_sync.py sync --live --storage-dir /path/to/private-backups
```

On Windows:

```powershell
py -3 claude_sync.py sync --live --storage-dir "$env:LOCALAPPDATA\Claude Code User Sync\Backups"
```

The Electron app keeps macOS backups under:

```text
~/Library/Application Support/Claude Account Sync/Backups/
```

The Windows app stores backups under `%LOCALAPPDATA%\Claude Code User Sync\Backups\`. The internal macOS storage name is retained for compatibility with earlier versions. The Electron app keeps its own preferences in its standard user-data directory; see the [app guide](desktop/README.md#storage) for details. Each operation includes a catalog snapshot, the original files needed for undo and an asset manifest. Available linked files are preserved under that operation's `asset-snapshot/` directory. On macOS, backup directories and files use owner-only permissions. Windows backups inherit the access permissions of their parent directory, so store them inside your own user profile rather than a shared folder.

To undo a live synchronization, quit Claude completely and use the exact backup path printed by that operation:

```sh
python3 claude_sync.py undo \
  --root "$HOME/Library/Application Support/Claude/claude-code-sessions" \
  --backup .sandbox/sync-OPERATION_ID/backup \
  --live
```

Replace `OPERATION_ID` with the operation ID, or supply the full backup path if you used the app or a custom storage directory. Undo refuses to overwrite records changed since the synchronization.

For Windows's standard data location, quit Claude and run:

```powershell
py -3 claude_sync.py undo --root "$env:APPDATA\Claude\claude-code-sessions" --backup ".sandbox\sync-OPERATION_ID\backup" --live
```

For an MSIX or custom location, supply the same `--app-data` override before `undo` and use that directory's `claude-code-sessions` as `--root`.

## Try it on a local copy

You can inspect and apply a plan to a private copy before changing the live catalogs. Use a new destination directory for each copy; keep Claude idle or closed while copying.

The following examples use macOS shell syntax. A Windows PowerShell example is included below.

```sh
python3 claude_sync.py sandbox --dest .sandbox/demo

python3 claude_sync.py plan \
  --root .sandbox/demo/registry \
  --projects .sandbox/demo/config/projects \
  --out .sandbox/demo/plan.json

python3 claude_sync.py apply \
  --root .sandbox/demo/registry \
  --plan .sandbox/demo/plan.json \
  --backup .sandbox/demo/backup
```

By default, `plan` leaves divergent records unresolved and excludes entries without a readable local transcript. Add `--resolve-newest` to use the latest activity, or `--all-chats` to include unavailable histories. Different versions tied for the latest activity remain unresolved.

To undo changes to the copy:

```sh
python3 claude_sync.py undo \
  --root .sandbox/demo/registry \
  --backup .sandbox/demo/backup
```

Plans become invalid if catalog files or required transcripts change before application.

Windows PowerShell equivalent:

```powershell
py -3 claude_sync.py sandbox --dest .sandbox/demo
py -3 claude_sync.py plan --root .sandbox/demo/registry --projects .sandbox/demo/config/projects --out .sandbox/demo/plan.json
py -3 claude_sync.py apply --root .sandbox/demo/registry --plan .sandbox/demo/plan.json --backup .sandbox/demo/backup
py -3 claude_sync.py undo --root .sandbox/demo/registry --backup .sandbox/demo/backup
```

## Inspect artifacts and linked files

Run an asset audit without changing the catalogs:

```sh
python3 claude_sync.py audit --out .sandbox/asset-audit.json
```

On Windows, use `py -3 claude_sync.py audit --out .sandbox/asset-audit.json`.

The audit checks artifact references, embedded image encoding and file signatures, and available local file paths. It records remote links without downloading them or checking account access. The output distinguishes missing delivered files from historical references and records failed delivery attempts separately.

Hosted artifacts keep their original URLs and access permissions. Backing up a linked file does not guarantee that all dependencies of an interactive project are included.

## Development and tests

```sh
npm test
python3 -m unittest discover
```

On Windows, use `py -3 -m unittest discover` for the Python suite. GitHub Actions is configured to run synthetic Python tests on both operating systems, test the Electron workflow and translations, and build a packaged backend and unpacked app on each platform.

The desktop app uses **i18next** with English, Spanish and Brazilian Portuguese JSON dictionaries in `desktop/locales/`. One interface and the same translation keys serve macOS and Windows. Tests check language coverage and interpolation placeholders. English is the default, and the selected language persists between launches.

The suites use synthetic catalogs and transcripts. They cover multiple accounts, new profiles, repeated syncs, conflict handling, deletion markers, artifact recovery, file checks, stale plans, undo and the desktop workflow. See the [app guide](desktop/README.md#tests-and-preview) for preview and packaging commands.

For an additional read check with the pinned Anthropic Agent SDK:

```sh
npm ci

node validate_sessions.mjs \
  --sandbox .sandbox/demo \
  --profile account-1/org-local \
  --out .sandbox/demo/validation.json
```

Choose a profile directory that exists in the copied registry. In Windows PowerShell, put the `node` command on one line rather than using the shell line-continuation characters shown above. The validator reads the copied transcripts, clears credential environment variables and blocks network and subprocess operations during the check. It reports counts and hashes without printing messages. This optional validator uses the pinned SDK; the Electron app does not use it during synchronization.

## Privacy and limitations

- Credentials, account login state and original transcripts are not copied between accounts or modified by synchronization.
- Permission grants, connector configuration and live process state are not transferred.
- Sandbox copies, plans, diagnostics and backups can contain private conversation content, paths and links. Keep them private; the repository excludes the standard generated-data locations.
- The utility depends on Claude Desktop's internal catalog format. Compatibility may change with Desktop updates, and synthetic tests cannot guarantee every authenticated in-app workflow.
- Only existing local data is available: missing transcripts or files cannot be reconstructed, and cloud access permissions are not transferred.

When reporting a problem, include the command, operating system and Claude Desktop versions, and a sanitized error message. Avoid uploading real transcripts, backup folders or raw diagnostic manifests.
