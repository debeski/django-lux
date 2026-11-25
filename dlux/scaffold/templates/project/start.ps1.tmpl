# composer-wrapper: 7
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

# `.composer-image` holds the digest the last verified update pinned, written by
# composer itself (`update self`, `agent update`, `check --beta` / `--stable`).
# It is read with the same pattern composer uses (case-sensitive), so a
# malformed lock falls back to the channel tag in both places.
# COMPOSER_SELF_IMAGE still beats it.
$composerLockFile = Join-Path $composerScriptRoot ".composer-image"
$composerLockPattern = '^debeski/composer:v[0-9]+(\.[0-9]+){1,2}((a|b|rc)[0-9]+)?@sha256:[0-9a-f]{64}$'
function Read-ComposerLock {
    if (-not (Test-Path -LiteralPath $composerLockFile)) { return "" }
    try {
        $raw = (Get-Content -LiteralPath $composerLockFile -TotalCount 1 -ErrorAction Stop)
    } catch {
        return ""
    }
    $value = ("$raw" -replace '\s', '')
    if ($value -cmatch $composerLockPattern) { return $value }
    return ""
}
$composerLockImage = Read-ComposerLock
$composerSelfImage = if ($env:COMPOSER_SELF_IMAGE) { $env:COMPOSER_SELF_IMAGE } elseif ($composerLockImage) { $composerLockImage } else { $composerChannelImage }

if ($PSScriptRoot) {
  $projectRoot = $PSScriptRoot
} else {
  $projectRoot = (Get-Location).Path
}

$projectRoot = (Resolve-Path $projectRoot).Path

# Resolved only when a container is about to start, so the deployer refresh
# routing still runs (and is tested) where this is not a Windows path.
function Get-ComposerContainerRoot {
  if ($projectRoot -match '^([A-Za-z]):\\(.*)$') {
    $drive = $matches[1].ToLower()
    $tail = ($matches[2] -replace '\\', '/')
    $containerRoot = "/host_mnt/$drive/$tail"
    return $containerRoot
  }
  throw "Unsupported Windows path format: $projectRoot"
}

# Secrets reach every composer run, the pin included: validating the Compose
# edit interpolates the same variables a deploy does.
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

# The deployer can only be refreshed here: a composer already running from
# this image cannot replace it. `update self` refreshes only the deployer;
# `update` with no named services refreshes it first, so the stack update
# that follows runs on the new deployer. Named services skip the refresh.
function Get-ComposerImageId {
    $id = docker image inspect --format "{{.Id}}" $script:composerSelfImage 2>$null
    if ($LASTEXITCODE -ne 0) { return "" }
    return ("$id").Trim()
}

function Get-ComposerImageVersion([string]$Image) {
    $version = docker run --rm --entrypoint cat $Image /app/VERSION 2>$null
    if ($LASTEXITCODE -ne 0) { return "" }
    return ("$version").Trim()
}

function Test-ComposerCanPin([string]$Image) {
    $label = docker image inspect --format '{{ index .Config.Labels "org.dlux.composer.image-pin" }}' $Image 2>$null
    if ($LASTEXITCODE -ne 0) { return $false }
    return (("$label").Trim() -eq "1")
}

# The installed deployer resolves the channel's newest release, verifies its
# signed digest and writes the lock; only then is that digest pulled, so the
# registry cannot swap what arrives. With no lock yet, the first pin trusts the
# channel tag once, exactly as every update did before pinning existed.
function Invoke-ComposerPin {
    $resolver = if ($script:composerLockImage) { $script:composerLockImage } else { $composerChannelImage }
    if (-not $script:composerLockImage) {
        docker pull $composerChannelImage | Out-Host
        if ($LASTEXITCODE -ne 0) { return $false }
    } else {
        docker image inspect $resolver 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            docker pull $resolver | Out-Host
            if ($LASTEXITCODE -ne 0) { return $false }
        }
    }
    if (-not (Test-ComposerCanPin $resolver)) {
        Write-Host "This Composer predates digest pinning; the deployer stays on $composerChannelImage."
        $script:composerSelfImage = $composerChannelImage
        return $true
    }
    $containerRoot = Get-ComposerContainerRoot
    $pinArgs = @("run", "--rm") + $secretArgs + @(
        "-e", "COMPOSER_ALLOW_UNVERIFIED_COMPOSER",
        "-v", "${projectRoot}:${containerRoot}",
        "-w", $containerRoot,
        "-v", "/var/run/docker.sock:/var/run/docker.sock",
        $resolver, "update", "self", "--pin"
    )
    & docker @pinArgs | Out-Host
    if ($LASTEXITCODE -ne 0) { return $false }
    $script:composerLockImage = Read-ComposerLock
    if (-not $script:composerLockImage) {
        # Nothing to pin yet (composer said why): keep the deployer just installed.
        $script:composerSelfImage = $resolver
        return $true
    }
    $script:composerSelfImage = $script:composerLockImage
    docker image inspect $script:composerSelfImage 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        docker pull $script:composerSelfImage | Out-Host
        if ($LASTEXITCODE -ne 0) { return $false }
    }
    return $true
}

