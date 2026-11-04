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
- Field test (November 3, 2026): the user could not find a recording in the
  selected `C:\Users\ccattell\Music\Audio Receiver Recordings` folder, although
  the log shows FFmpeg launched with the full timestamped MP3 path in that
  folder and then stopped. The log does not confirm the file's final location;
  investigate output-file existence/location after stopping before considering
  recording-folder behavior verified.
- Receiver logs the selected recording target when recording starts and, when
  FFmpeg exits, logs its exit code and whether the file exists and has data.
- Follow-up test (November 4, 2026): the recording was verified at its logged
  destination, and the user confirmed it plays correctly. The folder picker
  hides files; use Open Recording Folder to inspect recordings. FFmpeg returned
  a nonzero exit code despite a playable output; investigate the stop reason
  and process diagnostics in Slice 2D rather than inferring failure from the
  exit code alone.

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
- Manage saved Receivers from the menu and allow settings reset with confirmation.
- Keep discovery menu entries explicit about availability until Phase 3 implements
  Receiver discovery.
- Store Streamer logs in `%LOCALAPPDATA%\Audio Streamer\logs\Audio_Streamer.log`;
  leave any existing root-level log untouched.
- Include version, purpose, settings/log paths, and third-party credits in About.

### Slice 2D: Logging and Diagnostics for Both Apps

**Branch:** `feature/logging-diagnostics`

- Use Python's standard-library logging; preserve the existing per-app `logs`
  folders and Open Log Folder actions.
- Log application version and relevant settings/resource paths at startup.
- Log connection attempts, confirmed streaming, disconnects, and shutdown.
- Distinguish user-requested stops from unexpected process exits; record the
  reason for stopping without treating every nonzero exit as the same failure.
- Capture FFmpeg/FFplay error output and exit codes without blocking streaming,
  filling unread pipes, or flooding the log with progress messages.
- Include recording destination and output-file existence/size at completion.
  A nonempty file alone does not establish that recording finalized correctly.
- Preserve useful technical details while giving users clear error messages.
  Do not log credentials or other secrets.
- Test successful sessions, user stops, startup failures, unexpected disconnects,
  and recording results in both apps; verify that logs explain what happened.
- Keep discovery and the broader Receiver process-ownership refactor out of
  scope; coordinate any tightly coupled stop-diagnostics changes with Slice 1B.

Implementation and validation (November 4, 2026):

- Implemented startup/session/stop diagnostics in both apps with UTF-8 file
  logging, process IDs, raw and signed exit codes, and bounded stderr summaries.
- Receiver drains FFmpeg/FFplay stderr on reader threads; recording progress
  confirms audio output. Playback-only reports input opened without claiming
  speaker playback. Unexpected process failures are surfaced in the GUI.
- Streamer retains its existing progress confirmation and friendly disconnect
  handling, while logging requested stops and recent process errors without
  per-line progress/error flooding.
- Existing Receiver stop/close mechanics remain pending Slice 1B; nonempty
  recordings with nonzero exit codes are reported as finalization unconfirmed.
- Recorded-file playback also captures FFplay diagnostics and surfaces playback
  failures instead of leaving its error pipe unread.
- All 125 standard-library tests passed. A real bundled-FFmpeg synthetic-silence
  check verified dual output, positive progress, exit code zero, and nonempty
  MP3 output without changing audio devices or using the network.
- Both apps were rebuilt into `dist\Slice 2D Test`; executables, required
  FFmpeg/Tk runtime assets, and embedded diagnostics modules were verified.
  Slice 2C test builds are unchanged.
- User approved the packaged test on November 4, 2026. Receiver logs show
  confirmed recording output, the user-requested stop, output-file size, and
  subsequent recorded-file playback.
- Follow up in Slice 1B: stopping playback during recording produced WAV
  broken-pipe diagnostics, a nonzero recording-process exit, and an unconfirmed
  recording finalization warning. Recorded-file playback also reported
  `invalid new backstep -1`. Graceful recording shutdown remains unresolved;
  the improved logs now expose the evidence rather than hiding these warnings.

## Phase 3: Hybrid Receiver Discovery

### Slice 3A: Discovery Protocol Spike

**Branch:** `spike/receiver-discovery-protocol`

**Status:** Prototype and local validation complete; physical-network validation
remains outstanding before production discovery approval.

- Compare dependency-free UDP discovery with mDNS/zeroconf.
- Test multiple adapters, VPNs, Windows network profiles, and firewall behavior.
- Define bounded request/response messages with protocol version, request nonce, Receiver name, address, application version, and capabilities.
- Decide IPv4-only versus dual-stack initial support.
- Document malformed-packet, duplicate, timeout, and compatibility behavior.
- Confirm that the approach can operate under a standard user account.

#### Spike decision: IPv4 UDP request/reply

Use dependency-free UDP discovery on port **6006**, separate from the existing
TCP audio port **6005**. Keep manual and saved IP addresses as the fallback.
The standalone `discovery_spike.py` prototype is not imported or started by
either app; responder integration and the discovery UI remain Slices 3B/3C.

