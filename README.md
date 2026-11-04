# Audio Streamer is two seperate programs, one a "sender" the other a "receiver" that allows audio to be sent from 
# One computer over a network to another using FFMPEG. Use alongside of PowerToyz's Mouse Without Borders utility
# and you can combie two workstations into one! One mouse, one keyboard, one set of speakers for two workstations!
# Have fun and enjoy

## Validation

From the repository folder, run the dependency-free, headless test suite:

```powershell
py -3.11 -B -m unittest discover -s tests -v
```

The tests cover existing IPv4 validation, per-user data/history paths, recording
filenames, connection-status transitions, and Receiver process-dependent controls.
Streamer lifecycle tests run isolated Python child processes to cover startup,
later exits, graceful/forced stops, and restarts, with mocked GUI wiring.
On Windows they also exercise build/dev scripts in temporary folders with a fake
builder: interpreter lookup, argument forwarding, build failures, missing outputs,
mirroring, and installer failure propagation. Windows PowerShell 5.1 is required
for those script tests; they are skipped on other platforms.
The suite also checks project Python and spec files for Python 3.11-compatible syntax.
No application windows open, audio settings change, or FFmpeg processes start
in the automated suite.
The suite uses only Python's standard library; it does not require the app venv.
Python 3.11+ can run it.
This does not replace source-run or packaged-app smoke tests.

## Rebuild

Use the included PowerShell script to rebuild both packaged apps into `dist/Audio Receiver` and `dist/Audio Streamer` with their `_internal` folders:

```powershell
.\rebuild_audio_streamer.ps1
```

Build and dev scripts share interpreter lookup relative to the repository, in this order:
1. `.venv311` in the parent folder (the existing project environment).
2. `.venv311` inside the repository.
3. `.venv` inside the repository.
4. `.venv` in the parent folder.

They do not fall back to a global `python`. If the first existing environment is
broken, repair it or explicitly pass `-PythonPath` to select another executable.
For example:

```powershell
.\rebuild_audio_streamer.ps1 -PythonPath "H:\Dropbox\Audio Streamer Programs\.venv311\Scripts\python.exe"
```

The rebuild checks the interpreter, PyInstaller, and both checked-in `.spec` files
before clearing the two app folders under `dist`. It stops on the first failure
and requires each build's EXE and `_internal` folder before mirroring or reporting
success. Both builds must pass before either app is mirrored.
Close running packaged apps before rebuilding. Cleanup/copy errors (including
locked files) stop the build explicitly; a failed cleanup can leave a partial
`dist` folder, while existing mirrored builds remain untouched until mirroring.

It does **not** delete `build/Audio Receiver` or `build/Audio Streamer` by default,
and it mirrors runnable `exe + _internal` files from `dist` back into those folders.

Optional flags:
- `-CleanBuild` also wipes `build/Audio Receiver` and `build/Audio Streamer` before rebuilding.
- `-MirrorToBuild $false` skips the mirror step.

Build environment lock (current):
- Python 3.11.9 preferred for builds
- PyInstaller 6.20.0

## Dev Runs

For source-based testing, do not use bare `python .\Audio Receiver.py` or `python .\Audio Streamer.py` unless you have already activated the correct environment.

Use the dev launchers; they resolve the same environment as the build script,
forward application arguments, and report a nonzero application exit:

```powershell
.\run_audio_receiver_dev.ps1
.\run_audio_streamer_dev.ps1
```

Both launchers accept the same optional `-PythonPath` override. The current
Python 3.11.9 environment is at `H:\Dropbox\Audio Streamer Programs\.venv311`.
VS Code should use its `Scripts\python.exe` too; an existing terminal's bare
`python` command can still select a different installation.

### Streamer status and shutdown

- **Connecting** means FFmpeg has been requested but streaming is not confirmed.
- **Streaming** appears only after FFmpeg reports positive output-time progress.
  This confirms sender output, not that the Receiver's speakers are playing.
- **Stopping** disables Start/Stop while the owned FFmpeg process shuts down.
  It first receives `q`; if it does not exit within three seconds, it is killed
  and reaped with another bounded wait. Output-reader threads are joined.
- Unexpected exits show **Error**, restore Start, and display the exit code and
  recent FFmpeg diagnostics when available. Even an unrequested zero-code exit
  is treated as an ended stream, not a successful user stop.
- A connection reset after confirmed streaming instead shows an informational
  **Receiver Disconnected** notice with reconnect instructions. Start is restored;
  the status remains Error until restarted. Technical details stay in the log.
  Receiver Stop and a lost connection cannot be distinguished from the sender.
- A connection is saved only after streaming is confirmed. Stop and window-close
  do not block Tk while FFmpeg is shutting down; the window closes after cleanup.

## Per-user settings

Both apps use the shared settings module and application-version metadata
(`APP_VERSION`, currently `1.0.3`). Version information is included in startup logs.
Settings live outside the application/install folder:

- `%LOCALAPPDATA%\Audio Streamer\settings.json`
- `%LOCALAPPDATA%\Audio Receiver\settings.json`

