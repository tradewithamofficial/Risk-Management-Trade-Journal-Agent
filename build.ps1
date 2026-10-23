# Reuse the previous agents' onedir packaging. Never copy user databases.
param([switch]$SkipDependencyInstall)
$ErrorActionPreference='Stop'
$buildPython=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$releaseFolder=Join-Path $PSScriptRoot 'release\RiskManagementTradeJournalAgent'
$icon=Join-Path $PSScriptRoot 'assets\TradeWithAM_Robot.ico'
if (-not (Test-Path -LiteralPath $buildPython)) { throw 'Create .venv and install requirements first.' }
if (Test-Path -LiteralPath $releaseFolder) { throw 'Preserve/move existing release folder before rebuilding. No local data will be overwritten.' }
if (-not (Test-Path -LiteralPath $icon)) { throw 'Missing final gold ICO.' }
Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not $SkipDependencyInstall) {
        & $buildPython -m pip install -r (Join-Path $PSScriptRoot 'requirements-build.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Build dependencies failed.' }
    }
    & $buildPython -m PyInstaller --noconfirm --clean --onedir --windowed --name RiskManagementTradeJournalAgent `
        --icon $icon --version-file (Join-Path $PSScriptRoot 'windows-version.txt') `
        --add-data "$icon;assets" --distpath (Join-Path $PSScriptRoot 'release') `
        --workpath (Join-Path $PSScriptRoot 'build') --specpath (Join-Path $PSScriptRoot 'build') `
        (Join-Path $PSScriptRoot 'main.py')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
    foreach ($name in @('README.md','INSTALL.md','LICENSE','THIRD-PARTY-NOTICES.md')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $releaseFolder
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'RELEASE-SETUP.txt') -Destination (Join-Path $releaseFolder 'README-SETUP.txt')
    New-Item -ItemType Directory -Path (Join-Path $releaseFolder 'docs') | Out-Null
    foreach ($name in @('CHATGPT_MASTER_PROMPT.md','RELEASE-v1.0.0.md')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot "docs\$name") -Destination (Join-Path $releaseFolder 'docs')
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'third_party_licenses') -Destination $releaseFolder -Recurse
    Write-Host "Created: $(Join-Path $releaseFolder 'RiskManagementTradeJournalAgent.exe')"
    Write-Host 'Distribute the complete folder; no personal database is included.'
} finally { Pop-Location }
