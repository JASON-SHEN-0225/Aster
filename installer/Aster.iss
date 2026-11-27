; ============================================================================
;  Aster · 星流 2.0 —— Windows 安装包（Inno Setup 6）
;
;  构建：ISCC.exe installer\Aster.iss
;  产物：installer\dist\Aster-Setup-3.0.0.exe
;
;  设计要点：
;   * 固定 AppId，覆盖升级并保留 %APPDATA%\Aster 与 Downloads\Aster
;   * 安装/卸载均要求管理员权限（写 Program Files + 防火墙规则）
;   * 不写任何开机自启项（由 Aster 设置页自己管理）
;   * 无代码签名，不伪造签名；SmartScreen 提示属预期
; ============================================================================

#define MyAppName "Aster · 星流"
#ifndef MyAppVersion
  #define MyAppVersion "3.0.0"
#endif
#define MyAppPublisher "Aster"
#define MyAppURL "https://github.com/JASON-SHEN-0225/Aster"
#define MyAppExeName "Aster.exe"
#define MyAppId "{{6D3F0B21-9C4A-4E7B-8F52-1A9D3C6B7E40}"
#define ProjectRoot ".."

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\Aster
DefaultGroupName=Aster
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=admin
OutputDir=dist
OutputBaseFilename=Aster-Setup-{#MyAppVersion}
SetupIconFile={#ProjectRoot}\assets\aster.ico
UninstallDisplayIcon={app}\Aster.exe
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll
RestartApplications=no
AllowNoIcons=no
UsePreviousAppDir=yes
; 提权不换用户；部分机器桌面目录被重定向，{userdesktop} 仍可正常解析
UsedUserAreasWarning=no
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} {#MyAppVersion} 安装程序
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCopyright=MIT License

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式(&D)"; GroupDescription: "附加任务："

[Registry]
; 文件与文件夹的“发送到 Aster”右键菜单（当前用户，无需额外管理员）
Root: HKCU; Subkey: "Software\Classes\*\shell\AsterSend"; ValueType: string; ValueName: "MUIVerb"; ValueData: "发送到 Aster"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\*\shell\AsterSend"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\*\shell\AsterSend"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\*\shell\AsterSend\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" --enqueue ""%1"""; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\AsterSend"; ValueType: string; ValueName: "MUIVerb"; ValueData: "发送到 Aster"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\AsterSend"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\AsterSend"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\AsterSend\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" --enqueue ""%1"""; Flags: uninsdeletekey

[Files]
; 安装包只包含程序本体：单个 Aster.exe（图标、网页资源已内置在 exe 中）
Source: "{#ProjectRoot}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; 从旧版升级时清掉历史遗留（文档/截图、CLI、启动脚本、README/LICENSE）；
; 用户数据在 %APPDATA%\Aster 与 Downloads\Aster，绝不在此删除
Type: filesandordirs; Name: "{app}\docs"
Type: filesandordirs; Name: "{app}\assets"
Type: files; Name: "{app}\AsterCLI.exe"
Type: files; Name: "{app}\aster.bat"
Type: files; Name: "{app}\start-cli.bat"
Type: files; Name: "{app}\start-web.bat"
Type: files; Name: "{app}\install-firewall.bat"
Type: files; Name: "{app}\启动网页接收.bat"
Type: files; Name: "{app}\安装防火墙.bat"
Type: files; Name: "{app}\start-aster.bat"
Type: files; Name: "{app}\启动 Aster.bat"
Type: files; Name: "{app}\LICENSE"
Type: files; Name: "{app}\README.md"

[Icons]
Name: "{group}\Aster";          Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Comment: "Aster · 星流 图形界面"
Name: "{userdesktop}\Aster";    Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Comment: "Aster · 星流"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 Aster"; Flags: nowait postinstall skipifsilent

[Code]
const
  FwRuleTcp   = 'Aster TCP 47820';
  FwRuleUdp   = 'Aster UDP 47820';
  FwRuleHttps = 'Aster TCP 47821';

var
  FirewallError: String;

{ --------------------------------------------------------------------------
  通用工具
  -------------------------------------------------------------------------- }

function RunAndWait(const FileName, Params: String): Integer;
var
  ResultCode: Integer;
begin
  ResultCode := -1;
  try
    Exec(FileName, Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
    ResultCode := -1;
  end;
  Result := ResultCode;
end;

function TaskkillImage(const ImageName: String): Boolean;
begin
  { /T 连子进程一起结束；进程不存在时 taskkill 返回非 0，忽略即可 }
  RunAndWait(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM ' + ImageName);
  Result := True;
end;

procedure KillAsterProcesses();
begin
  TaskkillImage('{#MyAppExeName}');
  Sleep(700);
end;

function HasCommandLineParam(const ParamName: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), ParamName) = 0 then
    begin
      Result := True;
      Exit;
    end;
end;

{ --------------------------------------------------------------------------
  防火墙：只增删 Aster 自己命名的三条入站规则
  -------------------------------------------------------------------------- }

function NetshFirewall(const Params: String): Integer;
begin
  Result := RunAndWait(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall ' + Params);
end;

procedure AddFirewallRule(const RuleName, Protocol, Port: String);
var
  Cmd: String;
begin
  { 先删后加：升级安装或重复执行都不会产生重复规则 }
  NetshFirewall('delete rule name="' + RuleName + '"');
  Cmd := 'add rule name="' + RuleName + '" dir=in action=allow protocol=' + Protocol +
         ' localport=' + Port + ' profile=private,domain enable=yes';
  if NetshFirewall(Cmd) <> 0 then
    FirewallError := FirewallError + RuleName + ' ';
end;

procedure AddFirewallRules();
begin
  FirewallError := '';
  AddFirewallRule(FwRuleTcp,   'TCP', '47820');
  AddFirewallRule(FwRuleUdp,   'UDP', '47820');
  AddFirewallRule(FwRuleHttps, 'TCP', '47821');
end;

procedure RemoveFirewallRules();
begin
  { 卸载只删除上面这三条 Aster 自己的规则，不动其它程序或用户手动添加的规则 }
  NetshFirewall('delete rule name="' + FwRuleTcp + '"');
  NetshFirewall('delete rule name="' + FwRuleUdp + '"');
  NetshFirewall('delete rule name="' + FwRuleHttps + '"');
end;

{ --------------------------------------------------------------------------
  用户数据（%APPDATA%\Aster）：默认保留，卸载时可选删除
  -------------------------------------------------------------------------- }

function UserDataDir(): String;
begin
  Result := ExpandConstant('{userappdata}\Aster');
end;

function ShouldDeleteUserData(): Boolean;
begin
  { 静默卸载 / 带 /PURGEDATA 时不弹窗；否则默认「否」 }
  if HasCommandLineParam('/PURGEDATA') then
  begin
    Result := True;
    Exit;
  end;
  if UninstallSilent then
  begin
    Result := False;
    Exit;
  end;
  Result := MsgBox('是否同时删除 Aster 的配置、历史和证书？' + #13#10 + #13#10 +
                   '位置：' + UserDataDir() + #13#10 + #13#10 +
                   '选择「否」将保留这些数据，方便以后重装继续使用。' + #13#10 +
                   'Downloads\Aster 里的接收文件不会被删除。',
                   mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
end;

procedure DeleteUserData();
var
  DataDir: String;
begin
  DataDir := UserDataDir();
  if DirExists(DataDir) then
    DelTree(DataDir, True, True, True);
end;

{ --------------------------------------------------------------------------
  安装流程
  -------------------------------------------------------------------------- }

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    { CloseApplications 之外再兜底一次：确保 Aster.exe 被关闭 }
    KillAsterProcesses();
  end
  else if CurStep = ssPostInstall then
  begin
    AddFirewallRules();
    if FirewallError <> '' then
      MsgBox('以下防火墙规则未能添加：' + FirewallError + #13#10 + #13#10 +
             '手机可能无法访问 Aster。请打开 Aster 设置 → 配置 Windows 防火墙 重试。',
             mbInformation, MB_OK);
  end;
end;

{ --------------------------------------------------------------------------
  卸载流程
  -------------------------------------------------------------------------- }

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    KillAsterProcesses();
    RemoveFirewallRules();
    if ShouldDeleteUserData() then
      DeleteUserData();
  end;
end;

function InitializeUninstall(): Boolean;
begin
  { 卸载器同样需要管理员权限来删除防火墙规则；缺失时提示但仍继续 }
  if not IsAdmin then
    MsgBox('未以管理员身份运行卸载程序，防火墙规则可能无法删除。', mbInformation, MB_OK);
  Result := True;
end;
