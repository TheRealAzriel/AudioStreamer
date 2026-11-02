param(
    [string]$PythonPath
)

$ErrorActionPreference = 'Stop'

if ($PythonPath) {
    $candidates = @($PythonPath)
} else {
    $parentDirectory = Split-Path -Parent $PSScriptRoot
    $candidates = @(
        "$parentDirectory\.venv311\Scripts\python.exe",
        "$PSScriptRoot\.venv311\Scripts\python.exe",
        "$PSScriptRoot\.venv\Scripts\python.exe",
        "$parentDirectory\.venv\Scripts\python.exe"
    )
}

$python = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $python) {
    throw "Python interpreter not found. Checked: $($candidates -join ', '). Create a project virtual environment or pass -PythonPath."
}

$python = (Resolve-Path -LiteralPath $python).ProviderPath
try {
    $probe = & $python -c "import sys; print(sys.version.split()[0])" 2>&1
} catch {
    throw "Python interpreter cannot run: $python. Repair the environment or pass -PythonPath. $_"
}
if ($LASTEXITCODE -ne 0) {
    throw "Python interpreter cannot run: $python. Repair the environment or pass -PythonPath. $($probe -join ' ')"
}

$python