# A rebuilt tag can keep its version string, so compare image IDs, and start
# a container for a version only when there is one to report. The replaced
# image stays readable by ID after the pull.
function Update-ComposerDeployer {
    $beforeId = Get-ComposerImageId
    if ($env:COMPOSER_SELF_IMAGE) {
        Write-Host "Updating the Composer deployer ($composerSelfImage)..."
        # Out-Host keeps the pull's output out of this function's return value.
        docker pull $composerSelfImage | Out-Host
        if ($LASTEXITCODE -ne 0) { return $false }
    } else {
        Write-Host "Updating the Composer deployer ($composerChannel channel)..."
        if (-not (Invoke-ComposerPin)) { return $false }
    }
    $afterId = Get-ComposerImageId
    if ($beforeId -and $beforeId -eq $afterId) {
        Write-Host "Composer deployer is up to date ($(Get-ComposerImageVersion $script:composerSelfImage))."
        return $true
    }
    $previous = if ($beforeId) { Get-ComposerImageVersion $beforeId } else { "" }
    if (-not $previous) { $previous = "not installed" }
    Write-Host "Composer deployer: $previous -> $(Get-ComposerImageVersion $script:composerSelfImage)"
    return $true
}

function Get-ComposerInvocation([string[]]$Arguments) {
    $i = 0
    while ($i -lt $Arguments.Count) {
        $token = $Arguments[$i]
        if ($token -eq "-d" -or $token -eq "--dev" -or $token -like "--file=*") { $i += 1; continue }
        if ($token -eq "-f" -or $token -eq "--file") { $i += 2; continue }
        break
    }
    if ($i -ge $Arguments.Count) { return "" }
    $command = $Arguments[$i]
    $rest = @()
    if ($i + 1 -lt $Arguments.Count) { $rest = @($Arguments[($i + 1)..($Arguments.Count - 1)]) }
    if ($command -eq "self" -and $rest.Count -eq 1 -and $rest[0] -eq "update") { return "self_update" }
    if ($command -ne "update") { return "" }
    # `update self` takes only the global -f/-d options, in any position, like
    # composer itself; anything else is left for composer to reject.
    $selves = 0
    $options = $false
    $j = 0
    while ($j -lt $rest.Count) {
        $token = $rest[$j]
        if ($token -eq "-h" -or $token -eq "--help") { return "" }
        if ($token -eq "self") { $selves += 1; $j += 1; continue }
        if ($token -eq "-d" -or $token -eq "--dev" -or $token -like "--file=*") { $j += 1; continue }
        if ($token -eq "-f" -or $token -eq "--file") { $j += 2; continue }
        if ($token -in @("-a", "--app", "--status-file")) { $options = $true; $j += 2; continue }
        if (-not $token.StartsWith("-")) { return "" }
        $options = $true
        $j += 1
    }
    if ($selves -eq 0) { return "update_all" }
    if ($selves -eq 1 -and -not $options) { return "update_self" }
    return ""
}

$composerInvocation = Get-ComposerInvocation @($args)
if ($composerInvocation -eq "self_update") {
    [Console]::Error.WriteLine("Note: 'self update' is deprecated; use '.\start.ps1 update self'.")
    if (-not (Update-ComposerDeployer)) { exit 1 }
    exit 0
}
if ($composerInvocation -eq "update_self") {
    if (-not (Update-ComposerDeployer)) { exit 1 }
    exit 0
}
if ($composerInvocation -eq "update_all") {
    if (-not (Update-ComposerDeployer)) {
        [Console]::Error.WriteLine("Warning: could not refresh the Composer deployer; updating the stack with the installed one.")
    }
    Write-Host ""
}

# Announce the first-run download instead of letting `docker run` pull an
# unnamed image while the command appears to hang.
docker image inspect $composerSelfImage 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Composer image not installed locally - fetching $composerSelfImage..."
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

$containerRoot = Get-ComposerContainerRoot
$dockerArgs = @("run") + $ttyFlags + @("--rm") + $secretArgs + @(
  "-e", "COMPOSER_ALLOW_UNVERIFIED_COMPOSER",
  "-e", "COMPOSER_HEALTH_SETTLE_SECONDS",
  "-v", "${projectRoot}:${containerRoot}",
  "-w", $containerRoot,
  "-v", "/var/run/docker.sock:/var/run/docker.sock",
  $composerSelfImage
) + $args

& docker @dockerArgs
exit $LASTEXITCODE
