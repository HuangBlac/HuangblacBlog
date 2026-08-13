const navigationLinks = [...document.querySelectorAll("[data-nav] a[href^='#']")];

const featuredDate = document.querySelector("[data-featured-date]");
if (featuredDate && /^\d{4}-\d{2}-\d{2}$/.test(window.siteData?.featuredUpdated ?? "")) {
  const [year, month] = window.siteData.featuredUpdated.split("-");
  featuredDate.querySelector("[data-featured-month]").textContent = month;
  featuredDate.querySelector("[data-featured-year]").textContent = year;
  featuredDate.setAttribute("aria-label", `更新于 ${year}年${Number(month)}月`);
}

const observedSections = navigationLinks
  .map((link) => document.querySelector(link.getAttribute("href")))
  .filter(Boolean);

if ("IntersectionObserver" in window) {
  const sectionObserver = new IntersectionObserver(
    (entries) => {
      const visibleSection = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];

      if (!visibleSection) return;

      navigationLinks.forEach((link) => {
        const isCurrent = link.getAttribute("href") === `#${visibleSection.target.id}`;
        if (isCurrent) link.setAttribute("aria-current", "true");
        else link.removeAttribute("aria-current");
      });
    },
    { rootMargin: "-18% 0px -68%", threshold: [0, 0.15, 0.5] },
  );

  observedSections.forEach((section) => sectionObserver.observe(section));
}

const focusWidget = document.querySelector("[data-focus-widget]");

if (focusWidget) {
  const storageKey = "blai-shop.current-focus.v1";
  const focusList = focusWidget.querySelector("[data-focus-list]");
  const editButton = focusWidget.querySelector("[data-focus-edit]");
  const editor = focusWidget.querySelector("[data-focus-editor]");
  const editorList = focusWidget.querySelector("[data-focus-editor-list]");
  const addButton = focusWidget.querySelector("[data-focus-add]");
  const resetButton = focusWidget.querySelector("[data-focus-reset]");
  const cancelButton = focusWidget.querySelector("[data-focus-cancel]");
  const status = focusWidget.querySelector("[data-focus-status]");
  const defaultFocus = Array.isArray(window.siteData?.currentFocus)
    ? window.siteData.currentFocus
    : [];
  let currentFocus = loadFocus();

  function cleanFocus(items) {
    if (!Array.isArray(items)) return [];
    return items
      .filter((item) => typeof item === "string")
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, 8);
  }

  function loadFocus() {
    try {
      const storedFocus = JSON.parse(localStorage.getItem(storageKey));
      const cleanedFocus = cleanFocus(storedFocus);
      if (cleanedFocus.length) return cleanedFocus;
    } catch {
      // Invalid or unavailable browser storage falls back to the public defaults.
    }
    return cleanFocus(defaultFocus);
  }

  function renderFocus() {
    focusList.replaceChildren();
    currentFocus.forEach((item, index) => {
      const listItem = document.createElement("li");
      const number = document.createElement("span");
      const label = document.createElement("strong");
      number.textContent = String(index + 1).padStart(2, "0");
      label.textContent = item;
      listItem.append(number, label);
      focusList.append(listItem);
    });
  }

  function makeEditorRow(value = "") {
    const row = document.createElement("div");
    row.className = "focus-row";

    const input = document.createElement("input");
    input.type = "text";
    input.value = value;
    input.maxLength = 40;
    input.setAttribute("aria-label", "关注方向");

    const moveUp = document.createElement("button");
    moveUp.type = "button";
    moveUp.textContent = "↑";
    moveUp.setAttribute("aria-label", `上移${value ? `“${value}”` : "此项"}`);

    const moveDown = document.createElement("button");
    moveDown.type = "button";
    moveDown.textContent = "↓";
    moveDown.setAttribute("aria-label", `下移${value ? `“${value}”` : "此项"}`);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "×";
    remove.setAttribute("aria-label", `删除${value ? `“${value}”` : "此项"}`);

    moveUp.addEventListener("click", () => {
      const previous = row.previousElementSibling;
      if (previous) editorList.insertBefore(row, previous);
    });

    moveDown.addEventListener("click", () => {
      const next = row.nextElementSibling;
      if (next) editorList.insertBefore(next, row);
    });

    remove.addEventListener("click", () => row.remove());
    row.append(input, moveUp, moveDown, remove);
    return row;
  }

  function openEditor() {
    editorList.replaceChildren(...currentFocus.map((item) => makeEditorRow(item)));
    focusList.hidden = true;
    editor.hidden = false;
    editButton.setAttribute("aria-expanded", "true");
    status.textContent = "";
    editorList.querySelector("input")?.focus();
  }

  function closeEditor() {
    editor.hidden = true;
    focusList.hidden = false;
    editButton.setAttribute("aria-expanded", "false");
    editButton.focus();
  }

  function saveFocus(event) {
    event.preventDefault();
    const nextFocus = cleanFocus(
      [...editorList.querySelectorAll("input")].map((input) => input.value),
    );

    if (!nextFocus.length) {
      status.textContent = "至少保留一个关注方向。";
      return;
    }

    try {
      localStorage.setItem(storageKey, JSON.stringify(nextFocus));
      currentFocus = nextFocus;
      renderFocus();
      closeEditor();
    } catch {
      status.textContent = "浏览器阻止了本地保存，请直接修改 site-data.js。";
    }
  }

  const editingAvailable =
    ["127.0.0.1", "localhost"].includes(window.location.hostname) ||
    new URLSearchParams(window.location.search).has("edit");

  renderFocus();
  if (editingAvailable) editButton.hidden = false;

  editButton.addEventListener("click", () => {
    if (editor.hidden) openEditor();
    else closeEditor();
  });

  addButton.addEventListener("click", () => {
    if (editorList.children.length >= 8) {
      status.textContent = "最多保留八个关注方向。";
      return;
    }
    const row = makeEditorRow();
    editorList.append(row);
    row.querySelector("input").focus();
  });

  resetButton.addEventListener("click", () => {
    editorList.replaceChildren(...cleanFocus(defaultFocus).map((item) => makeEditorRow(item)));
    status.textContent = "已载入公开默认值，点击保存后生效。";
  });

  cancelButton.addEventListener("click", closeEditor);
  editor.addEventListener("submit", saveFocus);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !editor.hidden) closeEditor();
  });
}

