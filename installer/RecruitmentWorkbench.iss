#define MyAppName "招聘自动化工作台"
#define MyAppVersion "0.9.0-alpha"
#define MyAppPublisher "Recruitment Workbench"
#define MyAppExeName "招聘自动化工作台.exe"

[Setup]
AppId={{E4AE2F53-18DD-4F72-97FA-637F3AAB0D31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\RecruitmentWorkbench
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=招聘自动化工作台-v0.9-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "..\dist\招聘自动化工作台\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 用户数据库、浏览器登录状态和诊断文件位于 LOCALAPPDATA\RecruitmentWorkbench，
; 默认不随卸载删除，避免误删候选人数据。由用户在应用内显式清理。
Type: filesandordirs; Name: "{app}"
