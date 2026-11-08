<#
改完 backend\.env 后重启后端（.env 只在启动时读取一次，不重启不生效）

用法（在 PowerShell 窗口里执行）：
  powershell -ExecutionPolicy Bypass -File tools\restart-backend.ps1
#>
$ErrorActionPreference = "Continue"

$Repo = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Repo "backend"
$Logs = Join-Path $env:LOCALAPPDATA "xgsz-runtime\logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

# 1) 找到并停止旧的 uvicorn（用命令行匹配，比查端口可靠）
Write-Host "[1/2] 查找旧后端进程..." -ForegroundColor Cyan
$old = @()
try {
    $old = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction Stop |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'app\.main' }
} catch {
    Write-Host "      查询进程失败（可能权限不足），跳过停止步骤" -ForegroundColor Yellow
}
if ($old) {
    foreach ($p in $old) {
        Write-Host "      停止 PID=$($p.ProcessId)" -ForegroundColor DarkGray
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 3
} else {
    Write-Host "      没有在跑的后端" -ForegroundColor DarkGray
}

# 2) 启动
$py = Join-Path $Backend ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "找不到 venv：$py" -ForegroundColor Red
    return
}
Write-Host "[2/2] 启动后端..." -ForegroundColor Cyan
Start-Process -FilePath $py `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18080" `
    -WorkingDirectory $Backend -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Logs "uvicorn.out.log") `
    -RedirectStandardError (Join-Path $Logs "uvicorn.err.log")

$ok = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 2
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:18080/health" -TimeoutSec 5
        Write-Host "      健康：$($h.status)" -ForegroundColor Green
        $ok = $true
        break
    } catch { }
}
if ($ok) {
    Write-Host ""
    Write-Host "打开：http://127.0.0.1:18080   账号：admin / admin123" -ForegroundColor White
} else {
    Write-Host "      起不来，看日志：$Logs\uvicorn.err.log" -ForegroundColor Yellow
}
