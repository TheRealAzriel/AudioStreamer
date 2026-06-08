param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AppArgs
)

Set-Location "$PSScriptRoot"

$python = "h:/Dropbox (Personal)/Audio Streamer Programs/.venv311/Scripts/python.exe"
if (-not (Test-Path $python)) {
    throw "Expected Python 3.11 virtualenv not found at $python"
}

Write-Host "Running Audio Receiver with: $python"
& $python "$PSScriptRoot\Audio Receiver.py" @AppArgs