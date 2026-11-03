# Audio Streamer Development Plan

## Goal

Improve Audio Streamer and Audio Receiver through small, independently reviewed branches while preserving the preferred installed user experience.

The work includes:

- Fixing build portability and process-lifecycle defects.
- Adding native Windows-style menus to both applications.
- Allowing users to choose and persist the Receiver recording folder.
- Adding hybrid, on-demand Receiver discovery while retaining manual addresses.
- Replacing VB-CABLE with a standard-user Windows audio-capture solution.

## Current Baseline Status

The Receiver and Streamer baselines are approved.

- The current `uiux_updates` Receiver and Streamer were selected for promotion to `master`.
- The installed Receiver at `C:\Users\Chad\AppData\Local\Audio Receiver` is the approved Receiver baseline.
  - Its launcher has the same SHA-256 hash as the Receiver executables currently in `build` and `dist`.
  - All 946 application files in the installed package match `dist\Audio Receiver` by relative path, size, and SHA-256 hash after excluding installer metadata and the runtime log.
  - Its preferred UI is the light layout with a vertical volume control; Receive Stream, Stop Receiving, and Receive & Record controls; Mute All; status indicator; Play Recording and Stop Playing controls; and the local IP display.
  - The matching Receiver source is present on `uiux_updates` and has not changed since commit `b8c01e8`.
- `dist\_Audio Receiver\Audio Receiver.exe` is a distinct rejected legacy artifact:
  - SHA-256: `B55FCC58840CD301838D03E97DE8A31BFAEB9BA5F6180ED8E974E9472E389FBE`
  - Build timestamp: February 11, 2026 at 4:05 PM
  - Its visible UI has a dark layout with separate Receive, Stop Receiving, Start Recording, Stop Recording, Mute All, bitrate, playback, and local-IP controls.
  - The distinctive labels and layout match the Receiver source introduced by commit `6633d34` and subsequently changed during repository cleanup and later UI work.
  - Do not use this artifact or commit `6633d34` as the Receiver design baseline.
- The proposed installed Streamer path, `C:\Users\Chad\AppData\Local\Audio Receiver\Audio Streamer.exe`, does not currently exist.
- No installed Audio Streamer Start Menu shortcut or executable was found in the common installation locations checked.
- Despite the missing installed Streamer executable, the current `uiux_updates` Streamer source and packaged build are the approved Streamer baseline.

Prepare the approved sources on `cleanup/prepare-master-baseline`, remove tracked generated cache files, validate both applications, and then fast-forward local `master`. Keep `uiux_updates` temporarily for reference.

## Working Decisions

- Use native Tk/Windows menu bars with `File`, `Options`, and `Help` menus.
- Receiver discovery will be hybrid and on demand:
  - Keep manual IP entry.
  - Keep saved connections.
  - Add an explicit Discover/Refresh operation.
- Recordings will default to a user-writable folder.
- Users can browse for a different recording folder, and the choice will persist.
- Research both system-wide and per-application Windows audio capture before choosing the VB-CABLE replacement.
- VB-CABLE removal is the final major phase.

## Branch and Review Rules

1. Resolve and approve the source/UI baseline first.
2. Establish the approved baseline on `master`.
3. Create one short-lived branch per slice from the latest `master`.
4. Merge a slice before creating a dependent branch.
5. Do not create all branches in advance.
6. Keep unrelated fixes out of each branch.
7. Each pull request must include:
   - Focused validation or automated tests.
   - Updated documentation for changed behavior.
   - Python syntax/static validation.
   - A packaged-application smoke test when build or packaging behavior changes.
8. Preserve manual workflows until their replacement has been proven.

## Phase 0: Recover and Approve the Baseline

### Slice 0A: Approve the Application Baseline

**Status:** Complete

- Preserve the approved Receiver from the current `uiux_updates` source.
- Preserve the current `uiux_updates` Streamer source and packaged build.
- Reject `dist\_Audio Receiver` as an obsolete legacy Receiver artifact.

**Acceptance criteria**

- The approved Receiver remains tied to the current source.
- The approved Streamer remains tied to the current source.
- Both approved applications are prepared on `cleanup/prepare-master-baseline`.

### Slice 0B: Establish the Approved Baseline

**Branch:** Determined by Slice 0A

- Restore or forward-port the approved versions onto a clean baseline.
- Preserve the approved layout, labels, controls, and normal workflows.
- Remove only clearly abandoned generated artifacts from source control.
- Build and run both applications from source.
- Package both applications and compare them with the approved baseline.
- Merge the approved baseline into `master`.

**Acceptance criteria**

- `master` contains the approved Receiver and Streamer source.
- Source-run and packaged applications have materially equivalent UI and behavior.
- Both applications launch without relying on undocumented machine-specific paths.

