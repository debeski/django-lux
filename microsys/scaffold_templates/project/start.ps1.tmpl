Set-StrictMode -Version Latest

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

docker pull debeski/decrypter:compose *> $null

docker run -it --rm `
  -v "${projectRoot}:${containerRoot}" `
  -w "${containerRoot}" `
  -v /var/run/docker.sock:/var/run/docker.sock `
  debeski/decrypter:compose @args
