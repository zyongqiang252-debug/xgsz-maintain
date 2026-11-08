<#
xgsz-maintain 本地一键启动（Windows 无 Docker 方案）

前置：
  - 便携版 PostgreSQL 16 已解压到 %LOCALAPPDATA%\xgsz-runtime\pgsql
  - 数据目录已 initdb 到 %LOCALAPPDATA%\xgsz-runtime\pgdata（用户 admin / trust）
  - backend\.venv 已装好 requirements-core.txt + greenlet + psycopg[binary]
  - frontend 已 npm install && npm run build

用法：
  powershell -ExecutionPolicy Bypass -File tools\start-local.ps1
#>
$ErrorActionPreference = "Continue"

$Repo = Split-Path -Parent $PSScriptRoot
$Runtime = Join-Path $env:LOCALAPPDATA "xgsz-runtime"
$PgBin = Join-Path $Runtime "pgsql\bin"
$PgData = Join-Path $Runtime "pgdata"
$Backend = Join-Path $Repo "backend"
$Logs = Join-Path $Runtime "logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

function Test-Port($port) {
    try { return (Test-NetConnection -ComputerName 127.0.0.1 -Port $port -WarningAction SilentlyContinue).TcpTestSucceeded } catch { return $false }
}

Write-Host "[1/3] PostgreSQL (15432)..." -ForegroundColor Cyan
if (Test-Port 15432) {
    Write-Host "      已在运行，跳过" -ForegroundColor Green
} else {
    if (-not (Test-Path (Join-Path $PgBin "postgres.exe"))) {
        Write-Host "      未找到 PostgreSQL：$PgBin" -ForegroundColor Red
        Write-Host "      先跑 python tools\fetch_pg.py（或用备份里的 pgsql 目录）" -ForegroundColor Yellow
        return
    }
    & (Join-Path $PgBin "pg_ctl.exe") start -D $PgData `
        -o "-p 15432 -c listen_addresses=localhost" `
        -l (Join-Path $Logs "postgres.log") | Out-Null
    Start-Sleep -Seconds 3
    if (Test-Port 15432) { Write-Host "      已启动" -ForegroundColor Green }
    else { Write-Host "      启动失败，看 $Logs\postgres.log" -ForegroundColor Red }
}

Write-Host "[2/3] Redis (6379，可选)..." -ForegroundColor Cyan
if (Test-Port 6379) {
    Write-Host "      已在运行" -ForegroundColor Green
} else {
    Write-Host "      未运行：缓存与会话降级为进程内存，功能不受影响" -ForegroundColor Yellow
}

Write-Host "[3/3] 后端 (http://127.0.0.1:18080)..." -ForegroundColor Cyan
if (Test-Port 18080) {
    Write-Host "      已在运行，无需重复启动" -ForegroundColor Green
} else {
    $py = Join-Path $Backend ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) {
        Write-Host "      未找到 venv：$py" -ForegroundColor Red
        return
    }
    Start-Process -FilePath $py `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18080" `
        -WorkingDirectory $Backend -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Logs "uvicorn.out.log") `
        -RedirectStandardError (Join-Path $Logs "uvicorn.err.log")
    Start-Sleep -Seconds 10
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:18080/health" -TimeoutSec 15
        Write-Host "      health: $($h.status)" -ForegroundColor Green
    } catch {
        Write-Host "      未就绪，看 $Logs\uvicorn.err.log" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "打开：  http://127.0.0.1:18080" -ForegroundColor White
Write-Host "账号：  admin / admin123" -ForegroundColor White
Write-Host "接口：  http://127.0.0.1:18080/docs" -ForegroundColor White
Write-Host "冒烟：  cd backend; .venv\Scripts\python.exe ..\tools\smoke_test.py" -ForegroundColor DarkGray
