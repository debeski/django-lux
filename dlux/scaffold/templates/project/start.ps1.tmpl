# composer-wrapper: 6
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

# The deployer can only be refreshed here: a composer already running from
# this image cannot replace it. `update self` refreshes only the deployer;
# `update` with no named services refreshes it first, so the stack update
# that follows runs on the new deployer. Named services skip the refresh.
function Get-ComposerImageId {
    $id = docker image inspect --format "{{.Id}}" $composerSelfImage 2>$null
    if ($LASTEXITCODE -ne 0) { return "" }
    return ("$id").Trim()
}

function Get-ComposerImageVersion([string]$Image) {
    $version = docker run --rm --entrypoint cat $Image /app/VERSION 2>$null
    if ($LASTEXITCODE -ne 0) { return "" }
    return ("$version").Trim()
}

# A rebuilt tag can keep its version string, so compare image IDs, and start
# a container for a version only when there is one to report. The replaced
# image stays readable by ID after the pull.
function Update-ComposerDeployer {
    $beforeId = Get-ComposerImageId
    Write-Host "Updating the Composer deployer ($composerSelfImage)..."
    # Out-Host keeps the pull's output out of this function's return value.
    docker pull $composerSelfImage | Out-Host
    if ($LASTEXITCODE -ne 0) { return $false }
    $afterId = Get-ComposerImageId
    if ($beforeId -and $beforeId -eq $afterId) {
        Write-Host "Composer deployer is up to date ($(Get-ComposerImageVersion $composerSelfImage))."
        return $true
    }
    $previous = if ($beforeId) { Get-ComposerImageVersion $beforeId } else { "" }
    if (-not $previous) { $previous = "not installed" }
    Write-Host "Composer deployer: $previous -> $(Get-ComposerImageVersion $composerSelfImage)"
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

$dockerArgs = @("run") + $ttyFlags + @("--rm") + $secretArgs + @(
  "-v", "${projectRoot}:${containerRoot}",
  "-w", $containerRoot,
  "-v", "/var/run/docker.sock:/var/run/docker.sock",
  $composerSelfImage
) + $args

& docker @dockerArgs
exit $LASTEXITCODE
