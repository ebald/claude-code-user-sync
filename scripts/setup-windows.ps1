# Windows PowerShell 5.1 or newer. Dot-source this file to test its helpers.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:SetupRoot = Split-Path -Parent $PSScriptRoot
$script:NodeVersion = '22.23.3'
$script:NodeZipHash = '2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71'
$script:PythonVersion = '3.14.8'
$script:PythonInstallerHash = '759be887b96e736a3ca886daf8d575f18fcae1a09efab6902f42d59e8999f8ef'

function Show-SetupHelp {
    Write-Host @'
Claude Code User Sync - automatic source setup (Windows 10/11, x64)

Usage: setup.bat [--check | --no-launch | --help]

  --check       Check prerequisites only. Never downloads, installs or opens apps.
  --no-launch   Install missing prerequisites and project dependencies, then stop.
  --help        Show this help.

By default, setup prepares the project and opens the Electron app. It never
synchronizes chats. Compatible Node.js (22.12.0+) and Python (3.10+) are reused.
Missing runtimes are installed with WinGet when available. Otherwise, verified
official runtimes are installed under this project's ignored .sandbox/setup.
Installer elevation is requested by Windows only when needed. No permanent
execution-policy changes are made. Fallback runtimes do not change global PATH.

CLAUDE_SYNC_PYTHON may select a specific x64 Python executable (without arguments).
Install Claude Desktop and sign in separately: https://claude.com/download
'@
}

function Assert-WindowsHost {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or [Environment]::OSVersion.Version.Major -lt 10) {
        throw 'Run setup.bat on Windows 10 or Windows 11. Use setup.sh on macOS or Linux.'
    }
    $architecture = [Environment]::GetEnvironmentVariable('PROCESSOR_ARCHITEW6432')
    if (-not $architecture) { $architecture = [Environment]::GetEnvironmentVariable('PROCESSOR_ARCHITECTURE') }
    if ($architecture -ne 'AMD64') { throw 'The Windows app currently requires native x64 Windows and x64 runtimes.' }
}

function Get-InstalledCommandPaths([string]$Name) {
    @(Get-Command -Name $Name -CommandType Application -All -ErrorAction SilentlyContinue) |
        ForEach-Object { $_.Source } | Select-Object -Unique
}

function Invoke-NativeCapture([string]$Executable, [string[]]$Arguments) {
    try {
        $global:LASTEXITCODE = 0
        $output = & $Executable @Arguments 2>$null
        return [pscustomobject]@{ Code = $LASTEXITCODE; Output = ($output -join "`n") }
    } catch { return [pscustomobject]@{ Code = 1; Output = '' } }
}

function Invoke-NativeCommand([string]$Executable, [string[]]$Arguments) {
    $global:LASTEXITCODE = 0
    & $Executable @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw ('{0} failed (exit {1}).' -f (Split-Path -Leaf $Executable), $LASTEXITCODE) }
}

function Test-RuntimePath([string]$Path) {
    # Microsoft Store aliases can open the Store or install a runtime during a check.
    return $Path -and $Path -notmatch '(?i)[\\/]WindowsApps[\\/]' -and (Test-Path -LiteralPath $Path -PathType Leaf)
}

function Find-NodeRuntime {
    # Prefer the complete project-local runtime after an automatic npm repair.
    $candidates = @(Join-Path $script:SetupRoot ('.sandbox/setup/node-v{0}-win-x64/node.exe' -f $script:NodeVersion))
    $candidates += @(Get-InstalledCommandPaths 'node.exe')
    if ($env:ProgramFiles) { $candidates += Join-Path $env:ProgramFiles 'nodejs/node.exe' }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Test-RuntimePath $candidate)) { continue }
        $result = Invoke-NativeCapture $candidate @('-p', 'JSON.stringify({version:process.versions.node,arch:process.arch,platform:process.platform})')
        if ($result.Code -ne 0) { continue }
        try {
            $info = $result.Output | ConvertFrom-Json
            if ([Version]$info.version -ge [Version]'22.12.0' -and $info.arch -eq 'x64' -and $info.platform -eq 'win32') {
                # Keep the original Unicode path; Windows PowerShell 5.1 can
                # decode native UTF-8 paths using the console's legacy code page.
                return [pscustomobject]@{ Executable = [string]$candidate; Version = [string]$info.version }
            }
        } catch { continue }
    }
    return $null
}

