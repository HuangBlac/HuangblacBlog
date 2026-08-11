const articleManifest = {
  "math-to-ai-courses": {
    title: "数学系转人工智能需要选计算机相关课程吗？",
    kicker: "人工智能选课 / 知乎回答",
    deck: "从“小转”与“大转”两条路径出发，讨论数学系学生应该补哪些计算机课程，以及什么时候更该先做一个项目。",
    date: "发布于 2026-08-06",
    sourceUrl: "https://www.zhihu.com/question/2060844556388774290/answer/2068708878309758218",
  },
  "math-to-cs": {
    title: "数学系学生如何成功转向计算机？",
    kicker: "转向计算机 / 知乎回答原稿",
    deck: "从方向选择、技术栈到实战经验：一个仍在转向过程中的数学系学生所看到的问题。",
    date: "原稿归档",
    sourceUrl: "https://www.zhihu.com/question/1948843451870349237/answer/2040152802853380110",
  },
  "math-outlook": {
    title: "数学系的出路在哪？",
    kicker: "专业选择 / 知乎回答原稿",
    deck: "从应用数学、现实需求和交叉方向出发，讨论数学知识怎样进入真实问题。",
    date: "原稿归档",
    sourceUrl: "https://www.zhihu.com/question/664610171/answer/2025602014432752160",
  },
  "math-interdisciplinary": {
    title: "数学系该学什么交叉方向？",
    kicker: "交叉方向 / 知乎回答原稿",
    deck: "围绕 AI4Science、计算数学和代码能力形成的一次阶段性经验分享。",
    date: "发布于 2025-12-02",
    sourceUrl: "https://www.zhihu.com/question/1976403480596997396/answer/1979250728703915584",
  },
};

const slug = new URLSearchParams(window.location.search).get("slug");
const article = articleManifest[slug];
const markdown = window.articleContent?.[slug];
const titleElement = document.querySelector("[data-article-title]");
const kickerElement = document.querySelector("[data-article-kicker]");
const deckElement = document.querySelector("[data-article-deck]");
const dateElement = document.querySelector("[data-article-date]");
const bodyElement = document.querySelector("[data-article-body]");
const sourceLink = document.querySelector("[data-article-source]");

if (!article || typeof markdown !== "string") {
  document.title = "文章不存在｜布莱的小店";
  titleElement.textContent = "没有找到这篇文章";
  kickerElement.textContent = "404 / NOT FOUND";
  deckElement.textContent = "这个站内文章地址可能已经改变。";
  dateElement.textContent = "";
  bodyElement.replaceChildren();
  const message = document.createElement("p");
  const backLink = document.createElement("a");
  message.textContent = "请返回炒作栏目重新选择文章。";
  backLink.href = "index.html#buzz";
  backLink.textContent = "返回炒作栏目 →";
  bodyElement.append(message, backLink);
  sourceLink.hidden = true;
} else {
  document.title = `${article.title}｜布莱的小店`;
  titleElement.textContent = article.title;
  kickerElement.textContent = article.kicker;
  deckElement.textContent = article.deck;
  dateElement.textContent = article.date;
  sourceLink.href = article.sourceUrl;
  bodyElement.replaceChildren(renderMarkdown(markdown, article.title));
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

function renderMarkdown(source, articleTitle) {
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
