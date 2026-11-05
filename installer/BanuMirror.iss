; Inno Setup script for Banu mirror. Built by scripts\package.py, which passes:
;   AppVersion, StageDir (the finished app folder), OutDir (where Setup.exe goes)

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef StageDir
  #define StageDir "..\build\stage\Banu mirror"
#endif
#ifndef OutDir
  #define OutDir "..\dist"
#endif

#define AppName "Banu mirror"
#define AppExe "Banu mirror.exe"
#define UxPlayExe "{app}\engine\uxplay\uxplay.exe"
; Same name the app uses for its "Allow…" button, so the app sees this rule.
#define FirewallRule "Banu mirror (UxPlay)"

[Setup]
AppId={{6C1E3A2B-6E0F-4B7E-9F43-3B8D7A1C2E55}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=taimurishaq
AppPublisherURL=https://github.com/taimurishaq/banu-mirror
AppSupportURL=https://github.com/taimurishaq/banu-mirror
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Admin is needed to add the firewall rule that lets the iPad connect.
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutDir}
OutputBaseFilename=BanuMirror-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExe}
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; Remove an old rule first (reinstall / update), then allow UxPlay on Private networks.
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#FirewallRule}"""; Flags: runhidden; StatusMsg: "Setting up Windows Firewall..."
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#FirewallRule}"" dir=in action=allow program=""{#UxPlayExe}"" profile=private enable=yes"; Flags: runhidden; StatusMsg: "Setting up Windows Firewall..."
Filename: "{app}\{#AppExe}"; Description: "Open {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#FirewallRule}"""; Flags: runhidden; RunOnceId: "RemoveFirewallRule"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\{#AppName}\gstreamer-registry.bin"
