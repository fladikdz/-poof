; Inno Setup script for poof — iOS Location Spoofer.
;
; Compile from project root:
;     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" poof.iss
;
; Output: dist\PoofSetup.exe (single-file installer ~150-200 MB).

#define MyAppName "poof"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "poof"
#define MyAppURL "https://example.local/poof"
#define MyAppExeName "poof.exe"
#define MyTunneldExeName "poof-tunneld.exe"

[Setup]
AppId={{8F2E9C6D-3B5A-4E7F-9A1B-2C8D5E7F9A3B}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=
OutputDir=dist
OutputBaseFilename=PoofSetup
SetupIconFile=
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName} {#MyAppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableWelcomePage=no
DisableDirPage=no
DisableReadyPage=no
DisableFinishedPage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\{#MyTunneldExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Main GUI shortcut — normal user mode.
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
; Tunneld shortcut — requires admin. Inno Setup doesn't have a built-in "Run as
; administrator" flag for [Icons] entries, so we set it via a [Code] PostInstall
; hook that flips the .lnk's RunAs flag.
Name: "{group}\{#MyAppName} (start tunneld - admin)"; Filename: "{app}\{#MyTunneldExeName}"; WorkingDir: "{app}"; Comment: "Run this BEFORE the main app if you want iOS 17+ DVT spoofing. Will prompt for admin elevation."
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Offer to launch the GUI right after install.
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove leftover frozen-bundle temp dirs (PyInstaller onefile caches under
; %LOCALAPPDATA%\Temp\_MEI*). User-data in %APPDATA%\poof is intentionally kept
; — that's where their master key + session cert live.
Type: filesandordirs; Name: "{localappdata}\Temp\_MEI*"

[Code]
// Mark the tunneld shortcut as "Run as administrator" by flipping bit 0x20 of
// byte 22 (1-based) of the .lnk file. Inno Setup has no native [Icons] flag
// for this — Microsoft's Shell Link spec calls it the RunAsUser bit of the
// "second extra flags" byte in the header.
procedure SetRunAsAdmin(LnkPath: string);
var
  Buf: AnsiString;
  B: Byte;
begin
  if not FileExists(LnkPath) then Exit;
  if not LoadStringFromFile(LnkPath, Buf) then Exit;
  if Length(Buf) < 22 then Exit;
  B := Ord(Buf[22]);
  if (B and $20) = 0 then
  begin
    Buf[22] := Chr(B or $20);
    SaveStringToFile(LnkPath, Buf, False);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  LnkPath: string;
begin
  if CurStep = ssPostInstall then
  begin
    LnkPath := ExpandConstant('{group}\{#MyAppName} (start tunneld - admin).lnk');
    SetRunAsAdmin(LnkPath);
  end;
end;
