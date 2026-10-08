# Claude Code User Sync

**Keep your local Claude Code chats available when switching Claude user accounts on the same computer.**

English · [Español](docs/README.es.md) · [Português](docs/README.pt-BR.md)

Claude Code User Sync synchronizes the chat catalogs used by the **Code tab in Claude Desktop** across locally detected accounts. It includes one Electron desktop app for macOS, Windows and Linux, plus a Python command-line tool, with automatic backups and a way to undo changes. The app offers English, Spanish and Portuguese.

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

- **macOS 13 or newer, Windows 10/11 x64, Windows 11 ARM64, or Ubuntu 22.04+/Debian 12+**, with Claude Desktop installed and local conversations in its Code tab. Use the [macOS/Windows installation guide](https://support.claude.com/en/articles/10065433-install-claude-desktop) or the official [Linux beta guide](https://code.claude.com/docs/en/desktop-linux). Linux supports x64 and arm64.
- At least two locally initialized Claude account profiles with access to the Code tab through a [Pro, Max, Team or Enterprise subscription](https://code.claude.com/docs/en/desktop-quickstart). Sign in to each account, open the Code tab, select the Local environment and create a conversation on that computer before syncing.
- To run from source: **Node.js 22.12 or newer**, npm and **Python 3.10 or newer**. The Python synchronization engine uses only the standard library. On macOS, use a Python installation compatible with your macOS version. On Windows, use x64 Node.js and Python; Windows 11 ARM64 runs these tools and Electron through x64 emulation.
- Packaged builds include Electron and the Python engine; destination computers do not need Node.js or Python installed separately. A packaged macOS build may require a version newer than macOS 13, depending on the Python runtime used to build it.

| Platform | Desktop app | Validation status |
| --- | --- | --- |
| macOS | Electron app, built for the Mac's current architecture | ARM64 packaged installation, three languages, OS language selection and real synchronization with backup and Claude reopening verified locally |
| Windows 10/11 x64 | The same Electron interface; Windows x64 installer | Authenticated synchronization on a native x64 Windows host and the packaged installer remain unverified |
| Windows 11 ARM64 | x64 Node.js, Python and Electron through Windows emulation; packaged installer remains x64 | Source setup, two-account synchronization, verified backup and automatic Claude exit/reopening verified in a VM; packaged installer and ARM64-host packaging remain unverified |
| Linux | The same Electron interface; Debian installer and portable archive for the build computer’s architecture | Source setup, three languages, OS language selection, two-account synchronization, verified backup, repeated sync without catalog writes, native ARM64 package builds and automatic Claude exit/reopening verified in a Debian 13.7 ARM64 VM with LXDE; packaged installation and other Linux distributions or versions remain unverified |

Windows 11 ARM64 uses the system’s built-in [x64 emulation](https://learn.microsoft.com/en-us/windows/arm/apps-on-arm-x86-emulation). Windows 10 ARM64 is unsupported. A native Windows ARM64 app build is not provided.

Run Windows commands in regular Windows PowerShell, outside WSL. WSL, SSH and cloud sessions are excluded. Build the packaged app on its target operating system so it includes the correct Python executable.

## Get the source

Download the project with **Code → Download ZIP** on GitHub and extract it. If you already have [Git](https://git-scm.com/downloads), you can clone it instead:

```sh
git clone https://github.com/ebald/claude-code-user-sync.git
cd claude-code-user-sync
```

Run the commands below from the downloaded or cloned project folder. Install Claude Desktop separately and initialize your local Code conversations before syncing.

On Windows, if Claude asks for Git before a Local conversation, install [Git for Windows](https://git-scm.com/downloads/win), then quit and reopen Claude, or update Claude if you are not using worktrees; see [Claude's Git troubleshooting](https://code.claude.com/docs/en/desktop#git-and-git-lfs-errors). Setup installs neither Claude Desktop nor Git, and the synchronizer does not need Git when downloaded as a ZIP.

## Automatic setup

Packaged apps already include Electron and Python. The setup scripts are for running this project from its source code: they check existing tools, install missing prerequisites, download the project dependencies and open the app. On macOS, `setup.sh` prepares and opens the source app; it does not install a `.app` in Applications. Opening the app does **not** start a synchronization; you choose when to sync in the interface.

| System | Start automatic setup |
| --- | --- |
| macOS | Double-click `setup.command` in Finder, or run `bash ./setup.sh` in Terminal |
| Windows 10/11 x64 or Windows 11 ARM64 | Double-click `setup.bat` in File Explorer, or run `.\setup.bat` in PowerShell |
| Ubuntu / Debian | Run `bash ./setup.sh` in your normal user's terminal |

An internet connection is required for installation. The first launch may finish downloading the Electron runtime, so keep the connection available until the app opens. Compatible installed versions of Node.js, npm and Python are reused. The setup console uses English; the app opens in your system's supported language and offers English, Spanish and Portuguese.

When Node.js is missing or too old, the macOS/Linux script downloads a verified official Node.js distribution into the ignored `.sandbox/setup/` folder and uses it for this app. Missing Python on macOS is installed from an official signed Python package. On Ubuntu/Debian, `apt` installs missing Python, virtual-environment support, Electron runtime libraries and `binutils` for packaging. System package installation requests administrator privileges when needed; the app runs as your normal user.

On Linux where AppArmor restricts Electron launches from source, default setup builds and installs the `.deb` package and opens the installed app instead. Installation may request your administrator password. After installation, open the app directly from your application menu on later launches. This handles the restrictions used by Ubuntu 24.04 and newer; `--check` reports when this packaged route is needed without changing anything.

Windows setup selects x64 Node.js and Python on both supported Windows architectures. On Windows 11 ARM64, these tools and the Electron app run through x64 emulation. Windows setup uses PowerShell and [WinGet](https://learn.microsoft.com/en-us/windows/package-manager/winget/) when available. Otherwise, it verifies official Node.js and Python downloads and installs them for this project under `.sandbox/setup/`; the Python installer uses a per-user installation. Windows may show its normal installer permission prompt. Setup does not change the global PowerShell execution policy. Selected runtime paths apply to the setup and app process.

To check prerequisites without installing, downloading dependencies or opening the app:

```sh
# macOS / Linux
bash ./setup.sh --check
```

```powershell
# Windows
.\setup.bat --check
```

The check exits successfully when the prerequisites are ready, or reports what is missing and exits with status 1. To install missing prerequisites and prepare source dependencies without opening the app:

```sh
# macOS / Linux
bash ./setup.sh --no-launch
```

```powershell
# Windows
.\setup.bat --no-launch
```

On Linux, `--no-launch` also skips building and installing the app package. Add `--help` to either launcher to see the available options. For source launches, run the setup script again whenever you want to open the app. Manual setup and development remain available below.

### Manual setup for developers

If automatic setup used a project-local runtime, open the app later with the setup launcher. The manual `npm` commands below require Node.js and npm on your normal PATH.

Install [Node.js](https://nodejs.org/en/download) 22.12 or newer and [Python](https://www.python.org/downloads/) 3.10 or newer, then install the locked project dependencies. For Windows source launches, choose the x64 versions of both tools, including on Windows 11 ARM64:

```sh
npm ci
```

In Windows PowerShell, use `npm.cmd ci`. The build dependencies and Electron runtime are downloaded during setup; synchronization itself runs locally. Continue with your platform's instructions below.

## macOS instructions

Confirm the prerequisites, then start the Electron app:

```sh
node --version
python3 --version
npm start
```

### Use the app

1. Finish any running work in Claude.
2. The app starts in your operating system’s preferred supported language. Keep **System language** selected to follow that setting, or choose **English**, **Español** or **Português**; a manual choice is saved between launches.
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

To install the packaged Mac app, open the DMG and copy **Claude Code User Sync.app** to **Applications**, then open it from there. The packaged app includes its runtimes and does not need `setup.sh`.

See the [Electron app guide](desktop/README.md) for build details, storage locations and tests.

### Terminal or Finder launcher

Quit Claude completely with **Cmd+Q** and finish any running Claude Code processes, then run:

```sh
python3 claude_sync.py sync --live
```

Alternatively, open `sync.command` from Finder. After synchronization, reopen Claude and sign in to the account you want to use.

`sync --live` synchronizes all detected local profiles and projects. It reports counts, unresolved differences, unavailable histories and asset issues, along with the backup location. It can mirror a catalog entry even when the transcript is missing, but it cannot recreate missing conversation content.

## Windows instructions

Use Windows 10/11 x64 or Windows 11 ARM64. The ARM64 source route runs x64 tools through Windows emulation; see the verification scope below.

1. Install **x64 Node.js** 22.12 or newer and **x64 Python** 3.10 or newer from their official sites, including the Python launcher. Open a new PowerShell window after installation.
2. Download or clone this project, open PowerShell in its folder and run `npm.cmd ci` if you have not already done so.
3. Confirm the prerequisites and start the same Electron app used on macOS:

   ```powershell
   node --version
   py -3 --version
   npm.cmd start
   ```

The app automatically follows your operating system’s language. You can change it in the language selector. Finish active Claude tasks and click **Sync and reopen Claude**. The app requests a normal shutdown, checks that Claude has stopped, synchronizes and tries to reopen Claude. It does not force-kill Claude. Switch accounts manually after Claude reopens. The app can use a selected Claude executable if the installed app is not discovered automatically.

Claude can remain running in the system tray after its window closes. The app requests Claude's normal exit so its tray process can stop too. If automatic shutdown does not finish, complete active work, choose **Quit** or **Exit** from Claude's app menu or system tray menu, then retry synchronization.

To try the interface without changing Claude data:

```powershell
npm.cmd run preview
```

### Build a Windows installer

Run on a Windows x64 computer with x64 Node.js and Python. The packaged installer is x64; a native ARM64 build is not provided, and building on an ARM64 host has not been verified:

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

Use the native Windows paths for the profiles you intend to synchronize. The tool does not copy conversations between computers or between operating system user logins.

Windows asset checks currently support ordinary files on local drives. Network shares, junctions, symbolic links and cloud placeholder reparse points are refused. Make any needed cloud file available as a regular local file before syncing.

## Linux instructions

Use Ubuntu 22.04 or newer or Debian 12 or newer, with an x64 or arm64 desktop session. Install Claude Desktop using Anthropic’s [Linux beta installation guide](https://code.claude.com/docs/en/desktop-linux), then initialize local Code conversations in each account. Run the app as your normal desktop user.

Install Node.js 22.12 or newer, npm and Python 3.10 or newer. For packaging on Ubuntu or Debian, also install `python3-venv` and `binutils` (which provides `objdump`); automatic setup prepares both. From the project folder:

```sh
node --version
python3 --version
npm ci
npm start
```

On Ubuntu 24.04 and newer, AppArmor may block Electron startup from source or from the portable archive. If startup fails with a sandbox error, install the `.deb` package, which includes an AppArmor profile for this app. You can create it with `npm run build:linux` without launching the source app first. See [Ubuntu’s release notes](https://documentation.ubuntu.com/release-notes/24.04/).

The app uses the operating system’s language automatically, with the same language selector as macOS and Windows. Finish active Claude tasks and any Claude Code terminals, then click **Sync and reopen Claude**. For the official Linux installation, the app requests normal shutdown and waits up to 30 seconds before synchronizing. If it cannot safely request shutdown or Claude Code remains active, it asks you to quit Claude completely and try again. It does not force-kill processes. After Claude reopens, switch accounts manually.

To preview the interface without changing Claude data:

```sh
npm run preview
```

### Build Linux packages

Build on a Linux computer using Node.js and Python for that computer’s architecture. Build on the oldest supported distribution you intend to target (Ubuntu 22.04 is the baseline); packages built on a newer system or with a newer Python runtime may require newer Linux libraries.

```sh
sudo apt install python3-venv binutils
npm run build:linux
```

The build bundles the Python synchronization engine and creates a **Debian `.deb` installer** and a **portable `.tar.gz` archive** in `release/`. Open the `.deb` using your distribution’s software installer, or extract the portable archive and run its `claude-code-user-sync` executable as your normal user. Installed packages include Electron, Python, the backend and translations. Use `npm run pack` for an unpacked app directory.

From the project folder, you can also install the `.deb` in a terminal if a software installer is unavailable:

```sh
sudo apt install './release/claude-code-user-sync_1.3.0_arm64.deb'
```

This filename is an example for version 1.3.0 on ARM64. Replace it with the actual `.deb` filename for your version and architecture, then open **Claude Code User Sync** from the applications menu.

### Linux terminal and data locations

Quit Claude Desktop completely and finish active Claude Code terminals, then run:

```sh
python3 claude_sync.py sync --live
```

Reopen Claude Desktop from your application launcher, or run `claude-desktop`, then switch accounts. The standard catalog is `${XDG_CONFIG_HOME:-~/.config}/Claude/claude-code-sessions`; conversation transcripts are under `~/.claude/projects`. The app respects an absolute `XDG_CONFIG_HOME` or `XDG_DATA_HOME` when configured.

If the Claude data folder differs, select it in app settings, or use global CLI overrides before the command:

```sh
python3 claude_sync.py --app-data "/path/to/Claude" --projects-dir "/path/to/.claude/projects" sync --live
```

Source setup, language selection, authenticated synchronization between two accounts, a repeated sync without catalog writes and native ARM64 package builds have been verified on Debian 13.7 ARM64 with LXDE. Authenticated synchronization on other Linux distributions or versions, native packaged installation and the Ubuntu AppArmor setup route remain unverified.

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

The Windows app stores backups under `%LOCALAPPDATA%\Claude Code User Sync\Backups\`; Linux uses `${XDG_DATA_HOME:-~/.local/share}/Claude Code User Sync/Backups/`. The internal macOS storage name is retained for compatibility with earlier versions. The Electron app keeps its own preferences in its standard user-data directory; see the [app guide](desktop/README.md#storage) for details. Each operation includes a catalog snapshot, the original files needed for undo and an asset manifest. Available linked files are preserved under that operation's `asset-snapshot/` directory. On macOS and Linux, backup directories and files use owner-only permissions. Windows backups inherit the access permissions of their parent directory, so store them inside your own user profile rather than a shared folder.

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

For Linux’s standard data location, quit Claude and run:

```sh
python3 claude_sync.py undo \
  --root "${XDG_CONFIG_HOME:-$HOME/.config}/Claude/claude-code-sessions" \
  --backup .sandbox/sync-OPERATION_ID/backup \
  --live
```

Use the actual operation ID and the full backup path if the operation was run from the app.

## Try it on a local copy

You can inspect and apply a plan to a private copy before changing the live catalogs. Use a new destination directory for each copy; keep Claude idle or closed while copying.

The following examples use macOS/Linux shell syntax. A Windows PowerShell example is included below.

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

On Windows, use `py -3 -m unittest discover` for the Python suite. All nine [GitHub Actions jobs](https://github.com/ebald/claude-code-user-sync/actions/runs/37709530312) in the public repository passed for commit `697bd1a`: Python 3.10/3.14 tests, Electron workflow and translation tests, bundled-backend checks and packaged-app smoke checks on macOS, Windows and Linux. Linux installer and portable archive builds also passed.

The desktop app uses **i18next** with English, Spanish and Brazilian Portuguese JSON dictionaries in `desktop/locales/`. One interface and the same translation keys serve macOS, Windows and Linux. Tests check language coverage and interpolation placeholders. The default **System language** setting uses the operating system’s preferred supported language. English and Spanish regional variants use their matching translations; all Portuguese variants use Brazilian Portuguese. If none of the preferred languages is supported, the app uses English. A manual language choice persists between launches; select **System language** to return to automatic selection.

The suites use synthetic catalogs and transcripts. They cover multiple accounts, new profiles, repeated syncs, conflict handling, deletion markers, artifact recovery, file checks, stale plans, undo and the desktop workflow. See the [app guide](desktop/README.md#tests-and-preview) for preview and packaging commands.

On a Mac with Apple silicon, the local Electron 1.3.0 ARM64 build was installed from its DMG into Applications. Checks of the installed app passed for English, Spanish, Portuguese and automatic OS language selection. A real synchronization initiated by the user completed, created its backup and reopened Claude. This verifies that local workflow; other Claude Desktop versions can change its internal catalog format.

The default `setup.sh` launch passed using existing runtimes in a ZIP downloaded from the public GitHub repository without credentials; the real app opened in the OS language without starting synchronization. In a fresh source copy with spaces in its folder name and Node.js made unavailable to setup, the script downloaded and verified official Node.js 22.23.3, reused the installed Python and opened the app. The official Python package's download, SHA-256 and installer signature were verified separately; administrator installation on a Mac without Python has not yet been tested.

In a Windows 11 ARM64 virtual machine, `setup.bat --check` correctly reported missing prerequisites, `--no-launch` installed verified official x64 Node.js and Python plus npm dependencies as a normal user, and a final `--check` passed. The JavaScript and Python automated checks completed without failures. An Electron preview smoke check passed and exited normally after checking all three languages, automatic English selection from the OS, the actual local account count, the localized success status and renderer isolation.

A default `.\setup.bat` run also reused the runtimes, installed locked dependencies and opened the real app. It detected initialized local profiles, started in the OS language (English), and switched to Portuguese and back to **System language** (English). Closing its window normally returned exit status 0. Those installation and language checks did not initiate synchronization.

A separate Windows 11 ARM64 check used a ZIP downloaded directly from the public repository without credentials, extracted to a folder with spaces. `setup.bat --check` reported missing Node.js/npm and an available Python 3.14.8 x64; the default `setup.bat` run downloaded and verified Node.js 22.23.3 x64, installed the locked npm dependencies and opened the real app in the OS language (English). The final `--check` passed, and the source preview smoke check passed for all three languages, automatic OS language selection, the localized success status and renderer isolation. No synchronization was started during that installation check; the default setup's exit status was not recorded.

In the same Windows 11 ARM64 VM, the source app synchronized one harmless local Code conversation between two initialized signed-in accounts with official Claude Desktop MSIX 2.26454.0.0. It quit Claude normally and reopened it automatically. Both profile catalogs contained the conversation afterward; the backup snapshot and written catalog passed hash checks, no transcripts were missing, and a subsequent plan had no pending changes. Repeating synchronization wrote no catalog files and created no duplicates. The Windows packaged installer and packaging on an ARM64 host remain unverified.

In a freshly installed Debian 13.7 ARM64 VM with LXDE, a public GitHub ZIP at commit `641bac4` was downloaded without credentials and extracted to a folder with spaces. `bash ./setup.sh --check` reported missing Node.js/npm, Python virtual-environment support and curl without changing the source. The default `bash ./setup.sh` installed the prerequisites, downloaded and verified official Node.js 22.23.3 ARM64 and opened the source app with Python 3.13.5 and Electron 44.5.1. Normal app closure and the final prerequisite check both returned exit status 0. The real interface selected English from the OS locale `en_US` and switched to Portuguese and Spanish. The manual Spanish choice persisted across a VM reboot.

A second public ZIP at commit `697bd1a` was downloaded without credentials. The updated default setup installed `binutils`, verified official Node.js 22.23.3 ARM64 and opened the source app as the normal desktop user. Normal app closure and the final prerequisite check returned exit status 0.

Linux JavaScript checks had 57 passes and one expected skip; the updated Python suite ran 204 tests with six expected skips and no failures. The source preview smoke check passed for all three languages and automatic OS language selection.

In the same Debian VM, the source app synchronized one native local Code conversation between two initialized signed-in accounts with official Claude Desktop 2.26454.2 ARM64. Starting synchronization from the app while Claude was running closed Claude normally and reopened it automatically with login retained. Both profile catalogs contained the single conversation afterward; the backup snapshot and written catalog passed hash checks, no transcripts were missing, no conflicts remained and a subsequent plan had no pending changes. The check found no unexpected changes to native conversation histories or files and no writes outside the allowed synchronization scope.

A repeated real synchronization using the corrected public source, with Claude running, also closed Claude normally and reopened it with login retained. It wrote no catalog files, both profile backup snapshots passed hash checks and no duplicate conversations, missing transcripts, conflicts, pending changes or unexpected native file changes were found.

A native ARM64 build produced the version 1.3.0 Debian installer and portable archive successfully. Native packaged installation, authenticated synchronization on other Linux distributions or versions and the Ubuntu AppArmor setup route remain unverified.

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
