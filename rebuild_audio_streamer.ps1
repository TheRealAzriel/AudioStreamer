param(
    [switch]$CleanBuild,
    [bool]$MirrorToBuild = $true
)

Set-Location "$PSScriptRoot"

$pythonCandidates = @(
    "h:/Dropbox (Personal)/Audio Streamer Programs/.venv311/Scripts/python.exe",
    "h:/Dropbox (Personal)/Audio Streamer Programs/.venv/Scripts/python.exe"
)

$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
    throw "No project virtual environment found. Expected .venv311 or .venv under H:\Dropbox (Personal)\Audio Streamer Programs."
}

Write-Host "Using Python interpreter: $python"

# Keep dist clean for reproducible outputs.
Remove-Item -Recurse -Force `
    "$PSScriptRoot\dist\Audio Receiver", `
    "$PSScriptRoot\dist\Audio Streamer" `
    -ErrorAction SilentlyContinue

if ($CleanBuild) {
    Remove-Item -Recurse -Force `
        "$PSScriptRoot\build\Audio Receiver", `
        "$PSScriptRoot\build\Audio Streamer" `
        -ErrorAction SilentlyContinue
}

& $python -m PyInstaller --noconfirm "$PSScriptRoot\Audio Receiver.spec"
& $python -m PyInstaller --noconfirm "$PSScriptRoot\Audio Streamer.spec"

if ($MirrorToBuild) {
    New-Item -ItemType Directory -Path "$PSScriptRoot\build\Audio Receiver" -Force | Out-Null
    New-Item -ItemType Directory -Path "$PSScriptRoot\build\Audio Streamer" -Force | Out-Null

    Remove-Item -Recurse -Force "$PSScriptRoot\build\Audio Receiver\_internal" -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force "$PSScriptRoot\build\Audio Streamer\_internal" -ErrorAction SilentlyContinue

    Copy-Item -Recurse -Force "$PSScriptRoot\dist\Audio Receiver\_internal" "$PSScriptRoot\build\Audio Receiver\_internal"
    Copy-Item -Recurse -Force "$PSScriptRoot\dist\Audio Streamer\_internal" "$PSScriptRoot\build\Audio Streamer\_internal"

    Copy-Item -Force "$PSScriptRoot\dist\Audio Receiver\Audio Receiver.exe" "$PSScriptRoot\build\Audio Receiver\Audio Receiver.exe"
    Copy-Item -Force "$PSScriptRoot\dist\Audio Streamer\Audio Streamer.exe" "$PSScriptRoot\build\Audio Streamer\Audio Streamer.exe"
}

Write-Host "Build complete. Outputs are in: $PSScriptRoot\dist"
if ($MirrorToBuild) {
    Write-Host "Mirrored runnable files to: $PSScriptRoot\build"
}