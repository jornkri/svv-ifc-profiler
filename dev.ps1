# dev.ps1 — Start backend (uvicorn) + frontend (vite) i separate vinduer
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173
)

$root = $PSScriptRoot

# Finn Python: foretrekker .venv, faller tilbake til ArcGIS Pro
$python = @(
    "$root\.venv\Scripts\python.exe",
    "$root\venv\Scripts\python.exe",
    "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $python) {
    Write-Error "Finner ikke Python. Opprett .venv eller installer ArcGIS Pro."
    exit 1
}

Write-Host "Python: $python" -ForegroundColor Cyan

# Backend
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$root'; Write-Host 'Backend starter på http://localhost:$BackendPort' -ForegroundColor Green; & '$python' -m uvicorn src.api.server:app --port $BackendPort --reload"
) -WindowStyle Normal

# Frontend
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$root\web'; Write-Host 'Frontend starter på http://localhost:$FrontendPort' -ForegroundColor Green; npm run dev -- --port $FrontendPort"
) -WindowStyle Normal

Write-Host ""
Write-Host "Starter SVV IFC Profiler..." -ForegroundColor Green
Write-Host "  Backend:  http://localhost:$BackendPort" -ForegroundColor Cyan
Write-Host "  Frontend: http://localhost:$FrontendPort" -ForegroundColor Cyan
Write-Host ""
Write-Host "Lukk de to PowerShell-vinduene for å stoppe."
