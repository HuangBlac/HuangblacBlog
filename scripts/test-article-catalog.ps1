$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "article-catalog-common.ps1")

$tempBoundary = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$testRoot = Join-Path $tempBoundary ("huangblac-catalog-tests-" + [System.Guid]::NewGuid().ToString("N"))
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)

function New-TestCatalog {
  return [ordered]@{
    sections = [ordered]@{
      buzz = [ordered]@{ label = "Buzz"; anchor = "index.html#buzz"; context = "Article archive" }
      creative = [ordered]@{ label = "Creative"; anchor = "index.html#creative"; context = "Creative archive" }
    }
    stages = @(
      [ordered]@{
        id = "finished"
        label = "Finished"
        eyebrow = "FINISHED"
        note = "Complete story."
        action = "Read"
        collapsed = $false
      }
    )
    series = @(
      [ordered]@{ id = "sample-series"; label = "SERIES"; title = "Sample series" }
    )
    creative = [ordered]@{ incompleteTitle = "Incomplete"; expandLabel = "Expand"; warning = "Test warning" }
    articles = @(
      [ordered]@{
        slug = "sample"
        content = "content/sample.md"
        section = "buzz"
        title = "Sample article"
        deck = "Sample deck"
        series = "sample-series"
        format = "markdown"
        order = 10
      },
      [ordered]@{
        slug = "sample-creative"
        content = "content/creative/sample-creative.md"
        section = "creative"
        title = "Sample creative"
        deck = "Sample deck"
        stage = "finished"
        format = "prose"
        order = 20
      }
    )
  }
}

function New-TestCase([string]$name, [scriptblock]$mutate) {
  $caseRoot = Join-Path $testRoot $name
  $contentRoot = Join-Path $caseRoot "content"
  $creativeRoot = Join-Path $contentRoot "creative"
  New-Item -ItemType Directory -Force -Path $creativeRoot | Out-Null
  [System.IO.File]::WriteAllText((Join-Path $contentRoot "sample.md"), "# Sample article`n", $utf8WithoutBom)
  [System.IO.File]::WriteAllText((Join-Path $creativeRoot "sample-creative.md"), "Sample creative`n", $utf8WithoutBom)

  $catalog = New-TestCatalog
  if ($mutate) {
    & $mutate $catalog $contentRoot
  }
  $catalogJson = $catalog | ConvertTo-Json -Depth 12
  [System.IO.File]::WriteAllText((Join-Path $contentRoot "article-catalog.json"), $catalogJson, $utf8WithoutBom)
  return $caseRoot
}

function Assert-CatalogPasses([string]$name, [scriptblock]$mutate = $null) {
  $caseRoot = New-TestCase $name $mutate
  $null = Get-ArticleCatalogContext $caseRoot
  Write-Output "PASS: $name"
}

function Assert-CatalogFails([string]$name, [scriptblock]$mutate, [string]$expectedMessage) {
  $caseRoot = New-TestCase $name $mutate
  try {
    $null = Get-ArticleCatalogContext $caseRoot
  } catch {
    if ($_.Exception.Message -notlike "*$expectedMessage*") {
      throw "FAIL: $name returned unexpected error: $($_.Exception.Message)"
    }
    Write-Output "PASS: $name"
    return
  }
  throw "FAIL: $name did not reject invalid catalog data."
}

try {
  Assert-CatalogPasses "valid-catalog"
  Assert-CatalogFails "duplicate-slug" {
    param($catalog)
    $catalog.articles += $catalog.articles[0]
  } "duplicate slug"
  Assert-CatalogFails "duplicate-order" {
    param($catalog)
    $catalog.articles[1].section = "buzz"
    $catalog.articles[1].order = 10
    $catalog.articles[1].PSObject.Properties.Remove("stage")
  } "duplicate article order"
  Assert-CatalogFails "missing-content" {
    param($catalog, $contentRoot)
    Remove-Item -LiteralPath (Join-Path $contentRoot "sample.md")
  } "content file is missing"
  Assert-CatalogFails "path-escape" {
    param($catalog)
    $catalog.articles[0].content = "../sample.md"
  } "escapes the content directory"
  Assert-CatalogFails "unknown-stage" {
    param($catalog)
    $catalog.articles[1].stage = "unknown"
  } "must use a known stage"
  Assert-CatalogFails "unlisted-content" {
    param($catalog, $contentRoot)
    [System.IO.File]::WriteAllText((Join-Path $contentRoot "orphan.md"), "Unlisted`n", $utf8WithoutBom)
  } "unlisted Markdown files"
} finally {
  $resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
  if (
    $resolvedTestRoot.StartsWith($tempBoundary, [System.StringComparison]::OrdinalIgnoreCase) -and
    [System.IO.Path]::GetFileName($resolvedTestRoot).StartsWith("huangblac-catalog-tests-", [System.StringComparison]::Ordinal)
  ) {
    Remove-Item -Recurse -Force -LiteralPath $resolvedTestRoot -ErrorAction SilentlyContinue
  }
}
