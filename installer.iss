; Instalador de ASCENSO (Inno Setup 6)
#define AppVersion GetEnv("ASCENSO_VERSION")
#if AppVersion == ""
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6B7E1C52-3F1A-4C7B-9E2D-ASCENSO000001}
AppName=Ascenso
AppVersion={#AppVersion}
AppPublisher=Ascenso
DefaultDirName={localappdata}\Programs\Ascenso
DefaultGroupName=Ascenso
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=Ascenso-Instalador
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\Ascenso.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "dist\Ascenso\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Ascenso"; Filename: "{app}\Ascenso.exe"
Name: "{userdesktop}\Ascenso"; Filename: "{app}\Ascenso.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Ascenso.exe"; Description: "Abrir Ascenso ahora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "reg.exe"; Parameters: "delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v Ascenso /f"; Flags: runhidden; RunOnceId: "QuitarInicio"