If `LOCALAPPDATA` is unavailable, the path falls back to
`%USERPROFILE%\AppData\Local`. The same location is used for each app's log.
Logs are stored in a `logs` subfolder with an application-named `.log` file:
`%LOCALAPPDATA%\Audio Receiver\logs\Audio_Receiver.log` and
`%LOCALAPPDATA%\Audio Streamer\logs\Audio_Streamer.log`. Existing root-level
log files are left untouched.
Missing settings use in-memory defaults; a file is created on the first save.
The Receiver's File, Options, and Help menus include recording-folder selection,
open-folder actions, Receiver name/reset preferences, and About information.
The Streamer's File, Connections, Options, and Help menus provide exit, saved
Receiver management, settings reset, log-folder access, and About information.
Automatic Receiver discovery is not available yet; its menu actions explain that
discovery is planned for a later update. Manual IP entry and the existing
Start/Stop controls remain available.
Recordings default to `%USERPROFILE%\Music\Audio Receiver Recordings` when the
Music folder exists, otherwise `%LOCALAPPDATA%\Audio Receiver\Recordings`.
The folder is checked for writability before recording, and each recording start
uses a fresh timestamped MP3 filename. Existing schema-version-1 settings remain
valid; Receiver preferences are added without changing the schema version.
Receiver logs record the target path at recording start and report FFmpeg's exit
code plus the output file's existence and size when recording ends.

The versioned JSON format is:

```json
{
  "schema_version": 1,
  "saved_receivers": [["192.168.1.10", "Office Receiver"]],
  "receiver_name": "",
  "recording_folder": null
}
```

On the Streamer's first run without settings, saved addresses are imported from
the first existing `ip_history.json`: the current per-user data folder, the old
`%USERPROFILE%\AppData\Local\Audio Streamer` location, then the application's
resource/source folder. The original history file is never deleted or changed.
Once settings exist they take precedence; clearing saved connections will not
re-import old history.

JSON structure, schema version, IPv4 addresses, and names are validated. A bad or
unreadable file is reported in the log and an error dialog, not overwritten with
empty defaults. Manual streaming remains available, but saved-connection changes
are blocked until the file is repaired and the app restarted.

Saves write and flush a temporary file in the settings folder, then atomically
replace the destination. If saving fails, the previous settings and in-memory
connection list remain unchanged, and the error is displayed. The temporary file
is cleaned up. Do not edit the file while either app is running.

### Session diagnostics (Slice 2D)

Both apps write UTF-8 logs with startup version/resource/settings paths,
process IDs, connection milestones, stop reasons, exit codes (including signed
Windows codes), and a bounded tail of process diagnostics at session end.
Streamer confirms output using FFmpeg progress. Receiver recording confirms
output the same way; playback-only logs when FFplay opens its input, which is
not proof that speakers are playing.

Process stderr is continuously drained so it cannot block audio, but only
recent diagnostic lines are retained. Progress messages are not logged one by
one. Unexpected Receiver process failures show an error and direct users to
the log; a requested stop is labeled separately.

Recording logs include the output path and size. Missing/empty output is an
error; nonzero or unavailable exit codes leave finalization unconfirmed even
when a nonempty file exists. Receiver's existing forced-stop/window-close
behavior is not replaced here; graceful owned-process cleanup remains Slice 1B.
This logging does not establish a firewall failure without process evidence.

## Discovery protocol spike (Slice 3A)

The standalone `discovery_spike.py` prototype uses IPv4 UDP port 6006; neither
app runs it yet. No audio devices, app settings, or firewall rules are changed.
Use two PowerShell terminals for a bounded, local-only test:

```powershell
& "H:\Dropbox\Audio Streamer Programs\.venv311\Scripts\python.exe" -B "H:\Dropbox\Audio Streamer Programs\AudioStreamer\discovery_spike.py" respond --bind 127.0.0.1
```

```powershell
& "H:\Dropbox\Audio Streamer Programs\.venv311\Scripts\python.exe" -B "H:\Dropbox\Audio Streamer Programs\AudioStreamer\discovery_spike.py" discover --interface 127.0.0.1/8 --unicast
```

The responder exits after 30 seconds; discovery waits up to 2 seconds and prints
JSON results. For an explicitly authorized LAN test, bind the responder to
`0.0.0.0` and omit `--unicast` on the discovering machine, supplying its actual
local IPv4/prefix with `--interface`. Repeat `--interface` to select adapters.
Do not include VPN interfaces unless intentionally testing that network.
Inbound UDP firewall policy may require administrator approval; the prototype
does not change policy. Empty results do not identify the cause of failure.
See the Slice 3A section of `IMPLEMENTATION_PLAN.md` for the protocol decision,
limits, compatibility rules, and outstanding physical-network tests.

## Installers

The project now includes two separate installer definitions:
- `installers/AudioReceiver.iss`: user-level installer (no admin required)
- `installers/AudioStreamer.iss`: admin installer (VB-CABLE + firewall setup)

Build both installers with:

```powershell
.\build_installers.ps1 -AppVersion 1.0.0
```

Or use one-command target wrappers:

```powershell
# Build app(s) + make only Streamer installer
.\make_audio_streamer.ps1 -AppVersion 1.0.3

# Build app(s) + make only Receiver installer
.\make_audio_receiver.ps1 -AppVersion 1.0.3
```

Advanced wrapper (shared entry point):

```powershell
.\make_audio.ps1 -Target streamer -AppVersion 1.0.3
.\make_audio.ps1 -Target receiver -AppVersion 1.0.3
```

Notes:
- This command runs `rebuild_audio_streamer.ps1` first unless `-SkipRebuild` is used.
- All installer entry points accept `-PythonPath` and forward it to the rebuild.
- A failed rebuild stops installer creation. `-SkipRebuild` uses existing packages and ignores `-PythonPath`.
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
