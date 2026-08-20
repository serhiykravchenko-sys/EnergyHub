$ErrorActionPreference = "Stop"

$Source = (Resolve-Path "$PSScriptRoot\..\..\telegram-family-bot").Path
$Target = "\\homeassistant\addons\local\telegram_family_assistant"

if (-not $Source.EndsWith("telegram-family-bot")) {
    throw "Unexpected source directory: $Source"
}

if ($Target -ne "\\homeassistant\addons\local\telegram_family_assistant") {
    throw "Unexpected target directory: $Target"
}

New-Item -ItemType Directory -Force -Path $Target | Out-Null

robocopy $Source $Target /MIR /XD __pycache__ /XF *.pyc
$ExitCode = $LASTEXITCODE

if ($ExitCode -ge 8) {
    throw "Telegram Family Assistant synchronization failed with robocopy exit code $ExitCode."
}

Write-Host "Telegram Family Assistant synchronized. In Home Assistant, check the App store for updates."