### Slice 0C: Add a Test Foundation

**Branch:** `chore/test-foundation`

**Status:** Merged into local and remote `master` at `4351464`. All 17 headless
tests pass on Python 3.11.9 and 3.14.7, including Python 3.11 syntax checks.

- Add lightweight automated tests that do not open GUI windows or change system audio.
- Make pure settings, path, validation, discovery-message, and process-state logic importable.
- Add a single documented validation command.
- Cover IP validation, settings paths, recording filenames, and process-state transitions.

The initial suite preserves existing behavior through the dependency-free
`audio_common.py` helpers used by both apps. It covers data/history paths, IPv4
validation, recording filenames, status transitions, and Receiver controls derived
from process presence. Discovery-message and settings-JSON tests will be added
with those features; neither implementation exists yet. Actual child-process
lifecycle tests belong to Slices 1B and 1C. See README for the validation command.

Python 3.11.9 has been reinstalled and the parent `.venv311` environment repaired
without replacing its existing packages. Both application modules import
successfully with that environment, and dependency checks pass. VS Code's
environment tools report a successful selection but still list the old
interpreter; manually select the repaired environment if needed. GUI and
packaged-app smoke tests have not been performed for this
slice; portable build/dev launcher paths remain in Slice 1A.

## Phase 1: Reliability Fixes

### Slice 1A: Portable Build and Development Scripts

**Branch:** `fix/build-portability`

**Status:** Merged into local and remote `master` at `54068f1`.

- Remove hard-coded `H:\Dropbox (Personal)` interpreter paths.
- Resolve the repository virtual environment relative to the repository root.
- Optionally support an explicit interpreter parameter.
- Check the exit code of each PyInstaller invocation.
- Stop immediately after a failed build.
- Verify expected output files before mirroring or reporting success.
- Update README build and development instructions.

Validation:
- All 35 tests pass on Python 3.11.9, including 18 Windows PowerShell script tests.
- All project PowerShell scripts parse under Windows PowerShell 5.1.
- Real Receiver and Streamer packages build with Python 3.11.9 / PyInstaller 6.20.0
  from a relocated repository copy using the explicit interpreter override.
- Both refreshed packaged applications show responsive windows. Streaming,
  recording, audio controls, and installer execution were not exercised.
- All 946 Receiver and 978 Streamer packaged files match the successful relocated
  build by SHA-256 in both repository `dist` and mirrored `build` folders.
- In-place cleanup encountered filesystem locks in generated output folders and
  stopped explicitly. The lock owner was not identified; no unrelated process was
  stopped. Relocated build outputs were copied back to restore/refresh packages.
- PyInstaller reports unresolved `portcls.sys` dependencies for bundled legacy
  VB-CABLE drivers. Removing/replacing those drivers remains in Phase 4.

### Slice 1B: Receiver-Owned Process Cleanup

**Branch:** `fix/receiver-process-ownership`

- Remove machine-wide `taskkill`/`pkill` by executable name.
- Track and stop only FFmpeg/FFplay processes created by the current Receiver instance.
- Use graceful termination, bounded waits, and per-process forced termination as a fallback.
- Reap child processes and clear references.
- Stop monitoring threads and pending callbacks cleanly.
- Avoid `os._exit` unless a reproduced native shutdown defect requires it.

### Slice 1C: Streamer Process Lifecycle

**Branch:** `fix/streamer-process-lifecycle`

**Status:** Merged into local and remote `master` at `b03383e`. Slice 1B remains pending.

- Model `idle`, `connecting`, `streaming`, `stopping`, and `error` states.
- Detect immediate and later FFmpeg failures.
- Do not show Streaming merely because `Popen` returned.
- Restore controls and show an actionable message after unexpected exit.
- Distinguish normal user-requested stops from failures.
- Ensure output-reader threads stop cleanly.
- After confirmed streaming, report FFmpeg connection-reset exits as a friendly
  "Receiver disconnected" information notice with reconnect instructions, rather
  than a technical failure dialog. Preserve the exit code and diagnostics in the
  log. A reset cannot distinguish intentional Receiver stop from a dropped link.
  Keep startup failures and other FFmpeg errors explicit.

Validation:
- All 63 tests pass on Python 3.11.9, including 28 new lifecycle/UI wiring tests.
- Tests use real isolated Python children for immediate/later exits, nonblocking
  graceful and forced stops, repeated restarts, output decoding, and thread cleanup.
- An unrelated running child is verified to survive a Streamer stop.
- The source GUI was exercised with real FFmpeg synthetic silence to a null
  output: Connecting -> Streaming -> Stopping -> Idle, restored controls, and
  cancelled polling on close. No SetPlayBack, audio-device changes, or Receiver
  network connection was used.
