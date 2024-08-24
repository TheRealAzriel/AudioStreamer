# Attempt to use $PSScriptRoot; fall back to Get-Location if it's not available
if ($PSScriptRoot) {
    $currentDirectory = $PSScriptRoot
} else {
    $currentDirectory = Get-Location
}

#$currentDirectory = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent

$modulePath = Join-Path -Path $currentDirectory -ChildPath "AudioDeviceCmdlets.psd1"
$loggingfilePath = Join-Path -Path $currentDirectory -ChildPath "log.txt"  # Ensure logging path is defined

# Log for debugging purposes
"{0}: Current directory is {1}" -f (Get-Date), $currentDirectory | Out-File -Append -FilePath $loggingfilePath
"{0}: Module path is {1}" -f (Get-Date), $modulePath | Out-File -Append -FilePath $loggingfilePath

    try {
        Import-Module $modulePath -ErrorAction Stop
        "{0}: Module imported successfully." -f (Get-Date) | Out-File -Append -FilePath $loggingfilePath
    } catch {
        "{0}: Failed to import module: {1}" -f (Get-Date), $_.Exception.Message | Out-File -Append -FilePath $loggingfilePath
        exit 1
    }

$audioDevice = "CABLE Input (VB-Audio Virtual Cable)"
$playbackDevice = Get-AudioDevice -List | Where-Object {($_.Name -eq $audioDevice -and $_.Type -eq 'Playback')} |Select-Object -ExpandProperty ID

# Log the playback device info for debugging
"{0}: Playback Device ID: {1}" -f (Get-Date), $playbackDevice | Out-File -Append -FilePath $loggingfilePath

if ($null -eq $playbackDevice) {
    "{0}: Playback device '{1}' not found." -f (Get-Date), $audioDevice | Out-File -Append -FilePath $loggingfilePath
    #[System.Windows.MessageBox]::Show("Playback device not found. Please ensure VB-Audio Virtual Cable is installed and try again.", "Error", [System.Windows.MessageBoxButton]::OK, [System.Windows.MessageBoxImage]::Error)
    exit 1
}

try {
    # Set the default playback device
    Set-AudioDevice $playbackDevice -ErrorAction SilentlyContinue
    Set-AudioDevice -PlaybackVolume 100 -ErrorAction SilentlyContinue
    Set-AudioDevice -PlaybackMute $false -ErrorAction SilentlyContinue
    "{0}: Playback device set successfully." -f (Get-Date) | Out-File -Append -FilePath $loggingfilePath
} catch {
    "{0}: Error setting audio device '{1}': {2}" -f (Get-Date), $audioDevice, $_.Exception.Message | Out-File -Append -FilePath $loggingfilePath
    #[System.Windows.MessageBox]::Show("Please ensure VB-Audio Virtual Cable is installed and try again.", "Error", [System.Windows.MessageBoxButton]::OK, [System.Windows.MessageBoxImage]::Error)
    exit 1
}
