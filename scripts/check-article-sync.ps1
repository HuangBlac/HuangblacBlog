$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$contentRoot = Join-Path $projectRoot "content"
$dataPath = Join-Path $projectRoot "article-data.js"

$articles = [ordered]@{
  "math-to-ai-courses" = "math-to-ai-courses.md"
  "math-to-cs" = "math-to-cs.md"
  "math-outlook" = "math-outlook.md"
  "math-interdisciplinary" = "math-interdisciplinary.md"
}

function Normalize-Article([string]$value) {
  return $value.Replace("`r`n", "`n").TrimEnd()
}

$javascript = [System.IO.File]::ReadAllText($dataPath, [System.Text.Encoding]::UTF8)
$prefix = "window.articleContent = "

if (-not $javascript.StartsWith($prefix, [System.StringComparison]::Ordinal)) {
  throw "article-data.js does not start with the expected assignment."
}

$json = $javascript.Substring($prefix.Length).Trim()
if ($json.EndsWith(";", [System.StringComparison]::Ordinal)) {
  $json = $json.Substring(0, $json.Length - 1)
}

$embedded = $json | ConvertFrom-Json
$expectedSlugs = @($articles.Keys | Sort-Object)
$actualSlugs = @($embedded.PSObject.Properties | ForEach-Object { $_.Name } | Sort-Object)
$slugDiff = Compare-Object -ReferenceObject $expectedSlugs -DifferenceObject $actualSlugs

if ($slugDiff) {
  throw "article-data.js contains missing or unexpected article slugs."
}

foreach ($slug in $articles.Keys) {
  $sourcePath = Join-Path $contentRoot $articles[$slug]
  $source = [System.IO.File]::ReadAllText($sourcePath, [System.Text.Encoding]::UTF8)
  $embeddedArticle = [string]$embedded.PSObject.Properties[$slug].Value

  if ((Normalize-Article $source) -cne (Normalize-Article $embeddedArticle)) {
    throw "article-data.js is out of sync for '$slug'. Run scripts/sync-article-data.ps1."
  }
}

Write-Output "Article data is synchronized ($($articles.Count) articles)."
