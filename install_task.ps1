# notice_tap 을 윈도우 작업 스케줄러에 등록합니다.
# 터미널을 켜두지 않아도 정해진 주기마다 백그라운드에서 공지를 확인합니다.
#
#   등록:  powershell -ExecutionPolicy Bypass -File install_task.ps1
#   주기 바꾸기:  ... -File install_task.ps1 -IntervalMinutes 15
#   해제:  ... -File install_task.ps1 -Remove

param(
    [int]$IntervalMinutes = 30,
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$taskName = 'notice_tap'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($Remove) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "작업 '$taskName' 을 해제했습니다."
    } else {
        Write-Host "등록된 작업이 없습니다."
    }
    exit 0
}

$python = (Get-Command pythonw.exe -ErrorAction SilentlyContinue)
if ($null -eq $python) { $python = Get-Command python.exe }

# pythonw 로 실행하면 검은 콘솔 창이 뜨지 않습니다.
$action = New-ScheduledTaskAction -Execute $python.Source `
    -Argument '-m notice_tap check' -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Description 'notice_tap - 공지 게시판 새 글 확인' -Force | Out-Null

Write-Host "작업 '$taskName' 을 등록했습니다. ${IntervalMinutes}분마다 실행됩니다."
Write-Host "확인:  Get-ScheduledTask -TaskName $taskName"
Write-Host "즉시 실행:  Start-ScheduledTask -TaskName $taskName"
