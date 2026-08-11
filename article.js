const articleCatalog = window.articleCatalog ?? {};
const catalogArticles = Array.isArray(articleCatalog.articles)
  ? [...articleCatalog.articles].sort((a, b) => a.order - b.order)
  : [];
const slug = new URLSearchParams(window.location.search).get("slug");
const article = catalogArticles.find((item) => item.slug === slug);
const section = articleCatalog.sections?.[article?.section];
const stage = articleCatalog.stages?.find((item) => item.id === article?.stage);
const markdown = window.articleContent?.[slug];
const titleElement = document.querySelector("[data-article-title]");
const kickerElement = document.querySelector("[data-article-kicker]");
const deckElement = document.querySelector("[data-article-deck]");
const dateElement = document.querySelector("[data-article-date]");
const bodyElement = document.querySelector("[data-article-body]");
const sourceLink = document.querySelector("[data-article-source]");
const sourceFooter = document.querySelector("[data-article-source-footer]");
const sourceNote = document.querySelector("[data-article-source-note]");
const backLinks = document.querySelectorAll("[data-article-back]");
const contextElement = document.querySelector("[data-article-context]");
const sectionNavLinks = document.querySelectorAll("[data-section-nav]");
const readerAside = document.querySelector("[data-reader-aside]");
const seriesSection = document.querySelector("[data-series-section]");
const seriesLabel = document.querySelector("[data-series-label]");
const seriesTitle = document.querySelector("[data-series-title]");
const seriesNav = document.querySelector("[data-series-nav]");

function setSectionContext() {
  sectionNavLinks.forEach((link) => {
    if (link.dataset.sectionNav === article?.section) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });

  if (!article || !section) {
    contextElement.textContent = "站内原文归档";
    readerAside.hidden = true;
    backLinks.forEach((link) => {
      link.href = "index.html";
      link.textContent = link.classList.contains("article-back")
        ? "← 返回首页"
        : "返回首页 ←";
    });
    return;
  }

  contextElement.textContent = section.context;
  backLinks.forEach((link) => {
    link.href = section.anchor;
    link.textContent = link.classList.contains("article-back")
      ? `← 返回${section.label}`
      : `返回${section.label} ←`;
  });

  if (article.section === "creative") {
    document.body.classList.add("creative-article");
    readerAside.hidden = true;
  }
}

function renderSeries() {
  if (!article?.series) return;
  const series = articleCatalog.series?.find((item) => item.id === article.series);
  if (!series) return;

  const relatedArticles = catalogArticles.filter((item) => item.series === series.id);
  seriesLabel.textContent = series.label;
  seriesTitle.textContent = series.title;
  seriesNav.replaceChildren(
    ...relatedArticles.map((item) => {
      const link = document.createElement("a");
      link.href = `article.html?slug=${encodeURIComponent(item.slug)}`;
      link.textContent = item.title;
      if (item.slug === article.slug) link.setAttribute("aria-current", "page");
      return link;
    }),
  );
  seriesSection.hidden = false;
}

setSectionContext();
renderSeries();

if (!article || typeof markdown !== "string") {
  const destination = article && section
    ? { href: section.anchor, label: section.label }
    : { href: "index.html", label: "首页" };

  document.title = "文章不存在｜小黑的晓店";
  titleElement.textContent = "没有找到这篇文章";
  kickerElement.textContent = "404 / NOT FOUND";
  deckElement.textContent = "这个站内文章地址可能已经改变。";
  dateElement.textContent = "";
  bodyElement.replaceChildren();
  const message = document.createElement("p");
  const backLink = document.createElement("a");
  message.textContent = `请返回${destination.label}重新选择文章。`;
  backLink.href = destination.href;
  backLink.textContent = `返回${destination.label} →`;
  bodyElement.append(message, backLink);
  sourceFooter.hidden = true;
} else {
  document.title = `${article.title}｜小黑的晓店`;
  titleElement.textContent = article.title;
  kickerElement.textContent = article.kicker ?? `娱乐创作 / ${stage?.label ?? "创作"}`;
  deckElement.textContent = article.deck;
  dateElement.textContent = article.date ?? stage?.label ?? "";
  if (article.source?.url) {
    sourceLink.href = article.source.url;
    sourceLink.textContent = `前往${article.source.label} ↗`;
    sourceNote.textContent = section.sourceNote;
    sourceFooter.hidden = false;
  } else {
    sourceFooter.hidden = true;
  }
  bodyElement.replaceChildren(renderMarkdown(markdown, article.title, article.format === "prose"));
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderInline(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
      '<a href="$2" target="_blank" rel="noreferrer">$1</a>',
    );
}

function isBlockStart(line) {
  const trimmed = line.trim();
  return (
    /^#{1,3}\s+/.test(trimmed) ||
    /^>\s?/.test(trimmed) ||
    /^[-*]\s+/.test(trimmed) ||
    /^\d+\.\s+/.test(trimmed) ||
    trimmed.startsWith("```")
  );
}

function renderMarkdown(source, articleTitle, preserveSourceParagraphs = false) {
  const fragment = document.createDocumentFragment();
  const lines = source.replace(/^\uFEFF/, "").replaceAll("\r\n", "\n").split("\n");
  const firstContentLine = lines.findIndex((line) => line.trim());

  if (firstContentLine >= 0) {
    const possibleTitle = lines[firstContentLine].replace(/^#\s*/, "").trim();
    if (possibleTitle === articleTitle) lines[firstContentLine] = "";
  }

  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const codeLines = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      code.textContent = codeLines.join("\n");
      pre.append(code);
      fragment.append(pre);
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      const heading = document.createElement(`h${Math.min(headingMatch[1].length + 1, 4)}`);
      heading.innerHTML = renderInline(headingMatch[2]);
      fragment.append(heading);
      index += 1;
      continue;
    }

    if (/^>\s?/.test(trimmed)) {
      const quoteLines = [];
      while (index < lines.length && /^>\s?/.test(lines[index].trim())) {
        quoteLines.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      const quote = document.createElement("blockquote");
      quote.innerHTML = renderInline(quoteLines.join(" "));
      fragment.append(quote);
      continue;
    }

    const unordered = /^[-*]\s+/.test(trimmed);
    const ordered = /^\d+\.\s+/.test(trimmed);
    if (unordered || ordered) {
      const list = document.createElement(ordered ? "ol" : "ul");
      const pattern = ordered ? /^\d+\.\s+/ : /^[-*]\s+/;
      while (index < lines.length && pattern.test(lines[index].trim())) {
        const item = document.createElement("li");
        item.innerHTML = renderInline(lines[index].trim().replace(pattern, ""));
        list.append(item);
        index += 1;
      }
      fragment.append(list);
      continue;
    }

    const paragraphLines = [trimmed];
    index += 1;
    while (
      !preserveSourceParagraphs &&
      index < lines.length &&
      lines[index].trim() &&
      !isBlockStart(lines[index])
    ) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    const paragraph = document.createElement("p");
    paragraph.innerHTML = renderInline(paragraphLines.join(" "));
    fragment.append(paragraph);
  }

  return fragment;
}
