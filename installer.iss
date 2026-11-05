; Inno Setup script - builds QBConnector-Setup.exe
#define AppName "Arcadian QB Connector"
#ifndef AppVersion
  #define AppVersion "1.2.0"
#endif

[Setup]
AppId={{8F3B2C71-4A6D-4E19-B5C2-9D7E0A1F3C55}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Arcadian Cafe
DefaultDirName={autopf}\QBConnector
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\QBConnector.exe
OutputDir=installer
OutputBaseFilename=QBConnector-Setup-{#AppVersion}
SetupIconFile=assets\qbconnector.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; 32-bit app on purpose: QuickBooks 2015 SDK is 32-bit
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\QBConnector\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\QBConnector.exe"
Name: "{group}\{#AppName} (Demo - practice mode)"; Filename: "{app}\QBConnector.exe"; Parameters: "--demo"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\QBConnector.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\QBConnector.exe"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent

; Settings and the posting log are kept in %APPDATA%\ArcadianQBConnector
; and are NOT removed when uninstalling or upgrading.
