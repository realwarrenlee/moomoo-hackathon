param(
    [string]$TaskName = "MooTrade Read-Only Scheduler",
    [int]$ValidationDelayMinutes = 0
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Wrapper = Join-Path $Root "backend\scripts\run_readonly_schedule.cmd"
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$TodayUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")

$action = New-ScheduledTaskAction `
    -Execute $env:ComSpec `
    -Argument ('/d /c ""{0}""' -f $Wrapper) `
    -WorkingDirectory $Root

# Two UTC triggers cover 16:20 America/New_York in both DST offsets.
# The Python entry point accepts only the trigger whose ET wall clock is due.
$edt = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours(20).AddMinutes(20))
$edt.StartBoundary = "${TodayUtc}T20:20:00Z"
$est = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours(21).AddMinutes(20))
$est.StartBoundary = "${TodayUtc}T21:20:00Z"

$triggers = @($edt, $est)
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
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
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
    -Description "Read-only MooTrade schedule. No order authority. ORDER_WRITES_ENABLED must remain false." `
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
