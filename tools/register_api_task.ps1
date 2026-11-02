$ErrorActionPreference = "Stop"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "C:\Users\gabri\Documents\ABEL\tools\run_server.ps1"'
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "ABEL API" -Action $action -Trigger $trigger -Settings $settings -Description "API local do sistema ABEL" -Force
