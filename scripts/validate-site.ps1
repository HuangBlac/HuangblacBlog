param(
  [string]$SiteRoot = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if (-not $SiteRoot) {
  $SiteRoot = Join-Path $projectRoot "dist"
} elseif (-not [System.IO.Path]::IsPathRooted($SiteRoot)) {
  $SiteRoot = Join-Path $projectRoot $SiteRoot
}

$resolvedSiteRoot = [System.IO.Path]::GetFullPath($SiteRoot)
if (-not (Test-Path -LiteralPath $resolvedSiteRoot -PathType Container)) {
  throw "Site output does not exist: $resolvedSiteRoot"
}

$requiredFiles = @(
  "index.html",
  "404.html",
  "robots.txt",
  "sitemap.xml",
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
  "gaosongdeng-cup.html",
  "gaosongdeng-cup.css",
  "assets/favicon-32.png",
  "assets/apple-touch-icon.png",
  ".nojekyll"
)

foreach ($fileName in $requiredFiles) {
  $path = Join-Path $resolvedSiteRoot $fileName
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
    throw "Built site is missing '$fileName'."
  }
}

$unexpectedFiles = Get-ChildItem -LiteralPath $resolvedSiteRoot -Recurse -File | Where-Object {
  $_.Extension -in @(".md", ".ps1") -or $_.Name -in @("README.md", ".gitignore")
}
if ($unexpectedFiles) {
  throw "Build output contains source-only files: $($unexpectedFiles.FullName -join ', ')"
}

$privateName = [string]([char]0x9EC4) + [char]0x5357 + [char]0x6A35
$forbiddenText = @(
  $privateName,
  "C:\Users\",
  "AppData",
  "ZHIHU_ACCESS_SECRET",
  "Access Secret",
  "chatgpt.com/g/",
  "ChatGPT Exporter",
  "PSPath",
  "PSParentPath"
)

$textFiles = Get-ChildItem -LiteralPath $resolvedSiteRoot -Recurse -File | Where-Object {
  $_.Extension -in @(".html", ".css", ".js", ".json", ".txt")
}

foreach ($file in $textFiles) {
  $content = [System.IO.File]::ReadAllText($file.FullName, [System.Text.Encoding]::UTF8)
  foreach ($needle in $forbiddenText) {
    if ($content.Contains($needle)) {
      throw "Forbidden private text '$needle' found in '$($file.Name)'."
    }
  }
}

$siteBoundary = $resolvedSiteRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
$htmlFiles = Get-ChildItem -LiteralPath $resolvedSiteRoot -Recurse -Filter "*.html" -File

foreach ($htmlFile in $htmlFiles) {
  $html = [System.IO.File]::ReadAllText($htmlFile.FullName, [System.Text.Encoding]::UTF8)
  $references = [regex]::Matches($html, '(?:href|src)="([^"]+)"')

  foreach ($reference in $references) {
    $target = [System.Net.WebUtility]::HtmlDecode($reference.Groups[1].Value)
    if (
      $target.StartsWith("#") -or
      $target.StartsWith("https://") -or
      $target.StartsWith("mailto:") -or
      $target.StartsWith("tel:") -or
      $target.StartsWith("data:")
    ) {
      continue
    }

    if ($target.StartsWith("http://")) {
      throw "Insecure external link '$target' in '$($htmlFile.Name)'."
    }

    $localTarget = ($target -split '[?#]', 2)[0]
    if (-not $localTarget) {
      continue
    }

    $resolvedTarget = [System.IO.Path]::GetFullPath((Join-Path $htmlFile.DirectoryName $localTarget))
    if (
      $resolvedTarget -ne $resolvedSiteRoot -and
      -not $resolvedTarget.StartsWith($siteBoundary, [System.StringComparison]::OrdinalIgnoreCase)
    ) {
      throw "Local reference escapes the site root: '$target'."
    }

    if (-not (Test-Path -LiteralPath $resolvedTarget)) {
      throw "Broken local reference '$target' in '$($htmlFile.Name)'."
    }
  }
}

$catalog = (Get-Content -Raw -Encoding UTF8 (Join-Path $projectRoot "content/article-catalog.json")) | ConvertFrom-Json
$articlePages = Get-ChildItem -LiteralPath (Join-Path $resolvedSiteRoot "article") -Recurse -Filter "index.html" -File
if ($articlePages.Count -ne $catalog.articles.Count) {
  throw "Built site contains $($articlePages.Count) static article pages; expected $($catalog.articles.Count)."
}

