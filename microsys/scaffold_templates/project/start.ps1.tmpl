Set-StrictMode -Version Latest

# Check for --update flag to pull latest composer image
if ($args[0] -eq "--update") {
    Write-Host "=== Current Composer Version ==="
    $currentVersion = docker run --rm --entrypoint cat debeski/composer:latest /app/VERSION 2>$null
    if ($currentVersion) {
        Write-Host "  $currentVersion"
    } else {
        Write-Host "  (not present locally)"
    }

    Write-Host ""
    Write-Host "Pulling latest composer image..."
    docker pull debeski/composer:latest

    Write-Host ""
    Write-Host "=== Installed Version ==="
    docker run --rm --entrypoint cat debeski/composer:latest /app/VERSION

    exit 0
}

if ($PSScriptRoot) {
  $projectRoot = $PSScriptRoot
} else {
  $projectRoot = (Get-Location).Path
}

$projectRoot = (Resolve-Path $projectRoot).Path

if ($projectRoot -match '^([A-Za-z]):\\(.*)$') {
  $drive = $matches[1].ToLower()
  $tail = ($matches[2] -replace '\\', '/')
  $containerRoot = "/host_mnt/$drive/$tail"
} else {
  throw "Unsupported Windows path format: $projectRoot"
}

docker run -it --rm `
  -v "${projectRoot}:${containerRoot}" `
  -w "${containerRoot}" `
  -v /var/run/docker.sock:/var/run/docker.sock `
  debeski/composer:latest @args
