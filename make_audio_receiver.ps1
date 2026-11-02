param(
    [string]$AppVersion = "1.0.3",
    [switch]$SkipRebuild,
    [string]$PythonPath
)

Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot\make_audio.ps1" -Target receiver -AppVersion $AppVersion -SkipRebuild:$SkipRebuild -PythonPath $PythonPath
