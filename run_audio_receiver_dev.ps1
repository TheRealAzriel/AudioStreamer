[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$PythonPath,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AppArgs
)

$ErrorActionPreference = 'Stop'
$python = & "$PSScriptRoot\resolve_project_python.ps1" -PythonPath $PythonPath

Write-Host "Running Audio Receiver with: $python"
Push-Location -LiteralPath $PSScriptRoot
try {
    & $python "$PSScriptRoot\Audio Receiver.py" @AppArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Audio Receiver exited with code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}