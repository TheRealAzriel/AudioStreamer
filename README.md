# Audio Streamer is two seperate programs, one a "sender" the other a "receiver" that allows audio to be sent from 
# One computer over a network to another using FFMPEG. Use alongside of PowerToyz's Mouse Without Borders utility
# and you can combie two workstations into one! One mouse, one keyboard, one set of speakers for two workstations!
# Have fun and enjoy

## Rebuild

Use the included PowerShell script to rebuild both packaged apps into `dist/Audio Receiver` and `dist/Audio Streamer` with their `_internal` folders:

```powershell
.\rebuild_audio_streamer.ps1
```

The script uses the workspace venv at `H:\Dropbox (Personal)\Audio Streamer Programs\.venv` and rebuilds from the checked-in `.spec` files.
It does **not** delete `build/Audio Receiver` or `build/Audio Streamer` by default, and it mirrors runnable `exe + _internal` files from `dist` back into those build folders.

Optional flags:
- `-CleanBuild` also wipes `build/Audio Receiver` and `build/Audio Streamer` before rebuilding.
- `-MirrorToBuild $false` skips the mirror step.

Build environment lock (current):
- Python 3.14.2
- PyInstaller 6.20.0

## Installers

The project now includes two separate installer definitions:
- `installers/AudioReceiver.iss`: user-level installer (no admin required)
- `installers/AudioStreamer.iss`: admin installer (VB-CABLE + firewall setup)

Build both installers with:

```powershell
.\build_installers.ps1 -AppVersion 1.0.0
```

Notes:
- This command runs `rebuild_audio_streamer.ps1` first unless `-SkipRebuild` is used.
- Inno Setup 6 must be installed (`ISCC.exe`).
- Compiled installer binaries are written to `installer-output/`.

### How installation works for end users

- You distribute the generated setup executables from `installer-output/` (not a zip by default).
- Users install by double-clicking a setup executable:
	- `AudioReceiverSetup-<version>.exe`
	- `AudioStreamerSetup-<version>.exe`
- The installer copies files to the install location, creates Start Menu entries (searchable in Windows), and optionally desktop shortcuts.
- Streamer setup also performs one-time system setup (VB-CABLE + firewall rules) with administrator rights.
- After install, users launch from Start Menu/Desktop like a normal Windows app.