function Get-PythonCandidatePaths {
    Get-InstalledCommandPaths 'python.exe'
    Get-InstalledCommandPaths 'python3.exe'
    Join-Path $script:SetupRoot ('.sandbox/setup/python-{0}-x64/python.exe' -f $script:PythonVersion)
    # Listing an existing launcher's paths does not request/install an interpreter.
    foreach ($launcher in @(Get-InstalledCommandPaths 'py.exe')) {
        if (-not (Test-RuntimePath $launcher)) { continue }
        $listing = Invoke-NativeCapture $launcher @('--list-paths')
        if ($listing.Code -ne 0) { continue }
        foreach ($line in ($listing.Output -split "`n")) {
            if ($line -match '(?i)([a-z]:[\\/].*[\\/]python\.exe)\s*$') { $Matches[1].Trim() }
        }
    }
    foreach ($base in @($env:LOCALAPPDATA, $env:ProgramFiles)) {
        if (-not $base) { continue }
        $directory = if ($base -eq $env:LOCALAPPDATA) { Join-Path $base 'Programs/Python' } else { $base }
        if (Test-Path -LiteralPath $directory -PathType Container) {
            Get-ChildItem -LiteralPath $directory -Directory -Filter 'Python*' -ErrorAction SilentlyContinue |
                ForEach-Object { Join-Path $_.FullName 'python.exe' }
        }
    }
    if ($env:LOCALAPPDATA) {
        $managed = Join-Path $env:LOCALAPPDATA 'Python'
        if (Test-Path -LiteralPath $managed -PathType Container) {
            Get-ChildItem -LiteralPath $managed -Directory -Filter 'pythoncore-*' -ErrorAction SilentlyContinue |
                ForEach-Object { Join-Path $_.FullName 'python.exe' }
        }
    }
    # Per-user official installers do not have to add their interpreter to PATH.
    foreach ($registryRoot in @('HKCU:\Software\Python\PythonCore', 'HKLM:\Software\Python\PythonCore')) {
        if (-not (Test-Path -LiteralPath $registryRoot)) { continue }
        foreach ($key in @(Get-ChildItem -LiteralPath $registryRoot -ErrorAction SilentlyContinue)) {
            $installPath = Join-Path $key.PSPath 'InstallPath'
            if (Test-Path -LiteralPath $installPath) {
                $property = Get-ItemProperty -LiteralPath $installPath -ErrorAction SilentlyContinue
                if ($property -and $property.PSObject.Properties['ExecutablePath']) { $property.ExecutablePath }
            }
        }
    }
}

function Find-PythonRuntime {
    $override = $env:CLAUDE_SYNC_PYTHON
    $candidates = if ($override) {
        if (Test-RuntimePath $override) { @($override) } else { @(Get-InstalledCommandPaths $override) }
    } else { @(Get-PythonCandidatePaths) }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Test-RuntimePath $candidate)) { continue }
        # Single quotes inside Python avoid Windows PowerShell 5.1 native-argument
        # quoting removing embedded double quotes from the -c argument.
        $code = "import json,platform,struct,sys,venv,ensurepip; print(json.dumps({'version':list(sys.version_info[:3]),'bits':struct.calcsize('P')*8,'machine':platform.machine(),'executable':sys.executable,'platform':sys.platform}))"
        $result = Invoke-NativeCapture $candidate @('-B', '-c', $code)
        if ($result.Code -ne 0) { continue }
        try {
            $info = $result.Output | ConvertFrom-Json
            $version = $info.version -join '.'
            if ([Version]$version -ge [Version]'3.10.0' -and $info.bits -eq 64 -and $info.machine -match '^(?i:AMD64|x86_64)$' -and $info.platform -eq 'win32') {
                return [pscustomobject]@{ Executable = [string]$info.executable; Version = $version }
            }
        } catch { continue }
    }
    if ($override) { throw 'CLAUDE_SYNC_PYTHON must select an existing x64 Python 3.10+ executable with venv and ensurepip. Remove the override to let setup choose/install Python.' }
    return $null
}

function Refresh-SetupPath {
    $entries = @([Environment]::GetEnvironmentVariable('Path', 'Machine'), [Environment]::GetEnvironmentVariable('Path', 'User'), $env:Path)
    $env:Path = (($entries -join ';') -split ';' | Where-Object { $_ } | Select-Object -Unique) -join ';'
}

function Use-NodeRuntime($Node) { $env:Path = (Split-Path -Parent $Node.Executable) + ';' + $env:Path }

