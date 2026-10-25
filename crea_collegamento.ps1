# Crea sul Desktop il collegamento "CNV" con l'icona dell'app.
# Rilancialo se sposti la cartella del progetto:
#   powershell -ExecutionPolicy Bypass -File crea_collegamento.ps1

$project = $PSScriptRoot
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "CNV.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $project "run.bat"
$shortcut.WorkingDirectory = $project
$shortcut.IconLocation = (Join-Path $project "app\web\static\cnv.ico") + ",0"
$shortcut.Description = "CNV - Chi Ni Vidimu"
$shortcut.WindowStyle = 7  # finestra ridotta a icona: il browser si apre da solo
$shortcut.Save()

Write-Output "Collegamento creato: $shortcutPath"
