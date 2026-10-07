Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'setup-windows.ps1')

function Assert-Equal($Actual, $Expected, [string]$Message) {
    if ($Actual -ne $Expected) { throw ('{0}: expected {1}, received {2}' -f $Message, $Expected, $Actual) }
}
function Assert-Throws([scriptblock]$Action, [string]$Pattern) {
    try { & $Action } catch { if ($_.Exception.Message -match $Pattern) { return }; throw }
    throw ('Expected an error matching: {0}' -f $Pattern)
}

$originalNodeFinder = ${function:Find-NodeRuntime}
$originalHostInfo = ${function:Get-WindowsHostInfo}
$originalPythonFinder = ${function:Find-PythonRuntime}
$originalInstall = ${function:Install-Prerequisite}
$originalPortableNode = ${function:Install-PortableNode}
$originalUserPython = ${function:Install-UserPython}
$originalHash = ${function:Assert-FileHash}
$originalSignature = ${function:Assert-PythonSignature}
$originalPythonInstaller = ${function:Invoke-PythonInstaller}
$originalPathTest = ${function:Test-RuntimePath}
$originalCommands = ${function:Get-InstalledCommandPaths}
$originalCapture = ${function:Invoke-NativeCapture}
$originalPythonCandidates = ${function:Get-PythonCandidatePaths}
$previousOverride = $env:CLAUDE_SYNC_PYTHON
$previousPath = $env:Path
$previousProgressPreference = $ProgressPreference
try {
    $env:CLAUDE_SYNC_PYTHON = ''
    # Only Windows 11 ARM64 has the x64 emulation needed by our verified runtimes.
    function Get-WindowsHostInfo { return $script:testHost }
    $script:testHost = [pscustomobject]@{ Platform = [PlatformID]::Win32NT; Version = [Version]'10.0.19045'; Architecture = 'AMD64' }
    Assert-WindowsHost
    $script:testHost.Version = [Version]'10.0.26100'
    Assert-WindowsHost
    $script:testHost.Architecture = 'ARM64'
    $script:testHost.Version = [Version]'10.0.22000'
    $emulationMessages = @(Assert-WindowsHost 6>&1)
    Assert-Equal ($emulationMessages -join '') 'Windows ARM64: using built-in x64 emulation for the app and runtimes.' 'Windows 11 ARM64 reports the emulated x64 runtime choice'
    $script:testHost.Version = [Version]'10.0.21999'
    Assert-Throws { Assert-WindowsHost } 'Windows 11 or newer is required on ARM64'
    $script:testHost.Version = [Version]'10.0.26100'
    $script:testHost.Architecture = 'x86'
    Assert-Throws { Assert-WindowsHost } 'Use x64 Windows'
    $script:testHost.Architecture = ''
    Assert-Throws { Assert-WindowsHost } 'Use x64 Windows'
    $script:testHost.Architecture = 'AMD64'
    $script:testHost.Version = [Version]'6.3.9600'
    Assert-Throws { Assert-WindowsHost } 'Run setup.bat on Windows 10 or Windows 11'
    $script:testHost.Platform = [PlatformID]::Unix
    $script:testHost.Version = [Version]'10.0.26100'
    Assert-Throws { Assert-WindowsHost } 'Run setup.bat on Windows 10 or Windows 11'
    ${function:Get-WindowsHostInfo} = $originalHostInfo

    # Main-flow tests use functions in memory; no external process or install runs.
    function Assert-WindowsHost { $script:hostChecks++ }
    function Find-NodeRuntime { return $script:testNode }
    function Find-PythonRuntime { return $script:testPython }
    function Find-NpmCommand($Node) { return $script:testNpm }
    function Use-NodeRuntime($Node) { $script:calls += 'use-node' }
    function Install-Prerequisite([string]$Name, [string]$PackageId) {
        $script:calls += 'install:' + $PackageId
        if ($Name -eq 'Node.js') { $script:testNode = [pscustomobject]@{ Executable = 'C:\Node Runtime\node.exe'; Version = '22.23.3' }; $script:testNpm = 'C:\Node Runtime\npm.cmd' }
        if ($Name -eq 'Python') { $script:testPython = [pscustomobject]@{ Executable = 'C:\Python Runtime\python.exe'; Version = '3.14.8' } }
    }
    function Invoke-ProjectNpm([string]$Npm, [string[]]$Arguments) { $script:calls += 'npm:' + ($Arguments -join ' ') }
    function Install-PortableNode {
        $script:calls += 'repair-node-with-npm'
        $script:testNode = [pscustomobject]@{ Executable = 'C:\Private Node Runtime\node.exe'; Version = '22.23.3' }
        $script:testNpm = 'C:\Private Node Runtime\npm.cmd'
    }
    function Refresh-SetupPath { $script:calls += 'refresh-path' }
    $script:hostChecks = 0
    $script:calls = @()
    Assert-Equal (Invoke-Setup @('--bad-option')) 2 'Unknown options fail before changing anything'
    Assert-Equal $script:hostChecks 0 'Invalid arguments never inspect/install the host'
    Assert-Equal (Invoke-Setup @('--help')) 0 'Help is available on every host'
    Assert-Equal $script:hostChecks 0 'Help never inspects/installs the host'

    $script:testNode = [pscustomobject]@{ Executable = 'C:\Node Runtime\node.exe'; Version = '22.23.3' }
    $script:testPython = [pscustomobject]@{ Executable = 'C:\Python Runtime\python.exe'; Version = '3.14.8' }
    $script:testNpm = 'C:\Node Runtime\npm.cmd'
    Assert-Equal (Invoke-Setup @('--check')) 0 'Compatible check succeeds'
    Assert-Equal $script:calls.Count 0 'Check never changes PATH, installs dependencies or opens the app'
    Assert-Equal ([string]$env:CLAUDE_SYNC_PYTHON) '' 'Check never changes Python selection'
    $script:testNode = $null
    $script:testPython = $null
    $script:testNpm = $null
    Assert-Equal (Invoke-Setup @('--check', '--no-launch')) 1 'Check with missing runtimes fails, even with no-launch'
    Assert-Equal $script:calls.Count 0 'Missing-runtimes check never installs anything'

    $previousRoot = $script:SetupRoot
    try {
        $script:SetupRoot = Join-Path $script:SetupRoot 'missing-source-tree'
        Assert-Equal (Invoke-Setup @('--no-launch')) 1 'Incomplete sources fail before any installation'
        Assert-Equal $script:calls.Count 0 'Incomplete sources never install runtimes or dependencies'
    } finally { $script:SetupRoot = $previousRoot }

    Assert-Equal (Invoke-Setup @('--no-launch')) 0 'Automatic preparation succeeds'
    Assert-Equal ($script:calls -join '|') 'install:OpenJS.NodeJS.LTS|install:Python.Python.3.14|use-node|npm:ci --include=dev' 'Preparation installs exact prerequisites and locked development dependencies only'
    Assert-Equal $env:CLAUDE_SYNC_PYTHON 'C:\Python Runtime\python.exe' 'Selected Python is passed to the app/build process'
    $script:calls = @()
    Assert-Equal (Invoke-Setup @()) 0 'Default opens the app'
    Assert-Equal ($script:calls -join '|') 'use-node|npm:ci --include=dev|npm:start' 'Compatible runtimes are reused and only npm start launches'
    $script:calls = @()
    $script:testNpm = $null
    Assert-Equal (Invoke-Setup @('--no-launch')) 0 'Missing npm is repaired automatically'
    Assert-Equal ($script:calls -join '|') 'repair-node-with-npm|refresh-path|use-node|npm:ci --include=dev' 'Missing npm chooses verified complete private Node and prepares without launching'

    # Exercise real discovery with mocked capture. Store aliases must never run.
    ${function:Find-NodeRuntime} = $originalNodeFinder
    ${function:Find-PythonRuntime} = $originalPythonFinder
    $script:captured = @()
    function Test-RuntimePath([string]$Path) { return $Path -and $Path -match '[\\/]' -and $Path -notmatch '(?i)[\\/]WindowsApps[\\/]' -and ($script:privateNodeReady -or $Path -notmatch 'node-v22\.23\.3-win-x64') }
    function Get-InstalledCommandPaths([string]$Name) {
        if ($Name -eq 'node.exe') { @('C:\Users\Example\WindowsApps\node.exe', 'C:\Old\node.exe', 'C:\ARM\node.exe', 'C:\Node Runtime\node.exe') }
        if ($Name -eq 'custom-python.exe') { 'C:\Python Runtime\python.exe' }
    }
    function Get-PythonCandidatePaths { @('C:\Users\Example\WindowsApps\python.exe', 'C:\Old\python.exe', 'C:\ARM\python.exe', 'C:\32Bit\python.exe', 'C:\Python Runtime\python.exe') }
    function Invoke-NativeCapture([string]$Executable, [string[]]$Arguments) {
        $script:captured += $Executable
        if ($Executable -match 'node\.exe$') {
            $version = if ($Executable -match '\\Old\\') { '22.11.0' } else { '22.23.3' }
            $arch = if ($Executable -match '\\ARM\\') { 'arm64' } else { 'x64' }
            return [pscustomobject]@{ Code = 0; Output = (@{ version = $version; arch = $arch; platform = 'win32'; executable = $Executable } | ConvertTo-Json -Compress) }
        }
        Assert-Equal $Arguments[0] '-B' 'Python discovery disables bytecode writes during read-only checks'
        $version = if ($Executable -match '\\Old\\') { @(3, 9, 9) } else { @(3, 14, 8) }
        $architecture = if ($Executable -match '\\ARM\\') { 'win-arm64' } elseif ($Executable -match '\\32Bit\\') { 'win32' } else { 'win-amd64' }
        $bits = if ($Executable -match '\\32Bit\\') { 32 } else { 64 }
        # Even an x64 interpreter can report the native ARM64 host via machine().
        return [pscustomobject]@{ Code = 0; Output = (@{ version = $version; bits = $bits; architecture = $architecture; machine = 'ARM64'; platform = 'win32'; executable = $Executable } | ConvertTo-Json -Compress) }
    }
    $env:CLAUDE_SYNC_PYTHON = ''
    $script:privateNodeReady = $false
    Assert-Equal (Find-NodeRuntime).Executable 'C:\Node Runtime\node.exe' 'Discovery skips old/wrong-architecture Node'
    $script:privateNodeReady = $true
    Assert-Equal (Find-NodeRuntime).Executable (Join-Path $script:SetupRoot '.sandbox/setup/node-v22.23.3-win-x64/node.exe') 'Private runtime takes precedence on later setup runs'
    Assert-Equal (Find-PythonRuntime).Executable 'C:\Python Runtime\python.exe' 'Discovery selects an x64 interpreter on ARM64 and skips old/native ARM64/32-bit Python'
    Assert-Equal (@($script:captured | Where-Object { $_ -match 'WindowsApps' }).Count) 0 'Store aliases are never invoked'
    $env:CLAUDE_SYNC_PYTHON = 'C:\Old\python.exe'
    Assert-Throws { Find-PythonRuntime } 'CLAUDE_SYNC_PYTHON'
    $env:CLAUDE_SYNC_PYTHON = 'custom-python.exe'
    Assert-Equal (Find-PythonRuntime).Executable 'C:\Python Runtime\python.exe' 'Explicit command override resolves to its executable'

    # Install selection keeps native WinGet verification on; no download occurs here.
    ${function:Install-Prerequisite} = $originalInstall
    $script:wingetPresent = $true
    $script:installCalls = @()
    function Get-InstalledCommandPaths([string]$Name) { if ($Name -eq 'winget.exe' -and $script:wingetPresent) { 'C:\WindowsApps\winget.exe' } }
    function Invoke-NativeCommand([string]$Executable, [string[]]$Arguments) { $script:installCalls += ($Arguments -join ' ') }
    function Refresh-SetupPath { $script:installCalls += 'refresh-path' }
    function Install-PortableNode { $script:installCalls += 'verified-node-fallback' }
    function Install-UserPython { $script:installCalls += 'signed-python-fallback' }
    Install-Prerequisite 'Node.js' 'OpenJS.NodeJS.LTS'
    Assert-Equal $script:installCalls[0] 'install --id OpenJS.NodeJS.LTS --exact --source winget --architecture x64 --accept-package-agreements --accept-source-agreements --disable-interactivity' 'WinGet uses exact official IDs and native verification'
    $script:wingetPresent = $false
    Install-Prerequisite 'Node.js' 'OpenJS.NodeJS.LTS'
    Install-Prerequisite 'Python' 'Python.Python.3.14'
    Assert-Equal ($script:installCalls -join '|') 'install --id OpenJS.NodeJS.LTS --exact --source winget --architecture x64 --accept-package-agreements --accept-source-agreements --disable-interactivity|refresh-path|verified-node-fallback|refresh-path|signed-python-fallback|refresh-path' 'Missing WinGet chooses verified official fallbacks'

    # Suppress download progress without changing the caller or cleanup policy.
    $downloadTestDirectory = Join-Path ([IO.Path]::GetTempPath()) ('claude-sync-download-test-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $downloadTestDirectory | Out-Null
    try {
        $ProgressPreference = 'Stop'
        $script:downloadFails = $false
        function Invoke-WebRequest([switch]$UseBasicParsing, [string]$Uri, [string]$OutFile) {
            $script:downloadProgressPreference = $ProgressPreference
            [IO.File]::WriteAllText($OutFile, 'synthetic download fixture')
            if ($script:downloadFails) { throw 'Synthetic download failure' }
        }
        function Move-Item([string]$LiteralPath, [string]$Destination, [switch]$Force) {
            $script:moveProgressPreference = $ProgressPreference
            Microsoft.PowerShell.Management\Move-Item -LiteralPath $LiteralPath -Destination $Destination -Force:$Force
        }
        function Remove-Item([string]$LiteralPath, [switch]$Force) {
            $script:cleanupProgressPreference = $ProgressPreference
            Microsoft.PowerShell.Management\Remove-Item -LiteralPath $LiteralPath -Force:$Force
        }
        $destination = Join-Path $downloadTestDirectory 'download.bin'
        Save-OfficialDownload 'https://nodejs.org/synthetic-fixture' $destination
        Assert-Equal $script:downloadProgressPreference 'SilentlyContinue' 'Only download progress is suppressed'
        Assert-Equal $script:moveProgressPreference 'Stop' 'Original progress preference is restored before renaming'
        Assert-Equal $ProgressPreference 'Stop' 'Successful download preserves the caller preference'
        Assert-Equal (Test-Path -LiteralPath $destination) $true 'Successful download is retained'
        $script:downloadFails = $true
        Assert-Throws { Save-OfficialDownload 'https://nodejs.org/synthetic-fixture' $destination } 'Synthetic download failure'
        Assert-Equal $script:cleanupProgressPreference 'Stop' 'Failed download restores progress before cleanup'
        Assert-Equal $ProgressPreference 'Stop' 'Failed download preserves the caller preference'
        Assert-Equal (Test-Path -LiteralPath ($destination + '.partial')) $false 'Failed partial download is removed'
    } finally {
        $ProgressPreference = $previousProgressPreference
        Microsoft.PowerShell.Management\Remove-Item -LiteralPath $downloadTestDirectory -Recurse -Force
        Microsoft.PowerShell.Management\Remove-Item -LiteralPath Function:Invoke-WebRequest, Function:Move-Item, Function:Remove-Item
    }

    # Fail closed on altered downloads and invalid/wrong-publisher certificates.
    ${function:Assert-FileHash} = $originalHash
    ${function:Assert-PythonSignature} = $originalSignature
    function Get-FileHash([string]$LiteralPath, [string]$Algorithm) { return [pscustomobject]@{ Hash = $script:testHash } }
    $script:testHash = 'abcdef'
    Assert-FileHash 'download.exe' 'abcdef'
    Assert-Throws { Assert-FileHash 'download.exe' '000000' } 'SHA-256'
    function Get-AuthenticodeSignature([string]$LiteralPath) { return $script:testSignature }
    $script:testSignature = [pscustomobject]@{ Status = 'Valid'; SignerCertificate = [pscustomobject]@{ Subject = 'CN=Python Software Foundation, O=Python Software Foundation, C=US' } }
    Assert-PythonSignature 'python.exe'
    $script:testSignature = [pscustomobject]@{ Status = 'HashMismatch'; SignerCertificate = [pscustomobject]@{ Subject = 'CN=Python Software Foundation' } }
    Assert-Throws { Assert-PythonSignature 'python.exe' } 'signature'
    $script:testSignature = [pscustomobject]@{ Status = 'Valid'; SignerCertificate = [pscustomobject]@{ Subject = 'CN=Another Publisher' } }
    Assert-Throws { Assert-PythonSignature 'python.exe' } 'signature'

    # Verify the fallback's no-global-changes installer arguments and spaces.
    ${function:Invoke-PythonInstaller} = $originalPythonInstaller
    $script:installerExitCode = 0
    function Start-Process([string]$FilePath, [string[]]$ArgumentList, [switch]$Wait, [switch]$PassThru) {
        $script:installerArguments = $ArgumentList
        return [pscustomobject]@{ ExitCode = $script:installerExitCode }
    }
    Invoke-PythonInstaller 'C:\Repo With Spaces\python.exe' 'C:\Repo With Spaces\.sandbox\setup\python'
    Assert-Equal ($script:installerArguments -join '|') '/quiet|/norestart|InstallAllUsers=0|TargetDir="C:\Repo With Spaces\.sandbox\setup\python"|PrependPath=0|AppendPath=0|Include_launcher=0|InstallLauncherAllUsers=0|AssociateFiles=0|Shortcuts=0|Include_test=0|Include_doc=0|Include_pip=1' 'Fallback preserves spaces and avoids reboot/machine/PATH/launcher/association changes'
    $script:installerExitCode = 3010
    $restartMessages = @(Invoke-PythonInstaller 'C:\Repo With Spaces\python.exe' 'C:\Repo With Spaces\.sandbox\setup\python' 6>&1)
    Assert-Equal ($restartMessages -join '') 'Windows reports that a restart may be needed after installation.' 'Restart-required success only reports a message'
    $script:installerExitCode = 1603
    Assert-Throws { Invoke-PythonInstaller 'python.exe' 'target' } 'installation failed'
    Write-Host 'Windows setup regressions passed (mocked commands; no installation or launch).'
} finally {
    $env:CLAUDE_SYNC_PYTHON = $previousOverride
    $env:Path = $previousPath
    $ProgressPreference = $previousProgressPreference
}
