; ═══════════════════════════════════════════════════
; UV Dashboard 2.0 — Inno Setup 安装包脚本
;
; 使用方法：
;   1. 下载安装 Inno Setup: https://jrsoftware.org/isdl.php
;   2. 打开此 .iss 文件
;   3. 编译（Ctrl+F9）即可生成 .exe 安装包
; ═══════════════════════════════════════════════════

[Setup]
AppName=UV Dashboard 2.0
AppVersion=2.0.0
AppPublisher=雪球素养
AppPublisherURL=https://github.com/uv-dashboard
DefaultDirName={autopf}\UV Dashboard 2.0
DefaultGroupName=UV Dashboard 2.0
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=UV-Dashboard-2.0-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
SetupIconFile=build_assets\build_assets\AppIcon.ico
UninstallDisplayIcon={app}\UV Dashboard 2.0.exe
WizardStyle=modern

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"; Flags: checkedonce

[Files]
; 打包整个 dist\UV Dashboard 2.0\ 目录
Source: "dist\UV Dashboard 2.0\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\UV Dashboard 2.0"; Filename: "{app}\UV Dashboard 2.0.exe"
Name: "{group}\卸载 UV Dashboard 2.0"; Filename: "{uninstallexe}"
Name: "{autodesktop}\UV Dashboard 2.0"; Filename: "{app}\UV Dashboard 2.0.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\UV Dashboard 2.0.exe"; Description: "立即启动 UV Dashboard 2.0"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载时不删用户数据（%APPDATA%\UV Dashboard 2.0\）
; 如需彻底清理，用户手动删除该目录
