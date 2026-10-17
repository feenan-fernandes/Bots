$WshShell = New-Object -ComObject WScript.Shell
$TargetDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. Trading Platform Shortcut (The Main Trading Interface)
$TradingBat = Join-Path $TargetDir "Launch_Trading_Platform.bat"

# Root workspace
$TradeRootShortcut = Join-Path $TargetDir "Ouroboros_Trading_Platform.lnk"
$Shortcut1 = $WshShell.CreateShortcut($TradeRootShortcut)
$Shortcut1.TargetPath = $TradingBat
$Shortcut1.WorkingDirectory = $TargetDir
$Shortcut1.Description = "Ouroboros 3.2 Bento Grid 2.0 Trading Platform"
$Shortcut1.Save()
Write-Host "Created: $TradeRootShortcut"

# Desktop
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$TradeDesktopShortcut = Join-Path $DesktopPath "Ouroboros_Trading_Platform.lnk"
$Shortcut2 = $WshShell.CreateShortcut($TradeDesktopShortcut)
$Shortcut2.TargetPath = $TradingBat
$Shortcut2.WorkingDirectory = $TargetDir
$Shortcut2.Description = "Ouroboros 3.2 Bento Grid 2.0 Trading Platform"
$Shortcut2.Save()
Write-Host "Created Desktop: $TradeDesktopShortcut"

# 2. Control Center Shortcut (System Management / Diagnostics)
$ExePath = Join-Path $TargetDir "dist\Ouroboros_Control_Center\Ouroboros_Control_Center.exe"

$CtrlRootShortcut = Join-Path $TargetDir "Ouroboros_Control_Center.lnk"
$Shortcut3 = $WshShell.CreateShortcut($CtrlRootShortcut)
$Shortcut3.TargetPath = $ExePath
$Shortcut3.WorkingDirectory = $TargetDir
$Shortcut3.Description = "Ouroboros 3.2 Institutional Quant Control Center"
$Shortcut3.Save()
Write-Host "Created: $CtrlRootShortcut"

$CtrlDesktopShortcut = Join-Path $DesktopPath "Ouroboros_Control_Center.lnk"
$Shortcut4 = $WshShell.CreateShortcut($CtrlDesktopShortcut)
$Shortcut4.TargetPath = $ExePath
$Shortcut4.WorkingDirectory = $TargetDir
$Shortcut4.Description = "Ouroboros 3.2 Institutional Quant Control Center"
$Shortcut4.Save()
Write-Host "Created Desktop: $CtrlDesktopShortcut"
