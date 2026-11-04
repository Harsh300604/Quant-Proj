# One-time setup: creates the virtual environment on D: and installs the pinned packages.
# Usage, from the repo folder:
#     Set-ExecutionPolicy -Scope Process Bypass -Force; .\scripts\setup.ps1
#
# Needs Python 3.12 (or newer). If Python is not installed yet, install it ON D: with the
# official installer from python.org: choose "Customize installation" and set the install
# location to D:\Python312. Then run this script again.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# 1. Per-session caches/temp on D: (also refuses to run if the repo is not on D:)
. (Join-Path $PSScriptRoot "env.ps1")
if (-not $env:PIP_CACHE_DIR) { exit 1 }

# 2. Find Python 3.12+
$Py = $null
$Candidates = @("D:\Python312\python.exe", "D:\Python313\python.exe")
foreach ($c in $Candidates) { if (Test-Path $c) { $Py = $c; break } }
if (-not $Py) {
    foreach ($v in @("3.12", "3.13")) {
        try { $p = (& py "-$v" -c "import sys; print(sys.executable)" 2>$null); if ($LASTEXITCODE -eq 0 -and $p) { $Py = $p.Trim(); break } } catch {}
    }
}
if (-not $Py) {
    try { $p = (& python -c "import sys; print(sys.executable) if sys.version_info >= (3,12) else None" 2>$null); if ($p -and $p.Trim() -ne "None") { $Py = $p.Trim() } } catch {}
}
if (-not $Py) {
    Write-Host "ERROR: Python 3.12+ not found. Install it to D:\Python312 (python.org installer -> Customize installation), then rerun." -ForegroundColor Red
    exit 1
}
Write-Host "Using Python: $Py"

# 3. Virtual environment inside the repo (on D:)
$Venv = Join-Path $RepoRoot ".venv"
function Invoke-Step($What, [scriptblock]$Cmd) {
    Write-Host "-> $What"
    & $Cmd
    if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: $What failed (see the messages above)." -ForegroundColor Red; exit 1 }
}
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    Invoke-Step "create virtual environment" { & $Py -m venv $Venv }
}
$VPy = Join-Path $Venv "Scripts\python.exe"
Invoke-Step "upgrade pip" { & $VPy -m pip install --upgrade pip }
Invoke-Step "install pinned packages" { & $VPy -m pip install -r (Join-Path $RepoRoot "requirements.txt") }
Invoke-Step "install the quantagents package" { & $VPy -m pip install -e $RepoRoot --no-deps }

# 4. .env from the template (values left blank for you to fill in)
$EnvFile = Join-Path $RepoRoot ".env"
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $RepoRoot ".env.example") $EnvFile
    Write-Host "Created .env from .env.example - open it in Notepad and fill in the values." -ForegroundColor Yellow
}

. (Join-Path $Venv "Scripts\Activate.ps1")
Write-Host "Setup complete. venv: $Venv" -ForegroundColor Green
