param(
    [switch]$CleanBuild,
    [bool]$MirrorToBuild = $true,
    [string]$PythonPath
)

$ErrorActionPreference = 'Stop'
$python = & "$PSScriptRoot\resolve_project_python.ps1" -PythonPath $PythonPath

Write-Host "Using Python interpreter: $python"

Push-Location -LiteralPath $PSScriptRoot
try {
    & $python -m PyInstaller --version
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller is unavailable in $python. Install the documented build dependencies before rebuilding."
    }

    $appNames = @('Audio Receiver', 'Audio Streamer')
    foreach ($appName in $appNames) {
        if (-not (Test-Path -LiteralPath "$PSScriptRoot\$appName.spec" -PathType Leaf)) {
            throw "Build specification not found: $PSScriptRoot\$appName.spec"
        }
    }

    foreach ($appName in $appNames) {
        $distDirectory = "$PSScriptRoot\dist\$appName"
        if (Test-Path -LiteralPath $distDirectory) {
            Remove-Item -LiteralPath $distDirectory -Recurse -Force
        }
        $buildDirectory = "$PSScriptRoot\build\$appName"
        if ($CleanBuild -and (Test-Path -LiteralPath $buildDirectory)) {
            Remove-Item -LiteralPath $buildDirectory -Recurse -Force
        }
    }

    foreach ($appName in $appNames) {
        & $python -m PyInstaller --noconfirm "$PSScriptRoot\$appName.spec"
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller failed for $appName (exit code $LASTEXITCODE)."
        }
        if (-not (Test-Path -LiteralPath "$PSScriptRoot\dist\$appName\$appName.exe" -PathType Leaf)) {
            throw "Expected build output not found: $PSScriptRoot\dist\$appName\$appName.exe"
        }
        if (-not (Test-Path -LiteralPath "$PSScriptRoot\dist\$appName\_internal" -PathType Container)) {
            throw "Expected build output not found: $PSScriptRoot\dist\$appName\_internal"
        }
    }

    if ($MirrorToBuild) {
        foreach ($appName in $appNames) {
            $buildDirectory = "$PSScriptRoot\build\$appName"
            New-Item -ItemType Directory -Path $buildDirectory -Force | Out-Null
            if (Test-Path -LiteralPath "$buildDirectory\_internal") {
                Remove-Item -LiteralPath "$buildDirectory\_internal" -Recurse -Force
            }
            Copy-Item -LiteralPath "$PSScriptRoot\dist\$appName\_internal" -Destination "$buildDirectory\_internal" -Recurse -Force
            Copy-Item -LiteralPath "$PSScriptRoot\dist\$appName\$appName.exe" -Destination "$buildDirectory\$appName.exe" -Force
        }
    }

    Write-Host "Build complete. Outputs are in: $PSScriptRoot\dist"
    if ($MirrorToBuild) {
        Write-Host "Mirrored runnable files to: $PSScriptRoot\build"
    }
} finally {
    Pop-Location
}