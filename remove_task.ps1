#Requires -Version 5.1
<#
.SYNOPSIS
    Unregister the ScreencapMonitor scheduled task.
.DESCRIPTION
    Removes the task only. config.json, state.json, logs, and organized
    screenshots are preserved.
#>

$task = Get-ScheduledTask -TaskName "ScreencapMonitor" -ErrorAction SilentlyContinue
if ($task) {
    Unregister-ScheduledTask -TaskName "ScreencapMonitor" -Confirm:$false
    Write-Host "Task 'ScreencapMonitor' removed." -ForegroundColor Green
} else {
    Write-Host "Task 'ScreencapMonitor' not found — nothing to remove." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "config.json, state.json, logs, and organized screenshots are preserved."
Write-Host "To re-register the task, run setup.ps1 again."
