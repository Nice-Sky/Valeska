; Instalador de Arise Trainer (Inno Setup 6)
; - Si ya está instalado, ofrece ACTUALIZAR en el mismo lugar (se conservan progreso, fotos y ajustes).
; - Cierra la app si está abierta y la vuelve a abrir al terminar.
#define AppVersion GetEnv("ARISE_VERSION")
#if AppVersion == ""
  #define AppVersion "1.0.0"
#endif
#define MyAppId "{{8D2F4A61-7C3B-4E9A-B1D5-A215E7124A11}"

[Setup]
AppId={#MyAppId}
AppName=Arise Trainer
AppVersion={#AppVersion}
AppVerName=Arise Trainer {#AppVersion}
VersionInfoVersion={#AppVersion}
AppPublisher=Arise Trainer
DefaultDirName={localappdata}\Programs\AriseTrainer
DefaultGroupName=Arise Trainer
UsePreviousAppDir=yes
DisableDirPage=auto
DisableProgramGroupPage=yes
DisableWelcomePage=no
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=AriseTrainer-Instalador
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\AriseTrainer.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
AppMutex=AriseTrainerAppMutex

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Check: not IsUpgrade

[Files]
Source: "dist\AriseTrainer\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[InstallDelete]
; limpia archivos de la versión anterior que ya no se usan
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\Arise Trainer"; Filename: "{app}\AriseTrainer.exe"
Name: "{userdesktop}\Arise Trainer"; Filename: "{app}\AriseTrainer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AriseTrainer.exe"; Description: "Abrir Arise Trainer ahora"; Flags: nowait postinstall skipifsilent
Filename: "{app}\AriseTrainer.exe"; Parameters: "--actualizado"; Flags: nowait; Check: WizardSilent and not NoRelaunch

[UninstallRun]
Filename: "reg.exe"; Parameters: "delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v AriseTrainer /f"; Flags: runhidden; RunOnceId: "QuitarInicio"

[Code]
var
  PrevVersion: String;

function GetPrevVersion(): String;
var
  Key: String;
begin
  Result := '';
  Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppId}_is1';
  StringChangeEx(Key, '{{', '{', True);
  if not RegQueryStringValue(HKCU, Key, 'DisplayVersion', Result) then
    RegQueryStringValue(HKLM, Key, 'DisplayVersion', Result);
end;

function NoRelaunch(): Boolean;
var
  i: Integer;
begin
  Result := False;
  for i := 1 to ParamCount do
    if CompareText(ParamStr(i), '/NORELAUNCH') = 0 then
      Result := True;
end;

function IsUpgrade(): Boolean;
begin
  Result := PrevVersion <> '';
end;

function InitializeSetup(): Boolean;
begin
  PrevVersion := GetPrevVersion();
  Result := True;
end;

procedure InitializeWizard();
begin
  if IsUpgrade() then
  begin
    WizardForm.Caption := 'Actualizar Arise Trainer';
    WizardForm.WelcomeLabel1.Caption := 'Actualizar Arise Trainer';
    WizardForm.WelcomeLabel2.Caption :=
      'Ya tenés instalada la versión ' + PrevVersion + '.' + #13#10 + #13#10 +
      'Se va a actualizar a la versión {#AppVersion} en la misma carpeta.' + #13#10 +
      'Tu progreso, fotos y ajustes se conservan.' + #13#10 + #13#10 +
      'Si Arise Trainer está abierto, se va a cerrar y volver a abrir solo.';
  end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  if IsUpgrade() then
    Result := 'Actualización: ' + PrevVersion + '  ->  {#AppVersion}' + NewLine + NewLine + MemoDirInfo
  else
    Result := MemoDirInfo + NewLine + NewLine + MemoTasksInfo;
end;
