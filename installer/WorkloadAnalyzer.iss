[Setup]
AppName=WorkloadAnalyzer
AppVersion=1.0.0
AppPublisher=WorkloadAnalyzer
DefaultDirName={autopf}\WorkloadAnalyzer
DefaultGroupName=WorkloadAnalyzer
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=WorkloadAnalyzer_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\WorkloadAnalyzer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\WorkloadAnalyzer"; Filename: "{app}\WorkloadAnalyzer.exe"
Name: "{group}\{cm:UninstallProgram,WorkloadAnalyzer}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\WorkloadAnalyzer"; Filename: "{app}\WorkloadAnalyzer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\WorkloadAnalyzer.exe"; Description: "{cm:LaunchProgram,WorkloadAnalyzer}"; Flags: nowait postinstall skipifsilent
