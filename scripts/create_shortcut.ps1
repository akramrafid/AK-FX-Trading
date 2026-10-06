$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$ShortcutPath = Join-Path -Path $DesktopPath -ChildPath "AK Forex Trading Desk.lnk"
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "d:\AK Forex Trading\Launch_Trading_Desk.bat"
$Shortcut.WorkingDirectory = "d:\AK Forex Trading"
$Shortcut.Description = "Launch AK Forex Trading Desk & Live Bridge"
$Shortcut.Save()
Write-Host "Created shortcut: $ShortcutPath"
