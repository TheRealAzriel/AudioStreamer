#define MyAppName "Audio Streamer"
#define MyAppExeName "Audio Streamer.exe"
#define InboundRuleName "Audio Streamer TCP 6005"
#define ProgramRuleName "Audio Streamer Program"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8D698307-8E57-4D0D-BA6F-FB5F5680FC13}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher=Audio Streamer Programs
DefaultDirName={autopf}\Audio Streamer
DefaultGroupName=Audio Streamer
DisableProgramGroupPage=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline
OutputDir=..\installer-output
OutputBaseFilename=AudioStreamerSetup-{#AppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "installvbcable"; Description: "Install VB-CABLE audio driver (required for streaming)"; GroupDescription: "System setup:"; Flags: checkedonce

[Files]
Source: "..\dist\Audio Streamer\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Audio Streamer\Audio Streamer"; Filename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\Audio Streamer\Uninstall Audio Streamer"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Audio Streamer"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\_internal\VBCABLE_Driver_Pack43\VBCABLE_Setup_x64.exe"; Description: "Install VB-CABLE (x64)"; Flags: waituntilterminated skipifsilent; Tasks: installvbcable; Check: IsWin64
Filename: "{app}\_internal\VBCABLE_Driver_Pack43\VBCABLE_Setup.exe"; Description: "Install VB-CABLE (x86)"; Flags: waituntilterminated skipifsilent; Tasks: installvbcable; Check: not IsWin64
Filename: "{cmd}"; Parameters: "/C netsh advfirewall firewall add rule name=""{#InboundRuleName}"" dir=in action=allow protocol=TCP localport=6005"; Flags: runhidden waituntilterminated
Filename: "{cmd}"; Parameters: "/C netsh advfirewall firewall add rule name=""{#ProgramRuleName}"" dir=in action=allow program=""{app}\{#MyAppExeName}"" enable=yes"; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Audio Streamer"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C netsh advfirewall firewall delete rule name=""{#InboundRuleName}"""; Flags: runhidden waituntilterminated
Filename: "{cmd}"; Parameters: "/C netsh advfirewall firewall delete rule name=""{#ProgramRuleName}"""; Flags: runhidden waituntilterminated

[Code]
var
  RequirementsPage: TWizardPage;
  RequirementsText: TNewStaticText;

procedure InitializeWizard;
begin
  RequirementsPage := CreateCustomPage(
    wpWelcome,
    'System Setup Notice',
    'Audio Streamer requires elevated system setup'
  );

  RequirementsText := TNewStaticText.Create(RequirementsPage.Surface);
  RequirementsText.Parent := RequirementsPage.Surface;
  RequirementsText.Left := ScaleX(0);
  RequirementsText.Top := ScaleY(0);
  RequirementsText.Width := RequirementsPage.SurfaceWidth;
  RequirementsText.Height := ScaleY(180);
  RequirementsText.WordWrap := True;
  RequirementsText.Caption :=
    'During installation, setup will perform system-level actions:' + #13#10 +
    '- Install VB-CABLE virtual audio driver (required for streaming).' + #13#10 +
    '- Add Windows Firewall allow rules for Audio Streamer and TCP port 6005.' + #13#10 + #13#10 +
    'These actions require administrator permissions and happen once at install time.' + #13#10 +
    'After setup, Audio Streamer runs normally without recurring UAC prompts.';
end;