$sitemap = [System.IO.File]::ReadAllText((Join-Path $resolvedSiteRoot "sitemap.xml"), [System.Text.Encoding]::UTF8)
$eventUrl = "https://huangblac.com/gaosongdeng-cup.html"
if (-not $sitemap.Contains("<loc>$eventUrl</loc>")) {
  throw "Sitemap is missing event URL '$eventUrl'."
}
$eventHtml = [System.IO.File]::ReadAllText((Join-Path $resolvedSiteRoot "gaosongdeng-cup.html"), [System.Text.Encoding]::UTF8)
foreach ($requiredFragment in @(
  "<link rel=`"canonical`" href=`"$eventUrl`">",
  "<meta property=`"og:url`" content=`"$eventUrl`">",
  '<meta name="description" content="',
  '<meta property="og:title" content="',
  '<meta property="og:description" content="',
  '<meta property="og:image" content="',
  '<meta name="twitter:card" content="summary">',
  '<meta name="twitter:title" content="',
  '<meta name="twitter:description" content="',
  '<meta name="twitter:image" content="',
  '<link rel="icon" href="assets/favicon-32.png"',
  '<link rel="apple-touch-icon" href="assets/apple-touch-icon.png"'
)) {
  if (-not $eventHtml.Contains($requiredFragment)) {
    throw "Static event page is missing required metadata: $requiredFragment"
  }
}
foreach ($requiredFragment in @(
  '2026-11-22T00:00:00+08:00',
  'huangblac@gmail.com',
  '1239256942@qq.com',
  'https://github.com/HuangBlac/TomoriCup',
  '68.6'
)) {
  if (-not $eventHtml.Contains($requiredFragment)) {
    throw "Static event page is missing an agreed rule: $requiredFragment"
  }
}
foreach ($requiredPattern in @(
  '\u6b63\u5f0f\u5f81\u96c6\u901a\u544a',
  '\u5b8c\u6210\u5ea6\u5360 50 \u5206',
  '\u53ef\u4f53\u9a8c\u4e0e\u53ef\u68c0\u9a8c\u7a0b\u5ea6\u5360 30 \u5206',
  '\u60f3\u6cd5\u5360 20 \u5206',
  '\u7b2c\u4e09\u5341\u516d\u5c4a\u5168\u56fd\u9ad8\u677e\u706f\u676f\u9ed1\u5ba2\u677e\u7ade\u8d5b\u51a0\u519b',
  '\u6295\u7a3f\u5373\u6388\u6743'
)) {
  if (-not [regex]::IsMatch($eventHtml, $requiredPattern)) {
    throw "Static event page is missing an agreed rule matching: $requiredPattern"
  }
}
foreach ($obsoletePattern in @(
  '2000\u5b57',
  '\u91d1\u989d\u5f85\u516c\u5e03',
  '\u5c1a\u672a\u5f00\u653e\u6295\u7a3f',
  '\u6d3b\u52a8\u9884\u544a'
)) {
  if ([regex]::IsMatch($eventHtml, $obsoletePattern)) {
    throw "Static event page contains obsolete copy matching: $obsoletePattern"
  }
}
$homeHtml = [System.IO.File]::ReadAllText((Join-Path $resolvedSiteRoot "index.html"), [System.Text.Encoding]::UTF8)
if (-not $homeHtml.Contains('href="gaosongdeng-cup.html"') -or -not [regex]::IsMatch($homeHtml, '\u9605\u8bfb\u6b63\u5f0f\u5f81\u96c6\u901a\u544a')) {
  throw "Homepage does not link to the formal event notice."
}
foreach ($article in $catalog.articles) {
  $expectedUrl = "https://huangblac.com/article/$($article.slug)/"
  if (-not $sitemap.Contains("<loc>$expectedUrl</loc>")) {
    throw "Sitemap is missing article URL '$expectedUrl'."
  }

  $articlePage = Join-Path $resolvedSiteRoot "article/$($article.slug)/index.html"
  $articleHtml = [System.IO.File]::ReadAllText($articlePage, [System.Text.Encoding]::UTF8)
  foreach ($requiredFragment in @(
    "<meta property=`"og:title`" content=`"",
    "<meta property=`"og:description`" content=`"",
    "<meta property=`"og:url`" content=`"$expectedUrl`">",
    "<link rel=`"canonical`" href=`"$expectedUrl`">",
    '<script type="application/ld+json" data-article-schema>',
    'data-article-share',
    'data-article-share-status'
  )) {
    if (-not $articleHtml.Contains($requiredFragment)) {
      throw "Static article page '$($article.slug)' is missing required metadata: $requiredFragment"
    }
  }
}

$publicCatalog = [System.IO.File]::ReadAllText((Join-Path $resolvedSiteRoot "article-catalog.js"), [System.Text.Encoding]::UTF8)
if ($publicCatalog.Contains('"content"')) {
  throw "Public article catalog still exposes source-only content paths."
}

Write-Output "Validated static site ($($textFiles.Count) text files, $($htmlFiles.Count) HTML files)."
