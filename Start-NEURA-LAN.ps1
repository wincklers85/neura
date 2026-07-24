$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
Get-Content .env | ForEach-Object { if ($_ -and -not $_.StartsWith("#")) { $p=$_ -split "=",2; if($p.Count -eq 2){[Environment]::SetEnvironmentVariable($p[0],$p[1],"Process")}}}
Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden -ErrorAction SilentlyContinue
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -notlike '169.*' -and $_.IPAddress -ne '127.0.0.1'} | Select-Object -First 1).IPAddress
Write-Host "NÈURA sarà disponibile nella rete locale su http://${ip}:8765" -ForegroundColor Cyan
Write-Host "Usa questa modalità solo su una rete Wi-Fi fidata. La password resta obbligatoria."
& .\.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8765
