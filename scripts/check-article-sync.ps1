$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "article-catalog-common.ps1")

$context = Get-ArticleCatalogContext $projectRoot
$expectedFiles = [ordered]@{
  "article-catalog.js" = Get-GeneratedCatalogJavaScript $context
  "article-data.js" = Get-GeneratedArticleDataJavaScript $context
}

foreach ($fileName in $expectedFiles.Keys) {
  $path = Join-Path $projectRoot $fileName
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
    throw "Generated article file is missing: $fileName"
  }

  $actual = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
  if ((Normalize-GeneratedText $actual) -cne (Normalize-GeneratedText $expectedFiles[$fileName])) {
    throw "$fileName is out of sync. Run scripts/sync-article-data.ps1."
  }
}

Write-Output "Article catalog and content are synchronized ($($context.ArticlePaths.Count) articles)."
