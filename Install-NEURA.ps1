$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host ""; Write-Host "NÈURA Surface - installazione" -ForegroundColor Cyan
Write-Host "Questa procedura installa Python, Ollama, le dipendenze e il modello locale." 

function Has-Command($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

if (-not (Has-Command "python")) {
    if (-not (Has-Command "winget")) { throw "Winget non trovato. Installa Python 3.12 dal Microsoft Store e rilancia lo script." }
    Write-Host "Installazione Python 3.12..."
    winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
}

if (-not (Has-Command "ollama")) {
    if (-not (Has-Command "winget")) { throw "Winget non trovato. Installa Ollama dal sito ufficiale e rilancia lo script." }
    Write-Host "Installazione Ollama..."
    winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
}

if (-not (Test-Path ".venv")) {
    Write-Host "Creazione ambiente Python..."
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

$password = Read-Host "Scegli la password di accesso a NÈURA"
if ([string]::IsNullOrWhiteSpace($password)) { throw "La password non può essere vuota." }
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$key = [Convert]::ToBase64String($bytes)

$envFile = @"
APP_PASSWORD=$password
ENCRYPTION_KEY=$key
DATA_DIR=$Root\data
OLLAMA_URL=http://127.0.0.1:11434
MODEL_NAME=qwen3.5:2b
VISION_MODEL=qwen2.5vl:3b
MODEL_CONTEXT=4096
LLM_TIMEOUT=120
# Facoltativo: inserisci una chiave Tavily per una ricerca web più affidabile
TAVILY_API_KEY=
"@
Set-Content -Path ".env" -Value $envFile -Encoding UTF8

Write-Host "Avvio Ollama..."
Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
Write-Host "Download del modello qwen3.5:2b. Può richiedere alcuni minuti..."
& ollama pull qwen3.5:2b
$vision = Read-Host "Vuoi installare anche il modello locale per riconoscere immagini? (S/N)"
if ($vision -match "^[SsYy]") {
    Write-Host "Download del modello visivo..."
    & ollama pull qwen2.5vl:3b
}

Write-Host ""; Write-Host "Installazione completata." -ForegroundColor Green
Write-Host "Apri Start-NEURA.cmd per avviare NÈURA."
Pause
