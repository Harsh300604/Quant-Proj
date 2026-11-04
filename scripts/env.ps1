# QuantAgents per-session environment (affects ONLY this PowerShell window).
# Usage, from the repo folder:
#     Set-ExecutionPolicy -Scope Process Bypass -Force; . .\scripts\env.ps1
#
# - Refuses to run if the repo is not on D:
# - Points pip/uv/npm caches, TEMP/TMP and library caches at D:\CreatED-Quant\qa_store\...
# - Activates the project's virtual environment (.venv) if it exists
# Nothing is changed system-wide.

$QA_RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $QA_RepoRoot.ToUpper().StartsWith("D:")) {
    Write-Host "ERROR: the repo is at $QA_RepoRoot. It must be on the D: drive (e.g. D:\CreatED-Quant\quantagents)." -ForegroundColor Red
    return
}

if ($env:QA_STORE_ROOT) { $QA_Store = $env:QA_STORE_ROOT } else { $QA_Store = "D:\CreatED-Quant\qa_store" }
if (-not $QA_Store.ToUpper().StartsWith("D:")) {
    Write-Host "ERROR: QA_STORE_ROOT ($QA_Store) must be on D:." -ForegroundColor Red
    return
}

$QA_Dirs = @("pip-cache", "uv-cache", "npm-cache", "tmp", "lib-cache\matplotlib", "lib-cache\numba", "lib-cache\hf", "lib-cache\yfinance", "logs")
foreach ($d in $QA_Dirs) { New-Item -ItemType Directory -Force -Path (Join-Path $QA_Store $d) | Out-Null }

$env:QA_STORE_ROOT    = $QA_Store
$env:PIP_CACHE_DIR    = Join-Path $QA_Store "pip-cache"
$env:UV_CACHE_DIR     = Join-Path $QA_Store "uv-cache"
$env:npm_config_cache = Join-Path $QA_Store "npm-cache"
$env:TMP              = Join-Path $QA_Store "tmp"
$env:TEMP             = Join-Path $QA_Store "tmp"
$env:MPLCONFIGDIR     = Join-Path $QA_Store "lib-cache\matplotlib"
$env:NUMBA_CACHE_DIR  = Join-Path $QA_Store "lib-cache\numba"
$env:HF_HOME          = Join-Path $QA_Store "lib-cache\hf"
$env:PYTHONUTF8       = "1"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"

$QA_Activate = Join-Path $QA_RepoRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $QA_Activate) {
    . $QA_Activate
    Write-Host "QuantAgents environment ready. Store: $QA_Store  venv: $QA_RepoRoot\.venv" -ForegroundColor Green
} else {
    Write-Host "Caches and temp folders point to $QA_Store. No .venv yet - run .\scripts\setup.ps1" -ForegroundColor Yellow
}
