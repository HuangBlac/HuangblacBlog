$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "article-catalog-common.ps1")

$context = Get-ArticleCatalogContext $projectRoot
$catalogOutputPath = Join-Path $projectRoot "article-catalog.js"
$articleOutputPath = Join-Path $projectRoot "article-data.js"
$catalogJavaScript = Get-GeneratedCatalogJavaScript $context
$articleJavaScript = Get-GeneratedArticleDataJavaScript $context
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($catalogOutputPath, $catalogJavaScript, $utf8WithoutBom)
[System.IO.File]::WriteAllText($articleOutputPath, $articleJavaScript, $utf8WithoutBom)

Write-Output "Updated article-catalog.js and article-data.js from content/article-catalog.json"
