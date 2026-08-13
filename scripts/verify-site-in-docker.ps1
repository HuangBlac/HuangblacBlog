param(
  [string]$ImageName = "huangblac-blog-ci:local",
  [string]$OutputPath = "dist-docker"
)

$ErrorActionPreference = "Stop"

$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$dockerfile = Join-Path $projectRoot "Dockerfile.ci"
$docker = Get-Command docker -ErrorAction Stop

if (
  [System.IO.Path]::IsPathRooted($OutputPath) -or
  [System.IO.Path]::GetFileName($OutputPath) -cne $OutputPath -or
  $OutputPath -notmatch '^dist(?:-[a-z0-9][a-z0-9-]*)?$'
) {
  throw "OutputPath must be a project-root directory named 'dist' or 'dist-*'."
}

Write-Output "==> Build fixed CI image"
& $docker.Source build --file $dockerfile --tag $ImageName $projectRoot
if ($LASTEXITCODE -ne 0) {
  throw "Docker image build failed with exit code $LASTEXITCODE."
}

Write-Output "==> Verify site in Linux container"
$mount = "type=bind,source=$projectRoot,target=/workspace"
$runArguments = @("run", "--rm", "--mount", $mount, "--workdir", "/workspace")
if ($PSVersionTable.Platform -eq "Unix") {
  $uid = (& id -u).Trim()
  $gid = (& id -g).Trim()
  if ($LASTEXITCODE -ne 0 -or -not $uid -or -not $gid) {
    throw "Unable to determine the current Unix user for Docker output ownership."
  }
  $runArguments += @("--user", "${uid}:${gid}")
}
$runArguments += @($ImageName, "-OutputPath", $OutputPath)

& $docker.Source @runArguments
if ($LASTEXITCODE -ne 0) {
  throw "Docker site verification failed with exit code $LASTEXITCODE."
}

Write-Output "Docker site verification completed successfully."
