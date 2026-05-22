param(
    [string]$ConfigPath = "configs/pilot_local.yaml",
    [bool]$PullModels = $true,
    [bool]$RunTests = $true
)

$ErrorActionPreference = "Stop"

function Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Green
}

Step "Checking GitHub remote"
git remote -v

Step "Creating Python virtual environment"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

Step "Installing Python dependencies"
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[test]"

if ($RunTests) {
    Step "Running tests"
    & .\.venv\Scripts\pytest.exe -v
}

Step "Checking Ollama"
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    Write-Host "Ollama is not on PATH. Install it from https://ollama.com/download and rerun this script." -ForegroundColor Red
    exit 1
}
ollama --version

try {
    Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" | Out-Null
} catch {
    Write-Host "Ollama is installed but not responding on http://127.0.0.1:11434." -ForegroundColor Yellow
    Write-Host "Start Ollama, then rerun this script or run: ollama serve"
}

if ($PullModels) {
    Step "Pulling configured model queue"
    & .\.venv\Scripts\cadybara.exe pull-models
}

Step "Worker setup complete"
& .\.venv\Scripts\cadybara.exe model-status
Write-Host ""
Write-Host "Next: powershell -ExecutionPolicy Bypass -File scripts/worker_start_lab.ps1" -ForegroundColor Cyan