function Find-NpmCommand($Node) {
    $npm = Join-Path (Split-Path -Parent $Node.Executable) 'npm.cmd'
    if (Test-RuntimePath $npm) {
        $result = Invoke-NativeCapture $npm @('--version')
        if ($result.Code -eq 0 -and $result.Output.Trim() -match '^\d+\.\d+\.\d+(?:-[\w.-]+)?$') { return $npm }
    }
    return $null
}

function Assert-SourceTree {
    foreach ($file in @('package.json', 'package-lock.json')) {
        if (-not (Test-Path -LiteralPath (Join-Path $script:SetupRoot $file) -PathType Leaf)) {
            throw ('{0} is missing. Download or clone the complete repository before running setup.' -f $file)
        }
    }
}

function Save-OfficialDownload([string]$Url, [string]$Destination) {
    # TLS and installer verification remain enabled. The setting is process-local.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $partial = $Destination + '.partial'
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $partial
        Move-Item -LiteralPath $partial -Destination $Destination -Force
    } finally { if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force } }
}

function Assert-FileHash([string]$Path, [string]$Expected) {
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $Expected) {
        throw 'The official download failed its SHA-256 check. It has not been executed. Remove .sandbox/setup/downloads and retry.'
    }
}

function Get-DownloadDirectory {
    $directory = Join-Path $script:SetupRoot '.sandbox/setup/downloads'
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    return $directory
}

function Install-PortableNode {
    $directory = Get-DownloadDirectory
    $name = 'node-v{0}-win-x64.zip' -f $script:NodeVersion
    $archive = Join-Path $directory $name
    $sums = Join-Path $directory ('node-{0}-SHASUMS256.txt' -f $script:NodeVersion)
    Write-Host ('Downloading verified Node.js {0} from nodejs.org...' -f $script:NodeVersion)
    Save-OfficialDownload ('https://nodejs.org/dist/v{0}/SHASUMS256.txt' -f $script:NodeVersion) $sums
    $pattern = '^(?<hash>[a-fA-F0-9]{64})\s+\*?' + [regex]::Escape($name) + '$'
    $expected = @((Get-Content -LiteralPath $sums) | Where-Object { $_ -match $pattern } | ForEach-Object { ([regex]::Match($_, $pattern)).Groups['hash'].Value })
    if ($expected.Count -ne 1 -or $expected[0] -ne $script:NodeZipHash) { throw 'The official Node.js checksum list did not match the pinned release. No runtime was installed.' }
    Save-OfficialDownload ('https://nodejs.org/dist/v{0}/{1}' -f $script:NodeVersion, $name) $archive
    Assert-FileHash $archive $expected[0]
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $script:SetupRoot '.sandbox/setup') -Force
}

function Assert-PythonSignature([string]$Path) {
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or $signature.SignerCertificate.Subject -notmatch '(^|,\s*)CN=Python Software Foundation(,|$)') {
        throw 'The Python installer does not have a valid Python Software Foundation signature. It has not been executed.'
    }
}

function Invoke-PythonInstaller([string]$Installer, [string]$Target) {
    $arguments = @('/quiet', '/norestart', 'InstallAllUsers=0', ('TargetDir="{0}"' -f $Target), 'PrependPath=0', 'AppendPath=0', 'Include_launcher=0', 'InstallLauncherAllUsers=0', 'AssociateFiles=0', 'Shortcuts=0', 'Include_test=0', 'Include_doc=0', 'Include_pip=1')
    $installerProcess = Start-Process -FilePath $Installer -ArgumentList $arguments -Wait -PassThru
    if ($installerProcess.ExitCode -notin @(0, 3010)) { throw ('The per-user Python installation failed (exit {0}). Install x64 Python manually from https://www.python.org/downloads/windows/ and rerun setup.' -f $installerProcess.ExitCode) }
    if ($installerProcess.ExitCode -eq 3010) { Write-Host 'Windows reports that a restart may be needed after installation.' }
}

function Install-UserPython {
    $directory = Get-DownloadDirectory
    $name = 'python-{0}-amd64.exe' -f $script:PythonVersion
    $installer = Join-Path $directory $name
    Write-Host ('Downloading verified Python {0} from python.org...' -f $script:PythonVersion)
    Save-OfficialDownload ('https://www.python.org/ftp/python/{0}/{1}' -f $script:PythonVersion, $name) $installer
    Assert-FileHash $installer $script:PythonInstallerHash
    Assert-PythonSignature $installer
    Invoke-PythonInstaller $installer (Join-Path $script:SetupRoot ('.sandbox/setup/python-{0}-x64' -f $script:PythonVersion))
}

