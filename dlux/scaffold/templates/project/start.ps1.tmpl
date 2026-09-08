# composer-wrapper: 3
Set-StrictMode -Version Latest

# The wrapper resolves its own image before any composer code can run, so the
# channel has to be readable from here. `.composer-channel` holds one word,
# written by `composer check --beta` / `--stable`.
#
# COMPOSER_SELF_IMAGE still wins. An operator who pinned an exact image asked
# for that image; a channel is a default, and a default must never quietly
# discard an explicit pin.
$composerScriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$composerChannel = "stable"
$composerChannelFile = Join-Path $composerScriptRoot ".composer-channel"
if (Test-Path -LiteralPath $composerChannelFile) {
    try {
        $raw = (Get-Content -LiteralPath $composerChannelFile -TotalCount 1 -ErrorAction Stop)
        if ($raw) { $composerChannel = $raw.Trim().ToLowerInvariant() }
    } catch {
        $composerChannel = "stable"
    }
}
$composerChannelImage = if ($composerChannel -eq "beta") { "debeski/composer:beta" } else { "debeski/composer:latest" }
$composerSelfImage = if ($env:COMPOSER_SELF_IMAGE) { $env:COMPOSER_SELF_IMAGE } else { $composerChannelImage }

# Pull the deployer image before launching composer from that same image.
if ($args.Count -eq 2 -and $args[0] -eq "self" -and $args[1] -eq "update") {
    # `docker image inspect` first: `docker run` on a missing image pulls it,
    # silently, since the progress goes to the stderr this used to discard.
    Write-Host "=== Current Composer Version ==="
    docker image inspect $composerSelfImage 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $currentVersion = docker run --rm --entrypoint cat $composerSelfImage /app/VERSION
        Write-Host "  $currentVersion"
    } else {
        Write-Host "  (not present locally)"
    }

    Write-Host ""
    Write-Host "Pulling latest composer image..."
    docker pull $composerSelfImage

    Write-Host ""
    Write-Host "=== Installed Version ==="
    docker run --rm --entrypoint cat $composerSelfImage /app/VERSION

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

# Announce the first-run download instead of letting `docker run` pull an
# unnamed image while the command appears to hang.
docker image inspect $composerSelfImage 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Composer image not installed locally — fetching $composerSelfImage..."
  docker pull $composerSelfImage
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  Write-Host ""
}

# Attach stdin unconditionally, so a pipe reaches the container instead of the
# container getting no stdin at all. Allocate a TTY only when there is one;
# `-t` on a redirected stream fails.
$ttyFlags = @("-i")
if (-not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected) {
  $ttyFlags += "-t"
}

$dockerArgs = @("run") + $ttyFlags + @("--rm") + $secretArgs + @(
  "-v", "${projectRoot}:${containerRoot}",
  "-w", $containerRoot,
  "-v", "/var/run/docker.sock:/var/run/docker.sock",
  $composerSelfImage
) + $args

& docker @dockerArgs
exit $LASTEXITCODE
