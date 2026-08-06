param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$RepositoryUrl = "",
    [string]$Message = "",
    [switch]$AuditOnly
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Text)
    Write-Host "[food-map-github] $Text"
}

function Invoke-Git {
    param([string[]]$Arguments)
    & git -C $ProjectRoot @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

$publishPaths = @(
    ".dockerignore",
    ".env.example",
    ".gitignore",
    "assets",
    "README.md",
    "Dockerfile",
    "app.py",
    "docker-compose.yml",
    "requirements.txt",
    "docs",
    "frontend/index.html",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/vite.config.js",
    "frontend/scripts",
    "frontend/src",
    "scripts",
    "Start Food Map.cmd",
    "Publish to GitHub.cmd"
)

$blockedPathPatterns = @(
    "(^|/)\.env($|\.)",
    "^backups/",
    "^data/",
    "^reports/",
    "^output/",
    "^\.playwright-cli/",
    "^static/",
    "^frontend/node_modules/",
    "^frontend/dist/",
    "(^|/)__pycache__/",
    "\.sqlite($|-shm$|-wal$)",
    "\.pyc$"
)

$secretPatterns = @(
    "AIza[0-9A-Za-z_-]{30,}",
    "gh[pousr]_[0-9A-Za-z_]{20,}",
    "github_pat_[0-9A-Za-z_]{20,}",
    "sk-[0-9A-Za-z_-]{24,}",
    "xox[baprs]-[0-9A-Za-z-]{20,}",
    "-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "(?i)bearer\s+[0-9A-Za-z._-]{24,}",
    "(?i)(password|passwd|secret|access[_-]?token)\s*[:=]\s*['""](?!CHANGE_ME|YOUR_|<)[^'""]{8,}['""]"
)

function Get-PublishFiles {
    $files = @()
    foreach ($relativePath in $publishPaths) {
        $path = Join-Path $ProjectRoot $relativePath
        if (-not (Test-Path -LiteralPath $path)) {
            continue
        }
        if ((Get-Item -LiteralPath $path).PSIsContainer) {
            $files += Get-ChildItem -LiteralPath $path -Recurse -File
        } else {
            $files += Get-Item -LiteralPath $path
        }
    }
    return $files |
        Where-Object {
            $_.Extension -ne ".pyc" -and
            $_.FullName -notmatch "[\\/]__pycache__[\\/]"
        } |
        Sort-Object FullName -Unique
}

function Assert-PublishFilesSafe {
    $textExtensions = @(".css", ".html", ".js", ".mjs", ".json", ".md", ".ps1", ".py", ".txt", ".vue", ".yml", ".yaml", ".cmd")
    $rootPrefix = $ProjectRoot.TrimEnd("\") + "\"
    foreach ($file in Get-PublishFiles) {
        $relative = $file.FullName
        if ($relative.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            $relative = $relative.Substring($rootPrefix.Length)
        }
        $relative = $relative -replace "\\", "/"
        if ($relative -ne ".env.example") {
            foreach ($pattern in $blockedPathPatterns) {
                if ($relative -match $pattern) {
                    throw "Blocked private/runtime file: $relative"
                }
            }
        }
        if ($file.Name -eq ".env.example" -or $textExtensions -notcontains $file.Extension.ToLowerInvariant()) {
            continue
        }
        $content = Get-Content -Raw -LiteralPath $file.FullName
        foreach ($pattern in $secretPatterns) {
            if ($content -match $pattern) {
                throw "Potential secret detected in: $relative"
            }
        }
    }
}

Write-Step "Auditing the publish allowlist and scanning for secrets."
Assert-PublishFilesSafe
Write-Step "Privacy audit passed."

if ($AuditOnly) {
    Write-Step "Audit-only run complete. Nothing was committed or uploaded."
    exit 0
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not installed or is not available in PATH."
}

if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot ".git"))) {
    if ([string]::IsNullOrWhiteSpace($RepositoryUrl)) {
        $RepositoryUrl = Read-Host "首次使用，请输入空 GitHub 仓库地址"
    }
    if ([string]::IsNullOrWhiteSpace($RepositoryUrl)) {
        throw "A GitHub repository URL is required for first-time setup."
    }
    Write-Step "Initializing a new local Git repository."
    Invoke-Git @("init")
    Invoke-Git @("branch", "-M", "main")
    Invoke-Git @("remote", "add", "origin", $RepositoryUrl)
} elseif (-not [string]::IsNullOrWhiteSpace($RepositoryUrl)) {
    $origin = (& git -C $ProjectRoot remote get-url origin 2>$null)
    if ($LASTEXITCODE -eq 0) {
        Invoke-Git @("remote", "set-url", "origin", $RepositoryUrl)
    } else {
        Invoke-Git @("remote", "add", "origin", $RepositoryUrl)
    }
}

$originUrl = (& git -C $ProjectRoot remote get-url origin 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($originUrl)) {
    throw "Git remote 'origin' is not configured."
}

& git -C $ProjectRoot reset --quiet 2>$null
foreach ($relativePath in $publishPaths) {
    if (Test-Path -LiteralPath (Join-Path $ProjectRoot $relativePath)) {
        Invoke-Git @("add", "--", $relativePath)
    }
}

$staged = @(& git -C $ProjectRoot diff --cached --name-only)
if (-not $staged) {
    Write-Step "No safe changes to upload."
    exit 0
}

foreach ($file in $staged) {
    $normalized = $file -replace "\\", "/"
    if ($normalized -eq ".env.example") {
        continue
    }
    foreach ($pattern in $blockedPathPatterns) {
        if ($normalized -match $pattern) {
            Invoke-Git @("reset", "--")
            throw "Blocked file staged unexpectedly: $file"
        }
    }
}

Write-Step "Files approved for publishing:"
$staged | ForEach-Object { Write-Host "  $_" }

if ([string]::IsNullOrWhiteSpace($Message)) {
    $Message = "chore: update DuskRain food map $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
}

Invoke-Git @("commit", "-m", $Message)
$branch = (& git -C $ProjectRoot branch --show-current).Trim()
Invoke-Git @("push", "-u", "origin", $branch)
Write-Step "GitHub upload complete."
