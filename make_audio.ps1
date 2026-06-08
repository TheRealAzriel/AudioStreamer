param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("streamer", "receiver")]
    [string]$Target,

    [string]$AppVersion = "1.0.3",
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

$outputDir = "$PSScriptRoot\installer-output"
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

switch ($Target) {
    "streamer" {
        $issFile = ".\installers\AudioStreamer.iss"
        $outputFile = "AudioStreamerSetup-$AppVersion.exe"
    }
    "receiver" {
        $issFile = ".\installers\AudioReceiver.iss"
        $outputFile = "AudioReceiverSetup-$AppVersion.exe"
    }
    default {
        throw "Unsupported target: $Target"
    }
}

& $isccPath "/DAppVersion=$AppVersion" "/O$tempOutput" $issFile
if ($LASTEXITCODE -ne 0) {
    throw "Installer build failed for target '$Target'."
}

$builtInstaller = Join-Path $tempOutput $outputFile
if (-not (Test-Path $builtInstaller)) {
    throw "Expected installer was not found: $builtInstaller"
}

Copy-Item -Path $builtInstaller -Destination $outputDir -Force
Write-Host "Created installer: $outputDir\$outputFile"