| Option | Benefits | Costs and limits | Decision |
|---|---|---|---|
| UDP subnet broadcast with unicast replies | Standard library only; explicit on-demand scans; small bounded JSON contract | Custom protocol; broadcasts usually stay on one subnet; adapter selection and firewall access still required | Selected for the initial IPv4-only release |
| mDNS/DNS-SD using python-zeroconf | Standard service discovery with service names, caching, and IPv4/IPv6 support | Adds a dependency and multicast/service lifecycle management; does not bypass network isolation or firewall policy | Revisit if interoperability or IPv6 becomes a requirement |

This is a design comparison, not a measured mDNS performance comparison;
zeroconf was not installed. References:
[mDNS RFC 6762](https://www.rfc-editor.org/rfc/rfc6762),
[python-zeroconf documentation](https://python-zeroconf.readthedocs.io/en/latest/),
and [Windows Firewall rules](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/rules).

#### Version 1 wire contract

- UTF-8 JSON datagrams, maximum **1024 bytes** including all fields.
- Query fields, all required: `protocol="audio-streamer-discovery"`, integer
  `version=1`, `type="query"`, and `nonce` (32 lowercase hex characters from
  a fresh random 128-bit value per scan).
- Response fields, all required: the same protocol/version/nonce,
  `type="receiver"`, `name` (1-64 characters; no control characters),
  `address` (unicast IPv4), `app_version` (1-32 printable ASCII characters),
  integer `audio_port=6005`, and `capabilities=["tcp-mpegts-mp3-v1"]`.
- Validate every packet before displaying a result or replying. Reject invalid
  encoding/JSON, oversized messages, wrong field sets/types, unknown protocol
  versions, mismatched/stale nonces, and mismatched advertised/source IPs.
  Responses must originate from the discovery port.
- Recognized version-1 responses with unknown capabilities or another valid
  audio port may be listed as incompatible; do not enable streaming to them.
  Application version is informational, not a strict equality requirement.
- Treat discovery as an unauthenticated hint, not proof of identity. The nonce
  correlates responses but does not authenticate a Receiver. Never automatically
  connect, change saved labels, or trust a peer-supplied path/command.

#### Scan, adapter, and failure behavior

- Send one query from each explicitly selected local IPv4/prefix to that
  interface's directed broadcast address; use separate bound sockets.
  Prototype selection is explicit so it never probes a VPN adapter by default.
  Automatic adapter enumeration/profile filtering is an integration requirement.
- Default scan window **2 seconds**, hard configurable maximum **5 seconds**;
  check cancellation at intervals of at most 100 ms while waiting. No background
  announcements or continuous scanning. Refresh starts a new scan and nonce;
  packet loss may require Refresh rather than automatic retries.
- Maximum 8 selected interfaces, 64 distinct results, and 256 received packets
  per scan. Deduplicate by source IPv4/audio port; first valid response wins.
  One physical Receiver on two interfaces may appear twice because v1 has no
  persistent device identifier. Sort by display name/address.
- Responder handles at most 32 datagrams per second globally, including malformed
  traffic. It only replies to valid requests and never writes peer data into
  settings. Prototype responder runs for at most 60 seconds via the CLI.
- Empty results mean no valid replies in the scan window, not "firewall blocked"
  or "no Receiver exists." Propagate socket/bind errors explicitly and release
  owned sockets. Keep manual entry usable when discovery fails.
- VPNs, client-isolated Wi-Fi, routed subnets, and blocked broadcasts may prevent
  discovery even when manual TCP streaming works. IPv6 discovery is deferred;
  it requires multicast rather than this IPv4 broadcast design.

#### Windows privileges, firewall, and validation

- Creating and using the UDP sockets worked with a non-elevated token on this
  machine. Separate CLI processes exchanged a valid, compatible response on
  loopback UDP 6006 with no audio listener. A directed broadcast on the active
  Private Ethernet interface also found the same-host wildcard-bound responder.
  Both processes exited cleanly. These prove local operation, not inbound
  reachability from a second machine.
- Windows Firewall was enabled for all three profiles; the only active physical
  adapter was Ethernet on a Private network. No VPN or second physical adapter
  was available. No firewall rules, adapter settings, or profiles were changed.
- A standard user cannot be promised permission to add an inbound firewall
  exception. For production, an administrator-managed **Private-profile,
  local-subnet UDP 6006** Receiver exception may be needed. Permit the Receiver
  executable, not ffmpeg.exe: discovery belongs to the app process. Domain policy
  may prevent local exceptions. Do not silently elevate or enable Public access.
- Verified with tests: packet bounds/validation, Unicode names, version and
  capability compatibility, stale/spoofed-address rejection, deduplication,
  bounded timeouts/results/packet counts, responder rate limiting, cancellation,
  socket cleanup, and real loopback UDP discovery with no audio listener.
- The full suite passes **141 tests**, including 16 discovery tests. A
  multi-interface malformed/oversized-packet regression exposed a scan reading
  258 packets instead of the promised 256; the receive limit now applies before
  every read, including rejected packets.
- Two simultaneous loopback addresses exercise multiple socket/interface paths;
  directed-broadcast calculations and selected-interface binding are tested with
  mocks. These are not substitutes for two physical network adapters.
- Still requiring field tests before production discovery approval: two-machine
  broadcast/unicast replies, concurrent Ethernet/Wi-Fi, connected/disconnected
  VPN, Public/Domain profiles, explicit allow/block firewall rules, and managed
  standard-user firewall policy. Record actual outcomes rather than treating an
  empty scan as a diagnosis.

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
2D  Logging and diagnostics for both apps

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
