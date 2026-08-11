param(
  [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if (-not $OutputPath) {
  $OutputPath = Join-Path $projectRoot "dist"
} elseif (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
  $OutputPath = Join-Path $projectRoot $OutputPath
}

$resolvedOutput = [System.IO.Path]::GetFullPath($OutputPath)
$projectBoundary = $projectRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

if (
  $resolvedOutput -eq $projectRoot -or
  -not $resolvedOutput.StartsWith($projectBoundary, [System.StringComparison]::OrdinalIgnoreCase)
) {
  throw "Build output must be a child directory of the project root."
}

& (Join-Path $PSScriptRoot "check-article-sync.ps1")

$javascriptFiles = @(
  "script.js",
  "site-data.js",
  "article.js",
  "article-data.js"
)

$node = Get-Command node -ErrorAction Stop
foreach ($fileName in $javascriptFiles) {
  & $node.Source --check (Join-Path $projectRoot $fileName)
  if ($LASTEXITCODE -ne 0) {
    throw "JavaScript syntax check failed for '$fileName'."
  }
}

if (Test-Path -LiteralPath $resolvedOutput) {
  Remove-Item -Recurse -Force -LiteralPath $resolvedOutput
}
New-Item -ItemType Directory -Path $resolvedOutput | Out-Null

$publicFiles = @(
  "index.html",
  "styles.css",
  "script.js",
  "site-data.js",
  "article.html",
  "article.css",
  "article.js",
  "article-data.js"
)

foreach ($fileName in $publicFiles) {
  $sourcePath = Join-Path $projectRoot $fileName
  if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    throw "Required public file is missing: $fileName"
  }
  Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $resolvedOutput $fileName)
}

$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $resolvedOutput ".nojekyll"), "", $utf8WithoutBom)

Write-Output "Built static site at $resolvedOutput"
