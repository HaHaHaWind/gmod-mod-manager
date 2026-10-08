# GMod Workshop Mod 管理面板 - Windows 一键启动脚本
# 用法:
#   双击 start.bat,或 PowerShell 运行: .\start.ps1 [-Port 8000]
# 功能:自动创建虚拟环境并安装依赖 -> 生成 .env -> 数据库迁移 ->
#       缺失时自动构建前端 -> (可选)创建管理员 -> 启动服务
param(
    [int]$Port = 8000,
    [string]$Host_ = "127.0.0.1"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$VenvPy = Join-Path $Root "backend\.venv\Scripts\python.exe"

Write-Host ""
Write-Host "==> GMod Mod 管理面板 - 一键启动" -ForegroundColor Cyan
Write-Host ""

# 1) 探测 Python >= 3.10
$PyCmd = $null
foreach ($cand in @(@("python"), @("py", "-3"))) {
    try {
        $out = & $cand[0] $cand[1..($cand.Count - 1)] -c "import sys; print(sys.version_info >= (3, 10))" 2>$null
        if ("$out".Trim() -eq "True") { $PyCmd = $cand; break }
    } catch { }
}
if (-not $PyCmd) {
    Write-Host "!! 未找到 Python >= 3.10,请先安装:https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}
Write-Host "==> 使用 Python:$($PyCmd -join ' ')"

# 2) 虚拟环境 + 依赖(已存在则跳过)
if (-not (Test-Path $VenvPy)) {
    Write-Host "==> 首次运行:创建虚拟环境并安装后端依赖(需几分钟)…"
    & $PyCmd[0] $PyCmd[1..($PyCmd.Count - 1)] -m venv backend\.venv
    & $VenvPy -m pip install --upgrade pip -q
    & $VenvPy -m pip install -r backend\requirements.in -q
    if ($LASTEXITCODE -ne 0) { Write-Host "!! 依赖安装失败,请检查网络后重试" -ForegroundColor Red; exit 1 }
}
else {
    Write-Host "==> 虚拟环境已就绪,跳过依赖安装(如需重装:删除 backend\.venv 后重跑)"
}

# 3) 配置文件(已存在则不覆盖)
$FreshEnv = $false
if (-not (Test-Path "backend\.env")) {
    Copy-Item ".env.example" "backend\.env"
    $FreshEnv = $true
    Write-Host "==> 已从 .env.example 生成 backend\.env,可按需修改游戏路径等配置"
}

# 4) 数据库迁移
Push-Location backend
try { & $VenvPy -m alembic upgrade head } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { Write-Host "!! 数据库迁移失败" -ForegroundColor Red; exit 1 }

# 5) 前端产物(缺失且有 Node.js 时自动构建)
if (-not (Test-Path "frontend\dist\index.html")) {
    $Npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($Npm) {
        Write-Host "==> 未发现前端产物,自动 npm install + build(需几分钟)…"
        Push-Location frontend
        try {
            & npm install --no-audit --no-fund --loglevel=error
            & npm run build
        } finally { Pop-Location }
        if ($LASTEXITCODE -ne 0) { Write-Host "!! 前端构建失败,界面暂不可用(API 仍可访问)" -ForegroundColor Yellow }
    }
    else {
        Write-Host "!! 未安装 Node.js,跳过前端构建:界面将不可用,API 仍可访问" -ForegroundColor Yellow
        Write-Host "   安装 Node.js >= 18 后重新运行本脚本即可自动构建"
    }
}
else {
    Write-Host "==> 前端产物已就绪"
}

# 6) 首次使用:创建管理员账号(交互输入密码)
if ($FreshEnv) {
    $ans = Read-Host "是否现在创建管理员账号?(y/n)"
    if ($ans -match "^[Yy]") {
        $adminName = Read-Host "管理员用户名(默认 admin)"
        if ([string]::IsNullOrWhiteSpace($adminName)) { $adminName = "admin" }
        Push-Location backend
        try { & $VenvPy -m app.cli create-admin $adminName } finally { Pop-Location }
    }
    else {
        Write-Host "已跳过。之后可手动创建:cd backend; .venv\Scripts\python -m app.cli create-admin admin"
    }
}

# 7) 启动服务(前台运行,Ctrl+C 停止)
Write-Host ""
Write-Host "==> 启动服务:http://$($Host_):$Port(按 Ctrl+C 停止)" -ForegroundColor Green
Write-Host ""
Push-Location backend
try {
    & $VenvPy -m uvicorn app.main:app --host $Host_ --port $Port
} finally { Pop-Location }
