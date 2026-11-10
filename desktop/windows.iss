#define AppVersion GetEnv('KEMOMICHI_BUILD_VERSION')
[Setup]
AppId={{53D0CC26-0CE9-44AA-A4CF-4FD3C19AACAE}
AppName=KemoMichi
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\KemoMichi
DefaultGroupName=KemoMichi
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installers
OutputBaseFilename=KemoMichi-Windows-x86_64-setup
SetupIconFile=..\build\desktop-resources\KemoMichi.ico
UninstallDisplayIcon={app}\KemoMichi.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "..\dist\KemoMichi\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\KemoMichi"; Filename: "{app}\KemoMichi.exe"
Name: "{autodesktop}\KemoMichi"; Filename: "{app}\KemoMichi.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\KemoMichi.exe"; Description: "KemoMichi"; Flags: nowait postinstall skipifsilent
