Set-StrictMode -Version Latest

# Check for --update flag to pull latest decrypter image
if ($args[0] -eq "--update") {
    Write-Host "=== Current Decrypter Version ==="
    $currentVersion = docker run --rm --entrypoint cat debeski/decrypter:compose /app/VERSION 2>$null
    if ($currentVersion) {
        Write-Host "  $currentVersion"
    } else {
        Write-Host "  (not present locally)"
    }

    Write-Host ""
    Write-Host "Pulling latest decrypter image..."
    docker pull debeski/decrypter:compose

    Write-Host ""
    Write-Host "=== Installed Version ==="
    docker run --rm --entrypoint cat debeski/decrypter:compose /app/VERSION

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
  debeski/decrypter:compose @args
