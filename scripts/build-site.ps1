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
  "article-data.js",
  "article-catalog.js",
  "caidan.js"
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
  "404.html",
  "robots.txt",
  "styles.css",
  "script.js",
  "site-data.js",
  "article.html",
  "article.css",
  "article.js",
  "article-data.js",
  "article-catalog.js",
  "caidan.html",
  "caidan.js",
  "after-hours.html",
  "assets/huangblac-avatar-512.png",
  "assets/favicon-32.png",
  "assets/apple-touch-icon.png"
)

foreach ($fileName in $publicFiles) {
  $sourcePath = Join-Path $projectRoot $fileName
  if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    throw "Required public file is missing: $fileName"
  }
  $destinationPath = Join-Path $resolvedOutput $fileName
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destinationPath) | Out-Null
  Copy-Item -LiteralPath $sourcePath -Destination $destinationPath
}

$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)

function ConvertTo-HtmlAttribute([string]$value) {
  return [System.Net.WebUtility]::HtmlEncode($value)
}

function Set-HeadValue([string]$html, [string]$pattern, [string]$replacement) {
  return [regex]::Replace($html, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($match) $replacement }, 1)
}

$siteUrl = "https://huangblac.com"
$siteName = -join ([char]0x5C0F, [char]0x9ED1, [char]0x7684, [char]0x6653, [char]0x5E97)
$authorName = -join ([char]0x9EC4, [char]0x6653, [char]0x9ED1)
$articleTemplate = [System.IO.File]::ReadAllText((Join-Path $projectRoot "article.html"), [System.Text.Encoding]::UTF8)
$catalog = (Get-Content -Raw -Encoding UTF8 (Join-Path $projectRoot "content/article-catalog.json")) | ConvertFrom-Json
$sitemapUrls = New-Object System.Collections.Generic.List[string]
$sitemapUrls.Add("$siteUrl/")

foreach ($article in $catalog.articles) {
  $articleUrl = "$siteUrl/article/$($article.slug)/"
  $pageTitle = "$(ConvertTo-HtmlAttribute $article.title)$([char]0xFF5C)$siteName"
  $description = ConvertTo-HtmlAttribute $article.deck
  $schema = [ordered]@{
    "@context" = "https://schema.org"
    "@type" = "Article"
    headline = [string]$article.title
    description = [string]$article.deck
    author = [ordered]@{ "@type" = "Person"; name = $authorName }
    publisher = [ordered]@{ "@type" = "Person"; name = $authorName }
    image = "$siteUrl/assets/huangblac-avatar-512.png"
    mainEntityOfPage = $articleUrl
  }
  if ($article.datePublished) {
    $schema.datePublished = [string]$article.datePublished
  }
  $schemaJson = ($schema | ConvertTo-Json -Depth 5 -Compress).Replace("<", "\u003c").Replace(">", "\u003e")

  $html = $articleTemplate
  $html = Set-HeadValue $html '<meta name="description" content="[^"]*">' "<meta name=`"description`" content=`"$description`">"
  $html = Set-HeadValue $html '<meta property="og:title" content="[^"]*">' "<meta property=`"og:title`" content=`"$pageTitle`">"
  $html = Set-HeadValue $html '<meta property="og:description" content="[^"]*">' "<meta property=`"og:description`" content=`"$description`">"
  $html = Set-HeadValue $html '<meta property="og:url" content="[^"]*">' "<meta property=`"og:url`" content=`"$articleUrl`">"
  $html = Set-HeadValue $html '<meta name="twitter:title" content="[^"]*">' "<meta name=`"twitter:title`" content=`"$pageTitle`">"
  $html = Set-HeadValue $html '<meta name="twitter:description" content="[^"]*">' "<meta name=`"twitter:description`" content=`"$description`">"
  $html = Set-HeadValue $html '<title>[^<]*</title>' "<title>$pageTitle</title>"
  $html = Set-HeadValue $html '<link rel="canonical" href="[^"]*">' "<link rel=`"canonical`" href=`"$articleUrl`">"
  $html = Set-HeadValue $html '<script type="application/ld\+json" data-article-schema>.*?</script>' "<script type=`"application/ld+json`" data-article-schema>$schemaJson</script>"
  $html = $html.Replace('href="assets/', 'href="../../assets/').Replace('href="styles.css"', 'href="../../styles.css"').Replace('href="article.css"', 'href="../../article.css"')
  $html = $html.Replace('href="index.html', 'href="../../index.html').Replace('src="article-', 'src="../../article-').Replace('src="article.js"', 'src="../../article.js"')

  $articleOutput = Join-Path $resolvedOutput "article/$($article.slug)/index.html"
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $articleOutput) | Out-Null
  [System.IO.File]::WriteAllText($articleOutput, $html, $utf8WithoutBom)
  $sitemapUrls.Add($articleUrl)
}

$sitemapEntries = $sitemapUrls | ForEach-Object { "  <url><loc>$([System.Security.SecurityElement]::Escape($_))</loc></url>" }
$sitemap = @(
  '<?xml version="1.0" encoding="UTF-8"?>'
  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
  $sitemapEntries
  '</urlset>'
) -join "`n"
[System.IO.File]::WriteAllText((Join-Path $resolvedOutput "sitemap.xml"), "$sitemap`n", $utf8WithoutBom)

[System.IO.File]::WriteAllText((Join-Path $resolvedOutput ".nojekyll"), "", $utf8WithoutBom)

Write-Output "Built static site at $resolvedOutput"
