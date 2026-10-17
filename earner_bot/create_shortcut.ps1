$WshShell = New-Object -ComObject WScript.Shell
$TargetDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Target the standalone compiled .exe
$ExePath = Join-Path $TargetDir "dist\Ouroboros_Control_Center\Ouroboros_Control_Center.exe"

# Create shortcut in root workspace
$ShortcutPath = Join-Path $TargetDir "Ouroboros_Control_Center.lnk"
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $ExePath
$Shortcut.WorkingDirectory = $TargetDir
$Shortcut.Description = "Ouroboros 3.2 Institutional Quant Control Center"
$Shortcut.IconLocation = "$ExePath,0"
$Shortcut.Save()
Write-Host "Created root shortcut: $ShortcutPath -> $ExePath"

# Also create desktop shortcut if desired
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$DesktopShortcutPath = Join-Path $DesktopPath "Ouroboros_Control_Center.lnk"
$DesktopShortcut = $WshShell.CreateShortcut($DesktopShortcutPath)
$DesktopShortcut.TargetPath = $ExePath
$DesktopShortcut.WorkingDirectory = $TargetDir
$DesktopShortcut.Description = "Ouroboros 3.2 Institutional Quant Control Center"
$DesktopShortcut.IconLocation = "$ExePath,0"
$DesktopShortcut.Save()
Write-Host "Created desktop shortcut: $DesktopShortcutPath -> $ExePath"
