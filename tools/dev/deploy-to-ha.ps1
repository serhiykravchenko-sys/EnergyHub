[CmdletBinding()]
param(
    [ValidateSet("Addon", "HomeAssistant")]
    [string]$Scope = "Addon",

    [ValidateSet(
        "automations.yaml",
        "scripts.yaml",
        "scenes.yaml",
        "configuration.yaml"
    )]
    [string[]]$ConfigFiles = @(),

    [ValidateSet(
        "input_boolean",
        "input_number",
        "timer",
        "lovelace.dashboard_powmr1",
        "lovelace_dashboards",
        "lovelace_resources"
    )]
    [string[]]$StorageFiles = @(),

    [switch]$HomeAssistantStopped,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Assert-SourceFile {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required source file is missing: $Path"
    }
}

function Copy-WithBackup {
    param(
        [string]$Source,
        [string]$Target,
        [string]$Backup
    )

    Write-Host "  Source: $Source"
    Write-Host "  Target: $Target"

    if ($DryRun) {
        Write-Host "  Backup if target exists: $Backup"
        Write-Host "  Dry run: no file copied."
        return
    }

    if (Test-Path -LiteralPath $Target -PathType Leaf) {
        $BackupDirectory = Split-Path -Parent $Backup
        New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
        Copy-Item -LiteralPath $Target -Destination $Backup -Force
    }

    Copy-Item -LiteralPath $Source -Destination $Target -Force
    Write-Host "  Copied."
}

Write-Host "Deploying EnergyHub to Home Assistant..."
Write-Host "Scope: $Scope"

if ($Scope -eq "Addon") {
    if ($ConfigFiles.Count -gt 0 -or $StorageFiles.Count -gt 0) {
        throw "-ConfigFiles and -StorageFiles require -Scope HomeAssistant."
    }

    if ($DryRun) {
        Write-Host "Dry run: add-on mirror skipped."
        exit 0
    }

    & "$PSScriptRoot\sync-to-ha.ps1"

    if ($LASTEXITCODE -gt 7) {
        throw "Add-on synchronization failed with robocopy exit code $LASTEXITCODE."
    }

    Write-Host ""
    Write-Host "Add-on files synchronized."
    Write-Host "Now rebuild and restart the Energy Hub add-on, then inspect its logs."
    exit 0
}

if ($ConfigFiles.Count -eq 0 -and $StorageFiles.Count -eq 0) {
    throw "Select at least one -ConfigFiles or -StorageFiles item for -Scope HomeAssistant."
}

if ($StorageFiles.Count -gt 0 -and -not $DryRun -and -not $HomeAssistantStopped) {
    throw "Refusing to deploy .storage files while Home Assistant may be running. Stop HA Core and pass -HomeAssistantStopped."
}

$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
$SourceRoot = Join-Path $RepoRoot "homeassistant\live"
$TargetRoot = "\\homeassistant\config"

foreach ($File in $ConfigFiles) {
    Assert-SourceFile -Path (Join-Path $SourceRoot "config\$File")
}

foreach ($File in $StorageFiles) {
    Assert-SourceFile -Path (Join-Path $SourceRoot "storage\$File")
}

if (-not $DryRun -and -not (Test-Path -LiteralPath $TargetRoot -PathType Container)) {
    throw "Home Assistant config share is unavailable: $TargetRoot"
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss-fff"
$BackupRoot = Join-Path $TargetRoot "energyhub-deploy-backups\$Timestamp"

foreach ($File in $ConfigFiles) {
    Write-Host ""
    Write-Host "Configuration file: $File"
    Copy-WithBackup `
        -Source (Join-Path $SourceRoot "config\$File") `
        -Target (Join-Path $TargetRoot $File) `
        -Backup (Join-Path $BackupRoot "config\$File")
}

foreach ($File in $StorageFiles) {
    Write-Host ""
    Write-Host "Storage file: $File"
    Copy-WithBackup `
        -Source (Join-Path $SourceRoot "storage\$File") `
        -Target (Join-Path $TargetRoot ".storage\$File") `
        -Backup (Join-Path $BackupRoot "storage\$File")
}

if ($DryRun) {
    Write-Host ""
    Write-Host "Dry run completed. No target files were changed."
    exit 0
}

Write-Host ""
Write-Host "Home Assistant files synchronized. Previous targets were backed up under:"
Write-Host "  $BackupRoot"
Write-Host ""

if ($StorageFiles.Count -gt 0) {
    Write-Host "Run 'ha core check', start HA Core, and inspect helpers, automations, dashboards, and logs."
    Write-Host "Startup loads YAML and .storage; do not reload YAML separately."
}
else {
    if ($ConfigFiles -contains "configuration.yaml") {
        Write-Host "Run 'ha core check', then restart HA Core for configuration.yaml."
        Write-Host "The restart loads every selected YAML file; do not reload components separately."
    }
    else {
        if ($ConfigFiles -contains "automations.yaml") {
            Write-Host "Reload Automations from Developer Tools > YAML."
        }
        if ($ConfigFiles -contains "scripts.yaml") {
            Write-Host "Reload Scripts from Developer Tools > YAML."
        }
        if ($ConfigFiles -contains "scenes.yaml") {
            Write-Host "Reload Scenes from Developer Tools > YAML."
        }
    }
}

exit 0
