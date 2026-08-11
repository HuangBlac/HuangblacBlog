$projectRoot = Split-Path -Parent $PSScriptRoot
$contentRoot = Join-Path $projectRoot "content"
$outputPath = Join-Path $projectRoot "article-data.js"

function Read-Article([string]$fileName) {
  $path = Join-Path $contentRoot $fileName
  return [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
}

$articles = [ordered]@{
  "math-to-ai-courses" = Read-Article "math-to-ai-courses.md"
  "math-to-cs" = Read-Article "math-to-cs.md"
  "math-outlook" = Read-Article "math-outlook.md"
  "math-interdisciplinary" = Read-Article "math-interdisciplinary.md"
}

$json = $articles | ConvertTo-Json -Depth 3
$javascript = "window.articleContent = $json;`n"
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($outputPath, $javascript, $utf8WithoutBom)

Write-Output "Updated article-data.js from content/*.md"
