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
