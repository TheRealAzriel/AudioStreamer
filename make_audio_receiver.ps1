param(
    [string]$AppVersion = "1.0.3",
    [switch]$SkipRebuild
)

Set-Location "$PSScriptRoot"
& "$PSScriptRoot\make_audio.ps1" -Target receiver -AppVersion $AppVersion -SkipRebuild:$SkipRebuild
