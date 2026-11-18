param(
    [string]$TaskName = "MooTrade Auto Paper Scheduler",
    [int]$ValidationDelayMinutes = 0
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Wrapper = Join-Path $Root "backend\scripts\run_auto_paper_schedule.cmd"
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$TodayUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")

$action = New-ScheduledTaskAction `
    -Execute $env:ComSpec `
    -Argument ('/d /c ""{0}""' -f $Wrapper) `
    -WorkingDirectory $Root

# Two UTC triggers cover 09:35 America/New_York in both DST offsets.
# The Python entry point accepts only the trigger whose ET wall clock is due.
$edt = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours(13).AddMinutes(35))
$edt.StartBoundary = "${TodayUtc}T13:35:00Z"
$est = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours(14).AddMinutes(35))
$est.StartBoundary = "${TodayUtc}T14:35:00Z"

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
    -Description "MooTrade AUTO_PAPER execution phase. Submits only inside the 09:35-10:30 ET window, only to the pinned competition paper account, only with an AUTO_PAPER activation pin and a clean kill switch." `
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
