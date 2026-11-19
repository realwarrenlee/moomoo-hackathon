param(
    [string]$TaskName = "MooTrade Risk Monitor",
    [int]$ValidationDelayMinutes = 0
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Wrapper = Join-Path $Root "backend\scripts\run_risk_monitor.cmd"
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$TodayUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")

$action = New-ScheduledTaskAction `
    -Execute $env:ComSpec `
    -Argument ('/d /c ""{0}""' -f $Wrapper) `
    -WorkingDirectory $Root

# Two UTC triggers per window cover both US DST offsets. The Python entry
# point selects the due window from the America/New_York wall clock and
# skips triggers whose window is not due.
# 09:45 ET reconcile, 12:00 ET midday, 15:45 ET pre-close.
$edtReconcile = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours(13).AddMinutes(45))
$edtReconcile.StartBoundary = "${TodayUtc}T13:45:00Z"
$estReconcile = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours(14).AddMinutes(45))
$estReconcile.StartBoundary = "${TodayUtc}T14:45:00Z"
$edtMidday = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours(16).AddMinutes(0))
$edtMidday.StartBoundary = "${TodayUtc}T16:00:00Z"
$estMidday = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours(17).AddMinutes(0))
$estMidday.StartBoundary = "${TodayUtc}T17:00:00Z"
$edtPreClose = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours(19).AddMinutes(45))
$edtPreClose.StartBoundary = "${TodayUtc}T19:45:00Z"
$estPreClose = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours(20).AddMinutes(45))
$estPreClose.StartBoundary = "${TodayUtc}T20:45:00Z"

$triggers = @($edtReconcile, $estReconcile, $edtMidday, $estMidday, $edtPreClose, $estPreClose)
if ($ValidationDelayMinutes -gt 0) {
    $validation = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes($ValidationDelayMinutes))
    $triggers += $validation
}

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -DontStopOnIdleEnd `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartInterval (New-TimeSpan -Minutes 15) `
    -RestartCount 2

$principal = New-ScheduledTaskPrincipal `
    -UserId $User `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $triggers `
    -Settings $settings `
    -Principal $principal `
    -Description "MooTrade daily risk monitor. Read-only broker checks at 09:45 (reconcile), 12:00 (midday) and 15:45 (pre-close) ET. Never submits, cancels or liquidates; engages the persistent kill switch on the daily-drawdown threshold and unresolved ambiguous submissions." `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
[pscustomobject]@{
    TaskName = $task.TaskName
    State = $task.State
    UserId = $task.Principal.UserId
    LogonType = $task.Principal.LogonType
    WakeToRun = $task.Settings.WakeToRun
    StartWhenAvailable = $task.Settings.StartWhenAvailable
    MultipleInstances = $task.Settings.MultipleInstances
    NextRunTime = $info.NextRunTime
    LastRunTime = $info.LastRunTime
    LastTaskResult = $info.LastTaskResult
} | Format-List

$task.Triggers | Select-Object StartBoundary, Enabled | Format-Table -AutoSize
