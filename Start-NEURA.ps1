$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".env")) { throw "Configurazione mancante. Esegui prima Install-NEURA.ps1" }
Get-Content .env | ForEach-Object {
    if ($_ -and -not $_.StartsWith("#")) {
        $pair = $_ -split "=",2
        if ($pair.Count -eq 2) { [Environment]::SetEnvironmentVariable($pair[0],$pair[1],"Process") }
    }
}
Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:8765"
& .\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8765
