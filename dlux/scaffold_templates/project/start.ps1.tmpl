Set-StrictMode -Version Latest

# `--update` as the *only* argument self-updates the Composer tool image.
# `--update <service>` (and -u/-uo/restart/-r) pass through to the app instead.
if ($args.Count -eq 1 -and $args[0] -eq "--update") {
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

$secretArgs = @()
foreach ($candidate in @(".env", "secrets/.env", ".secrets/.env")) {
  $secretPath = Join-Path $projectRoot $candidate
  if (-not (Test-Path -LiteralPath $secretPath -PathType Leaf)) {
    continue
  }
  $secretKeys = @(
    Get-Content -LiteralPath $secretPath | ForEach-Object {
      if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=') { $matches[1] }
    }
  )
  if ($secretKeys.Count -eq 0) {
    throw "Secrets file contains no environment values: $secretPath"
  }
  $secretArgs = @(
    "--env-file", $secretPath,
    "-e", "COMPOSER_INHERITED_SECRET_KEYS=$($secretKeys -join ',')"
  )
  break
}

$dockerArgs = @("run", "-it", "--rm") + $secretArgs + @(
  "-v", "${projectRoot}:${containerRoot}",
  "-w", $containerRoot,
  "-v", "/var/run/docker.sock:/var/run/docker.sock",
  "debeski/composer:latest"
) + $args

& docker @dockerArgs
exit $LASTEXITCODE
