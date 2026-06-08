#define MyAppName "Audio Receiver"
#define MyAppExeName "Audio Receiver.exe"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{C67A7A5E-1BFD-4B7E-9F94-8E1B3CFB7F11}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher=Audio Streamer Programs
DefaultDirName={localappdata}\Audio Receiver
DefaultGroupName=Audio Receiver
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\installer-output
OutputBaseFilename=AudioReceiverSetup-{#AppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\Audio Receiver\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Audio Receiver\Audio Receiver"; Filename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\Audio Receiver\Uninstall Audio Receiver"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Audio Receiver"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Audio Receiver"; Flags: nowait postinstall skipifsilent

[Code]
var
  ReceiverInfoPage: TWizardPage;
  ReceiverInfoText: TNewStaticText;

procedure InitializeWizard;
begin
  ReceiverInfoPage := CreateCustomPage(
    wpWelcome,
    'Installation Mode',
    'Audio Receiver installs without administrator rights'
  );

  ReceiverInfoText := TNewStaticText.Create(ReceiverInfoPage.Surface);
  ReceiverInfoText.Parent := ReceiverInfoPage.Surface;
  ReceiverInfoText.Left := ScaleX(0);
  ReceiverInfoText.Top := ScaleY(0);
  ReceiverInfoText.Width := ReceiverInfoPage.SurfaceWidth;
  ReceiverInfoText.Height := ScaleY(170);
  ReceiverInfoText.WordWrap := True;
  ReceiverInfoText.Caption :=
    'This installer runs as a standard user and does not make system-level changes.' + #13#10 + #13#10 +
    'Setup will:' + #13#10 +
    '- Install Audio Receiver in your user profile.' + #13#10 +
    '- Add Start Menu shortcut(s) for Windows Search.' + #13#10 +
    '- Optionally add a desktop shortcut.';
end;
