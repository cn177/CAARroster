# 不正常推理协会 · 会员与队伍管理系统 —— Windows 一键启动
#
# 双击 start-windows.bat 就会跑这个脚本。
# 它会：找 Python → 建独立环境 → 装依赖 → 建数据库 → 建管理账号 → 启动服务。
# 第一次会慢几分钟，之后就快了。

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Say($msg) { Write-Host $msg }
function Line { Write-Host ("-" * 60) }

function Fail($msg) {
    Write-Host ""
    Write-Host "[错误] $msg" -ForegroundColor Red
    Write-Host ""
    Read-Host "按回车键关闭窗口"
    exit 1
}

Write-Host ""
Write-Host "============================================================"
Write-Host "  不正常推理协会 - 会员与队伍管理系统"
Write-Host "============================================================"
Write-Host ""

# ---------------------------------------------------------------- 1/5 找 Python
# 先看 PATH，再翻常见安装目录 —— 很多人装的时候忘了勾 "Add python.exe to PATH"。
$candidates = @()
foreach ($cmd in @("python", "py")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) { $candidates += $cmd }
}
foreach ($pattern in @(
        "C:\Python3*\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
        "C:\Program Files\Python3*\python.exe",
        "C:\Program Files (x86)\Python3*\python.exe")) {
    foreach ($hit in (Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue)) {
        $candidates += $hit.FullName
    }
}

$python = $null
$pyver = $null
foreach ($cand in $candidates) {
    try {
        $out = & $cand -c "import sys;print('%d.%d.%d' % sys.version_info[:3])" 2>$null
        if ($LASTEXITCODE -eq 0 -and "$out".Trim()) {
            $python = $cand
            $pyver = "$out".Trim()
            break
        }
    }
    catch { }
}

if (-not $python) {
    Say "[1/5] 没有找到可用的 Python。"
    Say ""
    Say "请先装 Python，步骤："
    Say "  1. 打开 https://www.python.org/downloads/windows/"
    Say "  2. 下载『Windows installer (64-bit)』"
    Say '  3. 安装时最下面那个 "Add python.exe to PATH" 一定要勾上'
    Say "  4. 装完关掉这个窗口，重新双击 start-windows.bat"
    Say ""
    Say "注意：如果在命令行敲 python 会跳出『应用商店』，说明 Python 其实根本没装 ——"
    Say "      那是微软放的占位符，不是真的 Python。"
    Fail "缺少 Python"
}
Say "[1/5] 找到 Python $pyver （$python）"

$parts = $pyver.Split(".")
if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 10)) {
    Fail "Python 版本太老（$pyver）。这个程序需要 3.10 以上，建议直接装 3.12。"
}

# ---------------------------------------------------------------- 2/5 独立环境
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Say "[2/5] 首次运行，正在创建独立运行环境（约半分钟）..."
    & $python -m venv ".venv"
    if (-not (Test-Path $py)) { Fail "创建运行环境失败，磁盘空间够吗？" }
}
else {
    Say "[2/5] 运行环境已就绪"
}

# ---------------------------------------------------------------- 3/5 装依赖
$depsFlag = Join-Path $root ".venv\deps-ok.txt"
if (-not (Test-Path $depsFlag)) {
    Say "[3/5] 正在安装依赖，第一次要下载一些东西，请耐心等..."
    Say "      （用的是清华镜像，国内会快很多）"
    $mirror = "https://pypi.tuna.tsinghua.edu.cn/simple"
    & $py -m pip install --upgrade pip -i $mirror --quiet
    & $py -m pip install -r requirements.txt -i $mirror
    if ($LASTEXITCODE -ne 0) {
        Fail "依赖安装失败。最常见的原因是服务器连不上网，或者防火墙拦了。"
    }
    "ok" | Out-File -FilePath $depsFlag -Encoding ascii
    Say "      依赖装好了"
}
else {
    Say "[3/5] 依赖已安装"
}

# ---------------------------------------------------------------- 4/5 数据库与账号
Say "[4/5] 检查数据库..."
& $py app.py --init-db | Out-Null

& $py app.py --check-admin
if ($LASTEXITCODE -ne 0) {
    Say ""
    Say "还没有管理账号，现在建一个。"
    Say "用户名固定是 admin，密码请设一个至少 8 位的。"
    Say ""
    if ($env:ARA_ADMIN_PASSWORD) {
        $plain = $env:ARA_ADMIN_PASSWORD
        Say "（使用环境变量 ARA_ADMIN_PASSWORD 里给的密码）"
    }
    else {
        $secure = Read-Host "请输入 admin 的密码" -AsSecureString
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    }
    if (-not $plain -or $plain.Length -lt 8) { Fail "密码太短，至少要 8 位。" }
    & $py app.py --create-admin admin $plain
    Say ""
    Say "账号已创建。登录后请到右上角『账号』页面把它改成你自己记得住的密码。"
}

# ---------------------------------------------------------------- 5/5 启动
$port = if ($env:ARA_PORT) { $env:ARA_PORT } else { "8000" }

Write-Host ""
Line
Write-Host "  服务已启动，正在监听 127.0.0.1:$port" -ForegroundColor Green
Write-Host "  它只对服务器自己开放，公网连不上 —— 这是故意的。"
Write-Host ""
Write-Host "  在你自己的电脑上打开一个终端，执行下面这条（换成你的用户名和服务器 IP）："
Write-Host ""
Write-Host "      ssh -L ${port}:127.0.0.1:${port} 你的用户名@服务器IP" -ForegroundColor Yellow
Write-Host ""
Write-Host "  保持那个终端窗口开着，然后用浏览器打开："
Write-Host ""
Write-Host "      http://127.0.0.1:$port" -ForegroundColor Yellow
Write-Host ""
Write-Host "  【重要】这个黑窗口不能关，关了服务就停了。"
Write-Host "         要长期运行请看 README 的『开机自启』一节。"
Line
Write-Host ""

& $py app.py --production --port $port

Write-Host ""
Say "服务已停止。"
Read-Host "按回车键关闭窗口"
