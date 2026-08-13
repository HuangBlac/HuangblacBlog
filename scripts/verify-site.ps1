param(
  [string]$OutputPath = "dist"
)

$ErrorActionPreference = "Stop"

if (
  [System.IO.Path]::IsPathRooted($OutputPath) -or
  [System.IO.Path]::GetFileName($OutputPath) -cne $OutputPath -or
  $OutputPath -notmatch '^dist(?:-[a-z0-9][a-z0-9-]*)?$'
) {
  throw "OutputPath must be a project-root directory named 'dist' or 'dist-*'."
}

function Invoke-VerificationStep([string]$label, [scriptblock]$action) {
  Write-Output "==> $label"
  & $action
}

Invoke-VerificationStep "Test article catalog" {
  & (Join-Path $PSScriptRoot "test-article-catalog.ps1")
}

Invoke-VerificationStep "Build static site" {
  & (Join-Path $PSScriptRoot "build-site.ps1") -OutputPath $OutputPath
}

Invoke-VerificationStep "Validate deployment artifact" {
  & (Join-Path $PSScriptRoot "validate-site.ps1") -SiteRoot $OutputPath
}

Write-Output "Site verification completed successfully."
