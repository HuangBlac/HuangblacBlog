$ErrorActionPreference = "Stop"

function Get-ArticleCatalogContext([string]$projectRoot) {
  $resolvedProjectRoot = [System.IO.Path]::GetFullPath($projectRoot)
  $contentRoot = Join-Path $resolvedProjectRoot "content"
  $contentBoundary = $contentRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
  $catalogPath = Join-Path $contentRoot "article-catalog.json"

  if (-not (Test-Path -LiteralPath $catalogPath -PathType Leaf)) {
    throw "Article catalog is missing: content/article-catalog.json"
  }

  $catalogJson = [System.IO.File]::ReadAllText($catalogPath, [System.Text.Encoding]::UTF8)
  try {
    $catalog = $catalogJson | ConvertFrom-Json
  } catch {
    throw "Article catalog is not valid JSON: $($_.Exception.Message)"
  }

  if (-not $catalog.sections -or -not $catalog.stages -or -not $catalog.series -or -not $catalog.articles) {
    throw "Article catalog must define sections, stages, series, and articles."
  }

  $sectionIds = @($catalog.sections.PSObject.Properties | ForEach-Object { $_.Name })
  if (-not $sectionIds.Count) {
    throw "Article catalog must define at least one section."
  }
  foreach ($sectionProperty in $catalog.sections.PSObject.Properties) {
    if (-not $sectionProperty.Value.label -or -not $sectionProperty.Value.anchor -or -not $sectionProperty.Value.context) {
      throw "Section '$($sectionProperty.Name)' must define label, anchor, and context."
    }
  }

  $stageIds = @($catalog.stages | ForEach-Object { [string]$_.id })
  $duplicateStageIds = @($stageIds | Group-Object | Where-Object { $_.Count -gt 1 })
  if ($duplicateStageIds) {
    throw "Article catalog contains duplicate stage ids: $($duplicateStageIds.Name -join ', ')"
  }

  foreach ($stage in $catalog.stages) {
    if (-not $stage.id -or -not $stage.label -or -not $stage.eyebrow -or -not $stage.note -or -not $stage.action) {
      throw "Every article stage must define id, label, eyebrow, note, and action."
    }
    if ($stage.collapsed -isnot [bool]) {
      throw "Article stage '$($stage.id)' must define collapsed as a boolean."
    }
  }

  if ($sectionIds -contains "creative") {
    if (
      -not $catalog.creative -or
      -not $catalog.creative.incompleteTitle -or
      -not $catalog.creative.expandLabel -or
      -not $catalog.creative.warning
    ) {
      throw "Creative catalog settings must define incompleteTitle, expandLabel, and warning."
    }
  }

  $seriesIds = @($catalog.series | ForEach-Object { [string]$_.id })
  $duplicateSeriesIds = @($seriesIds | Group-Object | Where-Object { $_.Count -gt 1 })
  if ($duplicateSeriesIds) {
    throw "Article catalog contains duplicate series ids: $($duplicateSeriesIds.Name -join ', ')"
  }
  foreach ($series in $catalog.series) {
    if (-not $series.id -or -not $series.label -or -not $series.title) {
      throw "Every article series must define id, label, and title."
    }
  }

  $slugSet = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
  $contentSet = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
  $orderSet = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
  $articlePaths = [ordered]@{}

  foreach ($article in $catalog.articles) {
    $slug = [string]$article.slug
    $relativeContent = [string]$article.content
    $section = [string]$article.section
    $format = [string]$article.format

    if (-not $slug -or $slug -notmatch '^[a-z0-9]+(?:-[a-z0-9]+)*$') {
      throw "Article slug '$slug' must use lowercase letters, numbers, and hyphens."
    }
    if (-not $slugSet.Add($slug)) {
      throw "Article catalog contains duplicate slug '$slug'."
    }
    if (-not $relativeContent) {
      throw "Article '$slug' does not define a content path."
    }
    if (-not $article.title -or -not $article.deck) {
      throw "Article '$slug' must define a title and deck."
    }
    if ($section -notin $sectionIds) {
      throw "Article '$slug' uses unknown section '$section'."
    }
    if ($format -notin @("markdown", "prose")) {
      throw "Article '$slug' uses unsupported format '$format'."
    }
    if ($null -eq $article.order -or -not ($article.order -is [ValueType]) -or $article.order -is [bool]) {
      throw "Article '$slug' must define a numeric order."
    }
    $orderKey = "$section`:$($article.order)"
    if (-not $orderSet.Add($orderKey)) {
      throw "Section '$section' contains duplicate article order '$($article.order)'."
    }

    if ($section -eq "creative") {
      if (-not $article.stage -or [string]$article.stage -notin $stageIds) {
        throw "Creative article '$slug' must use a known stage."
      }
    } elseif ($article.stage) {
      throw "Non-creative article '$slug' must not define a creative stage."
    }

    if ($article.series -and [string]$article.series -notin $seriesIds) {
      throw "Article '$slug' uses unknown series '$($article.series)'."
    }
    if ($article.source) {
      if (-not $article.source.label -or -not ([string]$article.source.url).StartsWith("https://", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Article '$slug' must use an HTTPS source URL and a source label."
      }
    }

    $contentPath = [System.IO.Path]::GetFullPath((Join-Path $resolvedProjectRoot $relativeContent))
    if (-not $contentPath.StartsWith($contentBoundary, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Article '$slug' content path escapes the content directory."
    }
    if ([System.IO.Path]::GetExtension($contentPath) -ne ".md") {
      throw "Article '$slug' content path must point to a Markdown file."
    }
    if ([System.IO.Path]::GetFileNameWithoutExtension($contentPath) -cne $slug) {
      throw "Article '$slug' content filename must match its slug."
    }
    if (-not (Test-Path -LiteralPath $contentPath -PathType Leaf)) {
      throw "Article '$slug' content file is missing: $relativeContent"
    }
    if (-not $contentSet.Add($contentPath)) {
      throw "Multiple catalog entries reference the same content file: $relativeContent"
    }

    $articlePaths[$slug] = $contentPath
  }

  $unlistedFiles = Get-ChildItem -LiteralPath $contentRoot -Recurse -Filter "*.md" -File | Where-Object {
    -not $contentSet.Contains($_.FullName)
  }
  if ($unlistedFiles) {
    $relativeFiles = $unlistedFiles | ForEach-Object {
      $_.FullName.Substring($resolvedProjectRoot.Length + 1).Replace("\", "/")
    }
    throw "Content directory contains unlisted Markdown files: $($relativeFiles -join ', ')"
  }

  return [pscustomobject]@{
    Catalog = $catalog
    CatalogJson = $catalogJson.Trim()
    ArticlePaths = $articlePaths
  }
}

function Get-ArticleContentMap($context) {
  $articles = [ordered]@{}
  foreach ($slug in $context.ArticlePaths.Keys) {
    $articles[$slug] = [System.IO.File]::ReadAllText(
      $context.ArticlePaths[$slug],
      [System.Text.Encoding]::UTF8
    )
  }
  return $articles
}

function Get-GeneratedCatalogJavaScript($context) {
  return "window.articleCatalog = $($context.CatalogJson);`n"
}

function Get-GeneratedArticleDataJavaScript($context) {
  $articles = Get-ArticleContentMap $context
  # Windows PowerShell 5.1 and PowerShell 7 differ in indentation and HTML
  # character escaping. Compact output plus explicit escaping keeps the
  # generated browser data byte-for-byte portable across both runtimes.
  $json = $articles | ConvertTo-Json -Depth 4 -Compress
  $json = $json.Replace("&", "\u0026")
  $json = $json.Replace("'", "\u0027")
  $json = $json.Replace("<", "\u003c")
  $json = $json.Replace(">", "\u003e")
  return "window.articleContent = $json;`n"
}

function Normalize-GeneratedText([string]$value) {
  return $value.Replace("`r`n", "`n").TrimEnd()
}