- Streaming is confirmed by positive FFmpeg output-time progress, not process
  creation. This does not independently confirm playback at the Receiver.
- Python 3.11 syntax/static checks pass. Pylance reports no diagnostics in the
  new lifecycle module or test file; its GUI diagnostics still report the known
  unresolved audio imports for the editor-selected environment.
- Both apps were rebuilt for this slice on November 3, 2026 using a relocated
  build because in-place output cleanup hit filesystem locks. The repository
  `dist` and mirrored `build` packages were refreshed and all 946 Receiver /
  978 Streamer files verified against that build by SHA-256. The Streamer EXE
  contains `streamer_lifecycle`, and both packaged windows launch responsively.
  Two-machine user testing confirmed VB-CABLE capture and playback after allowing
  FFplay through the Receiver firewall. Stopping Receiver produced FFmpeg reset
  code -10054 (unsigned 4294957242), prompting the friendly disconnect update.
  That update still requires a repeat two-machine test. Installer executables
  have not been rebuilt for this slice.
- Both test packages were rebuilt again after the friendly disconnect update;
  package hashes and responsive windows were verified. The classifier extracted
  from the compiled Streamer returns the new reconnect message for code 4294957242.

## Phase 2: Settings and Native Menus

### Slice 2A: Shared Settings Infrastructure

**Branch:** `feature/app-settings`

**Status:** Implemented; awaiting review and merge.

- Store per-user settings under `%LOCALAPPDATA%`.
- Validate settings loaded from JSON.
- Save settings atomically.
- Report load/save errors instead of silently discarding them.
- Define shared application-version metadata.
- Preserve or migrate existing saved Receiver addresses.

Implementation and validation:
- Both apps load the shared versioned settings model and log the shared
  application version (`1.0.3`). Settings/log paths honor `LOCALAPPDATA`, with
  the previous home-based path as a fallback.
- Streamer migrates legacy `ip_history.json` without modifying it. Existing new
  settings take precedence, including an intentionally empty saved list.
- Malformed/unreadable settings produce logged and visible errors. Streamer
  blocks saved-connection writes after a load error instead of overwriting data.
- Saves validate input, flush a same-directory temporary file, and atomically
  replace the destination. Save failures preserve the old file and connection UI.
- All 93 tests pass on Python 3.11.9, including 29 settings/migration/UI tests and
  a new LOCALAPPDATA path test. Project Python/spec syntax checks also pass.
- Source Streamer GUI migration, dropdown selection, saved names containing
  colons, persistence, and reload were verified using temporary app data only.
- Pylance diagnostics requests timed out; editor diagnostics remain unverified.
- Menus, Receiver recording behavior, and Receiver process cleanup are unchanged.
  Settings files for Receiver are not written until a future preference is saved.
- Both apps were rebuilt for Slice 2A on November 3, 2026 using a relocated
  build because the existing Dropbox output folders are locked. The `dist` and
  mirrored `build` folders were refreshed. `app_settings` and `audio_common`
  are embedded in both executables, and both packaged windows launch
  responsively. The build reuses the unchanged checked-in specs and runtime
  assets; the package `_internal` folders still have 945 Receiver / 977
  Streamer runtime files. Installers have not been rebuilt.

### Slice 2B: Receiver Menu and Recording Folder

**Branch:** `feature/receiver-menu-recording-folder`

Proposed menu:

```text
File
  Choose Recording Folder...
  Open Recording Folder
  Exit

Options
  Receiver Name...
  Reset Settings

Help
  Open Log Folder
  About Audio Receiver
```

- Default to `%USERPROFILE%\Music\Audio Receiver Recordings` when available.
- Fall back to `%LOCALAPPDATA%\Audio Receiver\Recordings`.
- Use a standard folder picker and remember the selected folder.
- Validate writability before recording; choose a fresh, non-overwriting
  timestamped filename each time recording starts.
- Keep existing schema-version-1 settings valid while persisting the Receiver
  name and recording folder.
- Store Receiver logs in `%LOCALAPPDATA%\Audio Receiver\logs\Audio_Receiver.log`;
  leave any existing root-level log untouched.
- Include version, purpose, settings/recording/log paths, and FFmpeg/Icons8
  credits in About.

### Slice 2C: Streamer Menu

**Branch:** `feature/streamer-menu`

Proposed menu:

```text
File
  Exit

Connections
  Discover Receivers...
  Refresh Discovered Receivers
  Manage Saved Receivers

Options
  Reset Settings

Help
  Open Log Folder
  About Audio Streamer
```

