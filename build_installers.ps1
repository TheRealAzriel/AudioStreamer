param(
    [string]$AppVersion = "1.0.0",
    [switch]$SkipRebuild
)

Set-Location "$PSScriptRoot"

$isccCandidates = @(
    "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)

$isccPath = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $isccPath) {
    throw "Inno Setup compiler not found. Install Inno Setup 6 and retry."
}

if (-not $SkipRebuild) {
    .\rebuild_audio_streamer.ps1
}

$tempOutput = Join-Path $env:TEMP "AudioStreamerInstallerOutput"
New-Item -ItemType Directory -Path $tempOutput -Force | Out-Null

if (Test-Path "$PSScriptRoot\installer-output") {
    Remove-Item -Recurse -Force "$PSScriptRoot\installer-output" -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path "$PSScriptRoot\installer-output" -Force | Out-Null

& $isccPath "/DAppVersion=$AppVersion" "/O$tempOutput" ".\installers\AudioReceiver.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Audio Receiver installer build failed."
}

& $isccPath "/DAppVersion=$AppVersion" "/O$tempOutput" ".\installers\AudioStreamer.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Audio Streamer installer build failed."
}

Copy-Item -Path "$tempOutput\*.exe" -Destination "$PSScriptRoot\installer-output" -Force

Write-Host "Installer build complete. Outputs are in: $PSScriptRoot\installer-output"
