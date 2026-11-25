# ============================================================
#  liuliu-trading-system dashboard -- install / remove autostart
#
#  Three mechanisms, all per-user and admin-free:
#    Task     : scheduled task, ONLOGON trigger (needs Task Scheduler reachable)
#    Run      : HKCU\...\CurrentVersion\Run registry value
#    Startup  : shortcut in the user's Startup folder
#  auto = try Task, then Run, then Startup.
#
#  usage:
#    powershell -ExecutionPolicy Bypass -File .\install-autostart.ps1
#    powershell -ExecutionPolicy Bypass -File .\install-autostart.ps1 -Method Run
#    powershell -ExecutionPolicy Bypass -File .\install-autostart.ps1 -Status
#    powershell -ExecutionPolicy Bypass -File .\install-autostart.ps1 -Uninstall
# ============================================================
[CmdletBinding()]
param(
    [switch]$Uninstall,
    [switch]$Status,
    [ValidateSet('auto', 'Task', 'Run', 'Startup')]
    [string]$Method = 'auto'
)

$ErrorActionPreference = 'Stop'
$TaskName  = 'liuliu-trading-dashboard'
$RunKey    = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$Here      = Split-Path -Parent $MyInvocation.MyCommand.Path
$Vbs       = Join-Path $Here 'run-hidden.vbs'
$Entry     = Join-Path $Here 'start-hidden.cmd'
$StartupDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
$Lnk       = Join-Path $StartupDir "$TaskName.lnk"
$Wscript   = Join-Path $env:SystemRoot 'System32\wscript.exe'
$Command   = "`"$Wscript`" `"$Vbs`""

function Show-Status {
    $found = $false
    try {
        $q = schtasks /Query /TN $TaskName /FO LIST 2>$null
        if ($LASTEXITCODE -eq 0) {
            $found = $true
            Write-Host "[task] $TaskName"
            $q | Where-Object { $_ -match '^(TaskName|Status|Task To Run|Run As User|Next Run Time)' } |
                ForEach-Object { Write-Host "       $_" }
        }
    } catch { }

    $runValue = (Get-ItemProperty -Path $RunKey -Name $TaskName -ErrorAction SilentlyContinue).$TaskName
    if ($runValue) { $found = $true; Write-Host "[run key] $runValue" }

    if (Test-Path $Lnk) { $found = $true; Write-Host "[startup shortcut] $Lnk" }

    if (-not $found) { Write-Host "no autostart installed" }
}

function Get-PortHealth {
    try { return (Invoke-WebRequest 'http://127.0.0.1:8777/api/health' -UseBasicParsing -TimeoutSec 5).StatusCode }
    catch { return 0 }
}

function Install-Task {
    schtasks /Create /F /TN $TaskName /SC ONLOGON /TR "`"$Wscript`" `"$Vbs`"" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[ok] scheduled task created: $TaskName (trigger: at logon)"
        Write-Host "     action: $Command"
        return $true
    }
    Write-Host "[skip] scheduled task not created (exit $LASTEXITCODE) -- Task Scheduler unreachable in this context"
    return $false
}

function Install-Run {
    New-ItemProperty -Path $RunKey -Name $TaskName -Value $Command -PropertyType String -Force | Out-Null
    Write-Host "[ok] registry Run value written: HKCU\...\Run\$TaskName"
    Write-Host "     value: $Command"
    return $true
}

function Install-Startup {
    if (-not (Test-Path $StartupDir)) { throw "startup folder not found: $StartupDir" }
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($Lnk)
    $sc.TargetPath = $Wscript
    $sc.Arguments = "`"$Vbs`""
    $sc.WorkingDirectory = $Here
    $sc.WindowStyle = 7
    $sc.Description = 'liuliu trading dashboard (127.0.0.1:8777)'
    $sc.Save()
    Write-Host "[ok] startup shortcut created: $Lnk"
    return $true
}

function Remove-All {
    $did = $false
    schtasks /Delete /F /TN $TaskName 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $did = $true; Write-Host "[ok] scheduled task deleted" }
    if (Get-ItemProperty -Path $RunKey -Name $TaskName -ErrorAction SilentlyContinue) {
        Remove-ItemProperty -Path $RunKey -Name $TaskName -Force
        $did = $true; Write-Host "[ok] registry Run value removed"
    }
    if (Test-Path $Lnk) { Remove-Item $Lnk -Force; $did = $true; Write-Host "[ok] startup shortcut deleted" }
    if (-not $did) { Write-Host "nothing to remove" }
}

if ($Status)    { Show-Status; exit 0 }
if ($Uninstall) { Remove-All; exit 0 }

if (-not (Test-Path $Vbs))   { Write-Error "missing: $Vbs";   exit 1 }
if (-not (Test-Path $Entry)) { Write-Error "missing: $Entry"; exit 1 }

$done = $false
try {
    switch ($Method) {
        'Task'    { $done = Install-Task }
        'Run'     { $done = Install-Run }
        'Startup' { $done = Install-Startup }
        'auto' {
            if (Install-Task) { $done = $true; break }
            try { if (Install-Run) { $done = $true; break } } catch { Write-Host "[skip] run key denied: $($_.Exception.Message)" }
            try { if (Install-Startup) { $done = $true } } catch { Write-Host "[skip] startup shortcut failed: $($_.Exception.Message)" }
        }
    }
} catch {
    Write-Host "[fail] $($_.Exception.Message)"
}

Write-Host ""
if ($done) {
    Write-Host "Installed. It starts hidden at your next logon."
    Write-Host "Test now without logging off: & '$Wscript' '$Vbs'"
} else {
    Write-Host "Not installed: every mechanism was blocked in this context."
    Write-Host "Run this script yourself in a normal PowerShell window (it needs no admin)."
}
Write-Host "Health now: $(Get-PortHealth) (200 = dashboard already serving)"
Write-Host "Status: powershell -ExecutionPolicy Bypass -File .\install-autostart.ps1 -Status"
Write-Host "Remove: powershell -ExecutionPolicy Bypass -File .\install-autostart.ps1 -Uninstall"
Write-Host "Log:    $Here\logs\dashboard.log  (UTF-8; read with: Get-Content -Encoding UTF8)"