- Preserve prominent Start and Stop controls.
- Preserve manual IP entry and saved connections.
- Keep menu actions and main-window controls synchronized.
- Store Streamer logs in `%LOCALAPPDATA%\Audio Streamer\logs\Audio_Streamer.log`;
  leave any existing root-level log untouched.

## Phase 3: Hybrid Receiver Discovery

### Slice 3A: Discovery Protocol Spike

**Branch:** `spike/receiver-discovery-protocol`

- Compare dependency-free UDP discovery with mDNS/zeroconf.
- Test multiple adapters, VPNs, Windows network profiles, and firewall behavior.
- Define bounded request/response messages with protocol version, request nonce, Receiver name, address, application version, and capabilities.
- Decide IPv4-only versus dual-stack initial support.
- Document malformed-packet, duplicate, timeout, and compatibility behavior.
- Confirm that the approach can operate under a standard user account.

### Slice 3B: Receiver Discovery Responder

**Branch:** `feature/receiver-discovery-service`

- Start a small discovery responder when Receiver launches.
- Stop it cleanly on exit.
- Respond only to valid requests.
- Use the persisted Receiver display name.
- Keep discovery separate from the audio listener.
- Do not require active audio reception for discovery.

### Slice 3C: Streamer Discovery UI

**Branch:** `feature/streamer-receiver-discovery`

- Run discovery outside the Tk UI thread.
- Show bounded progress, Refresh, and Cancel behavior.
- List name, IP address, version, and compatibility.
- Deduplicate responses.
- Merge discovered and saved entries without overwriting user labels.
- Fill the address field after selection but do not automatically start streaming.
- Leave manual entry available when discovery finds nothing or fails.

## Phase 4: Remove VB-CABLE and Admin Requirements

### Slice 4A: Windows Audio Capture Research

**Branch:** `spike/windows-native-audio-capture`

Compare:

- System-wide WASAPI loopback.
- Per-application Windows process loopback.
- A maintained Python capture package.
- A small C#, C++, or Rust helper.
- Verified capabilities of the bundled FFmpeg build.

Measure:

- Windows version support.
- Standard-user operation.
- Driver requirements.
- Latency and dropouts.
- CPU and memory use.
- Default-device changes.
- Packaging complexity.
- Dependency licensing and redistribution.

Do not select an implementation until a standard-user prototype captures real system audio without VB-CABLE.

### Slice 4B: Audio Capture Abstraction

**Branch:** `feature/audio-capture-backend`

- Separate audio acquisition from encoding and network transport.
- Define start, stop, source enumeration, format reporting, and error behavior.
- Temporarily keep VB-CABLE behind a legacy backend.
- Add the selected native backend.
- Test repeated start/stop and device changes.

### Slice 4C: Native System-Audio Capture

**Branch:** `feature/streamer-native-loopback`

- Make native system-output capture the default.
- Add source/device selection when useful.
- Persist the selected capture source.
- Handle device disconnection and default-device changes.
- Preserve acceptable latency and stream stability.

### Slice 4D: Optional Per-Application Capture

**Branch:** `feature/per-application-capture`

Proceed only if the research spike proves it reliable and supportable.

- Enumerate capturable applications.
- Handle process exit and recreation.
- Explain unsupported Windows versions or sources.
- Retain system-wide capture as the fallback.

### Slice 4E: Remove VB-CABLE and Elevation

**Branch:** `cleanup/remove-vb-cable-admin`

- Remove VB-CABLE assets and installation code.
- Remove SetPlayBack and its packaging entries.
- Remove obsolete prompts and driver-related documentation.
- Convert the Streamer installer to a user-level installation.
- Remove unnecessary Streamer inbound firewall rules.
- Test Receiver firewall behavior under a clean standard-user account.
- Verify both applications on a machine that never had VB-CABLE installed.

## Planned Order

```text
0A  Inventory and approve UI/source baselines
0B  Establish approved baseline on master
0C  Test foundation

1A  Build portability
1B  Receiver process ownership
1C  Streamer lifecycle

2A  Shared settings
2B  Receiver menu and recording folder
2C  Streamer menu

3A  Discovery protocol spike
3B  Receiver discovery responder
3C  Streamer discovery UI

4A  Native audio research
4B  Capture abstraction
4C  System-wide native loopback
4D  Per-application capture, if viable
4E  Remove VB-CABLE and elevation
```

## Completion Definition

The overall effort is complete when:

- Both applications retain the approved user experience.
- Builds are portable and fail explicitly.
- Application shutdown never kills unrelated processes.
- Status indicators reflect the actual streaming state.
- Both applications have conventional native menus and About dialogs.
- Recording location is user-selectable and persistent.
- Receiver discovery works while manual addressing remains available.
- Both applications install and run as standard users.
- Streaming works without VB-CABLE or another virtual audio driver.
