param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [int]$HealthTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path

function Write-Step {
    param([string]$Text)
    Write-Host "[DuskRain] $Text" -ForegroundColor Cyan
}

function Wait-Docker {
    param([int]$TimeoutSeconds = 180)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        & docker info *> $null
        if ($LASTEXITCODE -eq 0) {
            return $true
        }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)

    return $false
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Docker Desktop is not installed. Install Docker Desktop, then run this file again."
    }

    $answer = Read-Host "Docker Desktop is missing. Install it now with winget? [Y/n]"
    if ($answer -and $answer -notmatch '^[Yy]') {
        throw "Docker Desktop is required."
    }

    Write-Step "Installing Docker Desktop. Windows may request administrator approval."
    & winget install --id Docker.DockerDesktop --exact --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop installation failed with exit code $LASTEXITCODE."
    }
}

& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path -LiteralPath $dockerDesktop) {
        Write-Step "Starting Docker Desktop."
        Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
    }
    Write-Step "Waiting for the Docker engine."
    if (-not (Wait-Docker -TimeoutSeconds $HealthTimeoutSeconds)) {
        throw "Docker did not become ready within $HealthTimeoutSeconds seconds."
    }
}

$envFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Missing .env. Restore the encrypted private backup or create .env from .env.example first."
}

$dataDir = Join-Path $ProjectRoot "data"
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null

Write-Step "Building and starting the food map."
& docker compose --project-directory $ProjectRoot up -d --build
if ($LASTEXITCODE -ne 0) {
    throw "docker compose up failed with exit code $LASTEXITCODE."
}

$healthUrl = "http://127.0.0.1:8091/api/health"
$deadline = (Get-Date).AddSeconds($HealthTimeoutSeconds)
$healthy = $false
do {
    try {
        $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5
        if ($response) {
            $healthy = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 3
    }
} while ((Get-Date) -lt $deadline)

if (-not $healthy) {
    & docker compose --project-directory $ProjectRoot ps
    & docker compose --project-directory $ProjectRoot logs --tail 120
    throw "The container started, but the health endpoint did not become ready."
}

Write-Step "Food map is ready at http://127.0.0.1:8091/"
Start-Process "http://127.0.0.1:8091/"
