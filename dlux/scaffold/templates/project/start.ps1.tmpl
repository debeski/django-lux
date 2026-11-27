# composer-wrapper: 8
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
# It is read with the rule composer uses: the first non-empty line, stripped at
# its ends (and of a byte-order mark), must match the pattern whole
# (case-sensitive); nothing inside it is removed. A malformed lock falls back to
# the channel tag in both places. COMPOSER_SELF_IMAGE still beats it.
$composerLockFile = Join-Path $composerScriptRoot ".composer-image"
$composerLockPattern = '^debeski/composer:v[0-9]+(\.[0-9]+){1,2}((a|b|rc)[0-9]+)?@sha256:[0-9a-f]{64}$'
function Read-ComposerLock {
    if (-not (Test-Path -LiteralPath $composerLockFile)) { return "" }
    try {
        $lines = @(Get-Content -LiteralPath $composerLockFile -ErrorAction Stop)
    } catch {
        return ""
    }
    foreach ($line in $lines) {
        $value = "$line".TrimStart([char]0xFEFF).Trim(" ", "`t", "`r", "`v", "`f")
        if ($value) {
            if ($value -cmatch $composerLockPattern) { return $value }
            return ""
        }
    }
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
# edit interpolates the same variables a deploy does. The first file that exists
# is used; one that leaves out keys a later file holds is a stray copy shadowing
# the real one, and is refused rather than deployed on compose defaults.
$secretArgs = @()
$secretKeys = @()
$secretSource = ""
foreach ($candidate in @(".env", "secrets/.env", ".secrets/.env")) {
  $secretPath = Join-Path $projectRoot $candidate
  if (-not (Test-Path -LiteralPath $secretPath -PathType Leaf)) {
    continue
  }
  $secretLines = @(Get-Content -LiteralPath $secretPath)
  $keys = @(
    $secretLines | ForEach-Object {
      if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=') { $matches[1] }
    }
  )
  if ($secretSource) {
    $missing = @($keys | Where-Object { $secretKeys -notcontains $_ })
    if ($missing.Count -gt 0) {
      throw "Two secrets files: $secretSource is used, but $candidate holds keys it does not ($($missing -join ', ')). A stray $secretSource would deploy on compose defaults. Move the one you do not use into .xclude/, or merge them."
    }
    continue
  }
  # Docker reads the file as --env-file: KEY=value lines, no `export`, no spaces around `=`.
  for ($n = 0; $n -lt $secretLines.Count; $n++) {
    if ($secretLines[$n] -match '^\s*export\s' -or $secretLines[$n] -match '^\s*[A-Za-z_][A-Za-z0-9_]*\s+=') {
      throw "Secrets file $secretPath, line $($n + 1): write KEY=value, with no 'export' and no spaces around '=' (Docker reads this file with --env-file)."
    }
  }
  if ($keys.Count -eq 0) {
    throw "Secrets file contains no environment values: $secretPath"
  }
  $secretKeys = $keys
  $secretSource = $candidate
  $secretArgs = @(
    "--env-file", $secretPath,
    "-e", "COMPOSER_INHERITED_SECRET_KEYS=$($keys -join ',')"
  )
}

# The deployer sees only the project directory, so a Compose file linked from
# outside it cannot be read there.
$composeNames = @("compose.yml", "docker-compose.yml")
$composeNamed = ""
$composeDev = $false
for ($i = 0; $i -lt $args.Count; $i++) {
  $token = "$($args[$i])"
  if (($token -eq "-f" -or $token -eq "--file") -and $i + 1 -lt $args.Count) { $composeNamed = "$($args[$i + 1])"; $i++; continue }
  if ($token -like "--file=*") { $composeNamed = $token.Substring(7); continue }
  if ($token -eq "-d" -or $token -eq "--dev") { $composeDev = $true }
}
if ($composeNamed) { $composeNames = @($composeNamed) } elseif ($composeDev) { $composeNames += "compose.dev.yml" }
$projectPrefix = [System.IO.Path]::GetFullPath($projectRoot).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
foreach ($composeName in $composeNames) {
  $composePath = if ([System.IO.Path]::IsPathRooted($composeName)) { $composeName } else { Join-Path $projectRoot $composeName }
  $composeItem = Get-Item -LiteralPath $composePath -Force -ErrorAction SilentlyContinue
  if (-not $composeItem -or -not $composeItem.LinkType) { continue }
  $linkTarget = "$(@($composeItem.Target)[0])"
  if (-not [System.IO.Path]::IsPathRooted($linkTarget)) { $linkTarget = Join-Path (Split-Path -Parent $composePath) $linkTarget }
  $linkTarget = [System.IO.Path]::GetFullPath($linkTarget)
  if (-not $linkTarget.StartsWith($projectPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "$composeName is a symbolic link to $linkTarget, outside the project directory $projectRoot. The Composer container mounts only the project directory, so it cannot read that file: copy it into the project, or link to a file inside it."
  }
}

# Compose variables come from the secrets file only: one set in this shell
# never reaches Composer, so say so rather than deploy without it.
$shellOnly = @()
$ignoredVariables = @("HOME", "USER", "PATH", "PWD", "SHELL", "TERM", "HOSTNAME", "UID", "GID")
foreach ($composeName in $composeNames) {
  $composePath = if ([System.IO.Path]::IsPathRooted($composeName)) { $composeName } else { Join-Path $projectRoot $composeName }
  if (-not (Test-Path -LiteralPath $composePath -PathType Leaf)) { continue }
  $composeText = Get-Content -LiteralPath $composePath -Raw
  foreach ($match in [regex]::Matches("$composeText", '\$\{([A-Za-z_][A-Za-z0-9_]*)')) {
    $variable = $match.Groups[1].Value
    if ($variable -like "COMPOSER_*" -or $ignoredVariables -contains $variable) { continue }
    if ($secretKeys -contains $variable -or $shellOnly -contains $variable) { continue }
    if (Test-Path -LiteralPath "Env:$variable") { $shellOnly += $variable }
  }
}
if ($shellOnly.Count -gt 0) {
  $secretName = if ($secretSource) { $secretSource } else { "a secrets file" }
  $secretTarget = if ($secretSource) { $secretSource } else { ".secrets/.env" }
  [Console]::Error.WriteLine("Warning: $($shellOnly -join ', ') set in this shell, not in ${secretName}: Composer reads Compose variables from the secrets file only, so this run does not use the shell's value. Put it in $secretTarget to use it.")
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
    if ($LASTEXITCODE -ne 0) {
        [Console]::Error.WriteLine("The Composer pin could not be resolved with $resolver. If it printed only a usage line, that release predates this route: run '.\start.ps1 agent update', which moves the pin with the resident pair.")
        return $false
    }
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
