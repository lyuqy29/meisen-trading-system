# 梅森交易体系 · skill 安装器（Windows PowerShell）
# 用法:
#   powershell -ExecutionPolicy Bypass -File .\install-skill.ps1
#   powershell -ExecutionPolicy Bypass -File .\install-skill.ps1 -Project
#   powershell -ExecutionPolicy Bypass -File .\install-skill.ps1 -Force
param(
    [switch]$Project,
    [switch]$Force
)

$Name = "meisen-trading-system"
$Src = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($Project) {
    $Dest = Join-Path (Get-Location) ".dsh\skills\$Name"
} else {
    $Base = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
    $Dest = Join-Path $Base "skills\$Name"
}

if ((Test-Path $Dest) -and (-not $Force)) {
    Write-Host "目标已存在: $Dest"
    Write-Host "使用 -Force 覆盖。"
    exit 1
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Dest) | Out-Null
if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
Copy-Item -Recurse $Src $Dest
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $Dest "install-skill.sh"), (Join-Path $Dest "install-skill.ps1")

Write-Host "已安装到: $Dest"
Write-Host "在 DSH 中重启会话即可看到 $Name。"
