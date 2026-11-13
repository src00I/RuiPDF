; Inno Setup 脚本：把 dist\RuiPDF\ 做成安装包 dist\RuiPDF-Setup.exe。用法见 build_exe.bat。
; 装到当前用户自己的目录（不需要管理员权限），带开始菜单和可选的桌面快捷方式，
; 并登记"用 RuiPDF 打开"PDF（只是加进"打开方式"列表，不抢默认程序）。
; 这个文件要存成带 BOM 的 UTF-8，否则里面的中文在安装界面上会乱码。

#define AppName "RuiPDF"
#define AppVersion "1.0.0"
#define AppPublisher "Ruicheng Shi"

[Setup]
AppId={{6E0B4C1E-7C55-4E0B-9D3A-52F0A1C7B8D1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\RuiPDF
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=RuiPDF-Setup
SetupIconFile=ruipdf\assets\icon.ico
UninstallDisplayIcon={app}\RuiPDF.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut / 创建桌面快捷方式"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\RuiPDF\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; 许可证和第三方组件声明跟着程序一起装（AGPL / LGPL 要求分发时带上）
Source: "LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\RuiPDF"; Filename: "{app}\RuiPDF.exe"; AppUserModelID: "RuichengShi.RuiPDF"
Name: "{userdesktop}\RuiPDF"; Filename: "{app}\RuiPDF.exe"; Tasks: desktopicon; AppUserModelID: "RuichengShi.RuiPDF"

[Registry]
; 出现在 PDF 文件右键"打开方式"里
Root: HKCU; Subkey: "Software\Classes\Applications\RuiPDF.exe"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Applications\RuiPDF.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "RuiPDF"
Root: HKCU; Subkey: "Software\Classes\Applications\RuiPDF.exe\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\Applications\RuiPDF.exe\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\RuiPDF.exe"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\.pdf\OpenWithList\RuiPDF.exe"; Flags: uninsdeletekey

[Run]
Filename: "{app}\RuiPDF.exe"; Description: "Launch RuiPDF / 启动 RuiPDF"; Flags: nowait postinstall skipifsilent