const articleCatalog = window.articleCatalog;
const catalogArticles = Array.isArray(articleCatalog?.articles)
  ? [...articleCatalog.articles].sort((a, b) => a.order - b.order)
  : [];
const publicIndex = document.querySelector("[data-public-index]");
const creativeIndex = document.querySelector("[data-creative-index]");

function makeArticleHref(slug) {
  if (window.location.protocol === "file:") {
    return `article.html?slug=${encodeURIComponent(slug)}`;
  }
  return `article/${encodeURIComponent(slug)}/`;
}

function renderPublicIndex() {
  if (!publicIndex || !articleCatalog) return;

  const entries = catalogArticles
    .filter((item) => item.section === "buzz")
    .map((item) => {
      const article = document.createElement("article");
      const meta = document.createElement("p");
      const heading = document.createElement("h3");
      const headingLink = document.createElement("a");
      const deck = document.createElement("p");
      const actions = document.createElement("div");
      const readLink = document.createElement("a");

      article.className = "public-note public-note-linked";
      meta.className = "entry-meta";
      actions.className = "public-note-actions";
      readLink.className = "read-on-site";
      meta.textContent = [item.topic, item.date].filter(Boolean).join(" · ");
      headingLink.href = makeArticleHref(item.slug);
      headingLink.textContent = item.title;
      deck.textContent = item.deck;
      readLink.href = makeArticleHref(item.slug);
      readLink.textContent = "站内阅读全文 →";

      heading.append(headingLink);
      actions.append(readLink);
      if (item.source?.url) {
        const sourceLink = document.createElement("a");
        sourceLink.href = item.source.url;
        sourceLink.target = "_blank";
        sourceLink.rel = "noreferrer";
        sourceLink.textContent = `${item.source.label} ↗`;
        actions.append(sourceLink);
      }

      article.append(meta, heading, deck, actions);
      return article;
    });

  publicIndex.replaceChildren(...entries);
}

function makeCreativeList(items, action) {
  const list = document.createElement("ul");
  list.className = "creative-index";

  items.forEach((item) => {
    const listItem = document.createElement("li");
    const link = document.createElement("a");
    const title = document.createElement("strong");
    const status = document.createElement("span");

    link.href = makeArticleHref(item.slug);
    title.textContent = item.title;
    status.textContent = action;
    link.append(title, status);
    listItem.append(link);
    list.append(listItem);
  });

  return list;
}

function makeCreativeStage(stage) {
  const items = catalogArticles.filter(
    (item) => item.section === "creative" && item.stage === stage.id,
  );
  const section = document.createElement("section");
  const heading = document.createElement("div");
  const headingText = document.createElement("div");
  const eyebrow = document.createElement("p");
  const title = document.createElement("h3");
  const count = document.createElement("span");
  const note = document.createElement("p");

  section.className = "creative-stage";
  heading.className = "creative-stage-heading";
  eyebrow.className = "creative-stage-label";
  note.className = "creative-stage-note";
  eyebrow.textContent = stage.eyebrow;
  title.textContent = stage.label;
  count.textContent = `${items.length} 篇`;
  note.textContent = stage.note;

  headingText.append(eyebrow, title);
  heading.append(headingText, count);
  section.append(heading, note, makeCreativeList(items, stage.action));
  return section;
}

function renderCreativeIndex() {
  if (!creativeIndex || !articleCatalog || !Array.isArray(articleCatalog.stages)) return;

  const primaryStages = articleCatalog.stages.filter((stage) => !stage.collapsed);
  const collapsedStages = articleCatalog.stages.filter((stage) => stage.collapsed);
  const sections = primaryStages.map((stage) => makeCreativeStage(stage));

  if (collapsedStages.length) {
    const incomplete = document.createElement("details");
    const incompleteSummary = document.createElement("summary");
    const summaryHint = document.createElement("span");
    const incompleteBody = document.createElement("div");
    const warning = document.createElement("p");

    incomplete.className = "creative-incomplete";
    incompleteSummary.append(`${articleCatalog.creative.incompleteTitle} `);
    summaryHint.textContent = articleCatalog.creative.expandLabel;
    incompleteSummary.append(summaryHint);
    incompleteBody.className = "creative-incomplete-body";
    warning.className = "creative-warning";
    warning.textContent = articleCatalog.creative.warning;
    incompleteBody.append(
      warning,
      ...collapsedStages.map((stage) => makeCreativeStage(stage)),
    );
    incomplete.append(incompleteSummary, incompleteBody);
    sections.push(incomplete);
  }

  creativeIndex.replaceChildren(...sections);
}

renderPublicIndex();
renderCreativeIndex();
