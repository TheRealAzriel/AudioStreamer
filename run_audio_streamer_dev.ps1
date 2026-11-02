[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$PythonPath,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AppArgs
)

$ErrorActionPreference = 'Stop'
$python = & "$PSScriptRoot\resolve_project_python.ps1" -PythonPath $PythonPath

Write-Host "Running Audio Streamer with: $python"
Push-Location -LiteralPath $PSScriptRoot
try {
    & $python "$PSScriptRoot\Audio Streamer.py" @AppArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Audio Streamer exited with code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}