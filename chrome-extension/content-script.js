function visible(element) {
  const style = getComputedStyle(element);
  const rect = element.getBoundingClientRect();
  return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
}

function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function readPage() {
  const main = document.querySelector("main, article, [role='main']") || document.body;
  const text = cleanText(main.innerText).slice(0, 24000);
  const headings = [...document.querySelectorAll("h1,h2,h3")]
    .filter(visible).slice(0, 50).map((item) => cleanText(item.innerText));
  const links = [...document.querySelectorAll("a[href]")]
    .filter(visible).slice(0, 100).map((item) => ({
      text: cleanText(item.innerText || item.getAttribute("aria-label")),
      href: item.href
    })).filter((item) => item.text);
  return {title: document.title, url: location.href, text, headings, links};
}

function findByText(needle) {
  const wanted = cleanText(needle).toLocaleLowerCase("tr-TR");
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  let node;
  while ((node = walker.nextNode())) {
    if (!visible(node)) continue;
    const own = cleanText(node.innerText || node.getAttribute?.("aria-label"));
    if (own && own.length < 500 && own.toLocaleLowerCase("tr-TR").includes(wanted)) return node;
  }
  return null;
}

function findText(text) {
  const element = findByText(text);
  if (!element) return {found: false, text};
  element.scrollIntoView({behavior: "smooth", block: "center"});
  const oldOutline = element.style.outline;
  element.style.outline = "3px solid #3ee3ff";
  setTimeout(() => { element.style.outline = oldOutline; }, 3000);
  return {found: true, text, tag: element.tagName, label: cleanText(element.innerText).slice(0, 300)};
}

function clickText(text) {
  const element = findByText(text);
  if (!element) return {clicked: false, error: "İstenen öğe bulunamadı."};
  const target = element.closest("button,a,[role='button'],input[type='submit']") || element;
  target.scrollIntoView({behavior: "smooth", block: "center"});
  target.click();
  return {clicked: true, tag: target.tagName, label: cleanText(target.innerText || target.value)};
}

function clickNthLink(index) {
  const preferred = [...document.querySelectorAll("main a[href] h3")]
    .filter(visible).map((heading) => heading.closest("a")).filter(Boolean);
  const general = [...document.querySelectorAll("main a[href], article a[href], [role='main'] a[href], body a[href]")]
    .filter((item) => visible(item) && cleanText(item.innerText || item.getAttribute("aria-label")))
    .filter((item) => !item.href.startsWith("javascript:") && item.href !== location.href + "#");
  const links = [...new Set(preferred.length ? preferred : general)];
  const safeIndex = Number(index) - 1;
  const target = links[safeIndex];
  if (!target) return {clicked: false, error: "İstenen sırada görünür bağlantı bulunamadı."};
  const label = cleanText(target.innerText || target.getAttribute("aria-label"));
  target.scrollIntoView({behavior: "smooth", block: "center"});
  target.click();
  return {clicked: true, index: safeIndex + 1, label, url: target.href};
}

function youtubeOpenFirst() {
  const selectors = [
    "ytd-video-renderer a#video-title",
    "ytd-rich-item-renderer a#video-title-link",
    "ytd-grid-video-renderer a#video-title"
  ];
  const target = [...document.querySelectorAll(selectors.join(","))].find(visible);
  if (!target) return {clicked: false, error: "YouTube'da açılabilir video sonucu bulunamadı."};
  const title = cleanText(target.getAttribute("title") || target.innerText);
  const url = target.href;
  target.scrollIntoView({behavior: "smooth", block: "center"});
  target.click();
  return {clicked: true, title, url};
}

function typeText(args) {
  const selector = args.selector;
  let element = selector ? document.querySelector(selector) : document.activeElement;
  if (!element || !("value" in element)) {
    element = [...document.querySelectorAll("input,textarea,[contenteditable='true']")].find(visible);
  }
  if (!element) return {typed: false, error: "Yazılabilir alan bulunamadı."};
  element.focus();
  if (element.isContentEditable) {
    element.textContent = args.text;
    element.dispatchEvent(new InputEvent("input", {bubbles: true, inputType: "insertText", data: args.text}));
  } else {
    const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value")?.set;
    setter ? setter.call(element, args.text) : (element.value = args.text);
    element.dispatchEvent(new Event("input", {bubbles: true}));
    element.dispatchEvent(new Event("change", {bubbles: true}));
  }
  return {typed: true, field: element.name || element.id || element.tagName};
}

function media(command) {
  const item = [...document.querySelectorAll("video,audio")].find(visible) || document.querySelector("video,audio");
  if (!item) return {changed: false, error: "Sayfada video veya ses bulunamadı."};
  if (command === "play") item.play();
  else if (command === "pause") item.pause();
  else if (command === "mute") item.muted = true;
  else if (command === "unmute") item.muted = false;
  else if (command === "fullscreen") item.requestFullscreen();
  else return {changed: false, error: "Geçersiz medya komutu."};
  return {changed: true, command, paused: item.paused, muted: item.muted};
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  try {
    const args = message.arguments || {};
    let result;
    switch (message.action) {
      case "readPage": result = readPage(); break;
      case "findText": result = findText(args.text); break;
      case "clickText": result = clickText(args.text); break;
      case "clickNthLink": result = clickNthLink(args.index); break;
      case "youtubeOpenFirst": result = youtubeOpenFirst(); break;
      case "typeText": result = typeText(args); break;
      case "media": result = media(args.command); break;
      case "scroll":
        window.scrollBy({top: Number(args.amount || innerHeight * 0.8), behavior: "smooth"});
        result = {scrolled: true, y: scrollY};
        break;
      default: throw new Error("Desteklenmeyen sayfa işlemi.");
    }
    if (result?.error) sendResponse({ok: false, error: result.error});
    else sendResponse({ok: true, result});
  } catch (error) {
    sendResponse({ok: false, error: String(error.message || error)});
  }
  return true;
});