function Install-Prerequisite([string]$Name, [string]$PackageId) {
    $winget = @(Get-InstalledCommandPaths 'winget.exe') | Select-Object -First 1
    if ($winget) {
        Write-Host ('Installing {0} with Windows Package Manager. Windows may request installer permissions...' -f $Name)
        Invoke-NativeCommand $winget @('install', '--id', $PackageId, '--exact', '--source', 'winget', '--architecture', 'x64', '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity')
    } elseif ($Name -eq 'Node.js') { Install-PortableNode }
    elseif ($Name -eq 'Python') { Install-UserPython }
    else { throw ('Unknown prerequisite: {0}' -f $Name) }
    Refresh-SetupPath
}

function Invoke-ProjectNpm([string]$Npm, [string[]]$Arguments) {
    Push-Location -LiteralPath $script:SetupRoot
    try { Invoke-NativeCommand $Npm $Arguments } finally { Pop-Location }
}

function Invoke-Setup([string[]]$SetupArguments) {
    $check = $false
    $noLaunch = $false
    foreach ($argument in $SetupArguments) {
        switch ($argument) {
            '--check' { $check = $true }
            '--no-launch' { $noLaunch = $true }
            '--help' { Show-SetupHelp; return 0 }
            '-h' { Show-SetupHelp; return 0 }
            default { Write-Host ('Unknown option: {0}. Use setup.bat --help.' -f $argument); return 2 }
        }
    }
    try {
        Assert-WindowsHost
        Assert-SourceTree
        Write-Host 'Checking source prerequisites for Claude Code User Sync...'
        $node = Find-NodeRuntime
        $python = Find-PythonRuntime
        if ($node) { Write-Host ('Node.js {0} (x64): ready' -f $node.Version) } else { Write-Host 'Node.js 22.12.0+ (x64): missing or incompatible' }
        if ($python) { Write-Host ('Python {0} (x64): ready' -f $python.Version) } else { Write-Host 'Python 3.10+ (x64): missing or incompatible' }
        $npm = if ($node) { Find-NpmCommand $node } else { $null }
        if ($npm) { Write-Host 'npm: ready' } else { Write-Host 'npm: missing' }
        if ($check) {
            if ($node -and $python -and $npm) { Write-Host 'All prerequisites are ready. No changes were made.'; return 0 }
            Write-Host 'Run setup.bat to install missing prerequisites, or follow the manual developer instructions in README.md.'
            return 1
        }
        if (-not $node) { Install-Prerequisite 'Node.js' 'OpenJS.NodeJS.LTS'; $node = Find-NodeRuntime }
        if (-not $python) { Install-Prerequisite 'Python' 'Python.Python.3.14'; $python = Find-PythonRuntime }
        if (-not $node) { throw 'A compatible x64 Node.js runtime was not found after installation. Reopen the terminal and rerun setup, or install Node.js from https://nodejs.org/en/download.' }
        if (-not $python) { throw 'A compatible x64 Python runtime was not found after installation. Reopen the terminal and rerun setup, or install Python from https://www.python.org/downloads/windows/.' }
        $npm = Find-NpmCommand $node
        if (-not $npm) {
            Write-Host 'Preparing a complete project-local Node.js runtime with npm...'
            Install-PortableNode
            Refresh-SetupPath
            $node = Find-NodeRuntime
            if (-not $node) { throw 'The verified project-local Node.js runtime could not be started.' }
            $npm = Find-NpmCommand $node
        }
        if (-not $npm) { throw 'The verified Node.js runtime does not have a usable npm.cmd. Remove .sandbox/setup/node-v22.23.3-win-x64 and rerun setup.' }
        Use-NodeRuntime $node
        $env:CLAUDE_SYNC_PYTHON = $python.Executable
        Write-Host 'Installing the locked project dependencies...'
        Invoke-ProjectNpm $npm @('ci', '--include=dev')
        if ($noLaunch) { Write-Host 'Setup complete. The app was not opened. Run setup.bat when you want to open it.'; return 0 }
        Write-Host 'Opening Claude Code User Sync. Synchronization starts only when you choose it in the app.'
        Invoke-ProjectNpm $npm @('start')
        return 0
    } catch { Write-Host ('Setup could not finish: {0}' -f $_.Exception.Message); return 1 }
}

if ($MyInvocation.InvocationName -ne '.') { exit (Invoke-Setup -SetupArguments $args) }
