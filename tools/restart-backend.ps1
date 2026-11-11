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
$outLog = Join-Path $Logs "uvicorn.out.log"
$errLog = Join-Path $Logs "uvicorn.err.log"

# ── 环境变量去重（本机特有坑，必须留着）────────────────────────────
# Clash / 宿主进程会同时写入 HTTP_PROXY 和 http_proxy 两个仅大小写不同的
# 变量。PowerShell 5.1 的 Start-Process 一旦带 -RedirectStandardOutput /
# -RedirectStandardError，就会把环境变量复制进大小写不敏感的字典，随即抛：
#   Start-Process : 已添加项。字典中的关键字:"HTTPS_PROXY"所添加的关键字:"https_proxy"
# 后果是「进程其实起来了，但脚本报错退出，后面等健康的循环不执行」。
# 这里按名读取（按名读取不受重复键影响）→ 清掉 → 只写回小写名，值不丢。
foreach ($k in 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy') {
    $v = [Environment]::GetEnvironmentVariable($k)
    if ($v) {
        [Environment]::SetEnvironmentVariable($k, $null)
        [Environment]::SetEnvironmentVariable($k, $v)
    }
}

$started = $false
try {
    Start-Process -FilePath $py `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18080" `
        -WorkingDirectory $Backend -WindowStyle Hidden `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog -ErrorAction Stop
    $started = $true
} catch {
    # 兜底：重定向这条路走不通时，宁可没日志也要把服务拉起来
    Write-Host "      重定向启动失败（$($_.Exception.Message)），改用无日志方式启动" -ForegroundColor Yellow
    try {
        Start-Process -FilePath $py `
            -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18080" `
            -WorkingDirectory $Backend -WindowStyle Hidden -ErrorAction Stop
        $started = $true
        $outLog = "(未重定向，无日志文件)"
    } catch {
        Write-Host "      启动失败：$($_.Exception.Message)" -ForegroundColor Red
    }
}

$ok = $false
if ($started) {
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 2
        try {
            $h = Invoke-RestMethod -Uri "http://127.0.0.1:18080/health" -TimeoutSec 5
            Write-Host "      健康：$($h.status)" -ForegroundColor Green
            $ok = $true
            break
        } catch { }
    }
}
if ($ok) {
    Write-Host ""
    Write-Host "打开：http://127.0.0.1:18080   账号：admin / admin123" -ForegroundColor White
    Write-Host "日志：$outLog" -ForegroundColor DarkGray
} else {
    Write-Host "      起不来，看日志：$errLog" -ForegroundColor Yellow
}
