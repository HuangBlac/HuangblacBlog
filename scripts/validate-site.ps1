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
  "styles.css",
  "script.js",
  "site-data.js",
  "article.html",
  "article.css",
  "article.js",
  "article-data.js",
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

Write-Output "Validated static site ($($textFiles.Count) text files, $($htmlFiles.Count) HTML files)."
