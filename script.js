const navigationLinks = [...document.querySelectorAll("[data-nav] a[href^='#']")];
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
