; Instalador de Arise Trainer (Inno Setup 6)
#define AppVersion GetEnv("ARISE_VERSION")
#if AppVersion == ""
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8D2F4A61-7C3B-4E9A-B1D5-A215E7124A11}
AppName=Arise Trainer
AppVersion={#AppVersion}
AppPublisher=Arise Trainer
DefaultDirName={localappdata}\Programs\AriseTrainer
DefaultGroupName=Arise Trainer
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=AriseTrainer-Instalador
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\AriseTrainer.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "dist\AriseTrainer\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Arise Trainer"; Filename: "{app}\AriseTrainer.exe"
Name: "{userdesktop}\Arise Trainer"; Filename: "{app}\AriseTrainer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AriseTrainer.exe"; Description: "Abrir Arise Trainer ahora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "reg.exe"; Parameters: "delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v AriseTrainer /f"; Flags: runhidden; RunOnceId: "QuitarInicio"
