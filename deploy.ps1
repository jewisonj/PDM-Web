# PDM-Web Deployment Script for Fly.io
# Usage: .\deploy.ps1

# Load environment from .env file if it exists
$envFile = "$PSScriptRoot\backend\.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            Set-Item -Path "env:$name" -Value $value
        }
    }
    Write-Host "Loaded environment from $envFile" -ForegroundColor Green
}

# Check required variables
$requiredVars = @(
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY"
)

$missing = @()
foreach ($var in $requiredVars) {
    if (-not (Get-Item -Path "env:$var" -ErrorAction SilentlyContinue)) {
        $missing += $var
    }
}

if ($missing.Count -gt 0) {
    Write-Host "Missing required environment variables:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "Set them in backend\.env or as environment variables" -ForegroundColor Yellow
    exit 1
}

# Get values
$SUPABASE_URL = $env:SUPABASE_URL
$SUPABASE_ANON_KEY = $env:SUPABASE_ANON_KEY

Write-Host "Deploying PDM-Web to Fly.io..." -ForegroundColor Cyan
Write-Host "  Supabase URL: $SUPABASE_URL" -ForegroundColor Gray

# Deploy
fly deploy `
    --build-arg VITE_SUPABASE_URL=$SUPABASE_URL `
    --build-arg VITE_SUPABASE_ANON_KEY=$SUPABASE_ANON_KEY

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Deployment successful!" -ForegroundColor Green
    Write-Host "Open your app: fly open" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "Deployment failed!" -ForegroundColor Red
    exit 1
}
