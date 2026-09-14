let socket = null;
let reconnectTimer = null;

async function getToken() {
  return (await chrome.storage.local.get("jarvisToken")).jarvisToken || "";
}

function connect() {
  clearTimeout(reconnectTimer);
  getToken().then((token) => {
    if (!token) return;
    socket = new WebSocket("ws://127.0.0.1:8765/ws/chrome?token=" + encodeURIComponent(token));
    socket.onopen = () => sendTabs();
    socket.onmessage = (event) => handleMessage(JSON.parse(event.data));
    socket.onclose = () => {
      socket = null;
      reconnectTimer = setTimeout(connect, 3000);
    };
    socket.onerror = () => socket?.close();
  });
}

function send(payload) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(payload));
}

async function sendTabs() {
  const tabs = await chrome.tabs.query({});
  send({
    type: "tabs",
    tabs: tabs.map((tab) => ({
      id: tab.id,
      windowId: tab.windowId,
      title: tab.title,
      url: tab.url,
      active: tab.active,
      pinned: tab.pinned
    }))
  });
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({active: true, lastFocusedWindow: true});
  if (!tab?.id) throw new Error("Aktif Chrome sekmesi bulunamadı.");
  return tab;
}

async function waitForTabComplete(tabId, timeoutMs = 20000) {
  const current = await chrome.tabs.get(tabId);
  if (current.status === "complete") return;
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error("Sayfanın yüklenmesi zaman aşımına uğradı."));
    }, timeoutMs);
    function listener(id, info) {
      if (id === tabId && info.status === "complete") {
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    }
    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function pageCommand(action, args) {
  const tab = await activeTab();
  try {
    return await chrome.tabs.sendMessage(tab.id, {action, arguments: args});
  } catch (error) {
    throw new Error("Bu sayfaya erişilemiyor. Sayfayı yenileyin veya Chrome özel sayfasından çıkın.");
  }
}

async function handleMessage(message) {
  if (message.type !== "command") return;
  const id = message.id;
  try {
    let result;
    const args = message.arguments || {};
    switch (message.action) {
      case "openUrl": {
        const tab = await chrome.tabs.create({url: args.url, active: true});
        result = {opened: Boolean(tab.id), tabId: tab.id, url: tab.url || args.url};
        break;
      }
      case "newTab": {
        const tab = await chrome.tabs.create({url: args.url || "chrome://newtab/", active: true});
        result = {opened: Boolean(tab.id), tabId: tab.id};
        break;
      }
      case "youtubeSearchOpen": {
        const query = encodeURIComponent(String(args.query || ""));
        const tab = await chrome.tabs.create({url: "https://www.youtube.com/results?search_query=" + query, active: true});
        await waitForTabComplete(tab.id);
        await new Promise((resolve) => setTimeout(resolve, 900));
        const page = await chrome.tabs.sendMessage(tab.id, {action: "youtubeOpenFirst", arguments: {}});
        if (!page?.ok) throw new Error(page?.error || "YouTube videosu açılamadı.");
        result = page.result;
        break;
      }
      case "listTabs": {
        const tabs = await chrome.tabs.query({});
        result = {
          count: tabs.length,
          tabs: tabs.map((tab) => ({id: tab.id, title: tab.title, url: tab.url, active: tab.active}))
        };
        break;
      }
      case "activateTab": {
        const tabId = args.tabId ? Number(args.tabId) : (await activeTab()).id;
        await chrome.tabs.update(tabId, {active: true});
        result = {activated: true, tabId};
        break;
      }
      case "activateRelativeTab": {
        const current = await activeTab();
        const tabs = await chrome.tabs.query({windowId: current.windowId});
        const position = tabs.findIndex((tab) => tab.id === current.id);
        const offset = Number(args.offset || -1);
        const target = tabs[(position + offset + tabs.length) % tabs.length];
        if (!target?.id) throw new Error("Geçilecek sekme bulunamadı.");
        await chrome.tabs.update(target.id, {active: true});
        result = {activated: true, tabId: target.id, title: target.title};
        break;
      }
      case "closeTab": {
        const tabId = args.tabId ? Number(args.tabId) : (await activeTab()).id;
        await chrome.tabs.remove(tabId);
        result = {closed: true, tabId};
        break;
      }
      case "pinTab": {
        const tabId = args.tabId ? Number(args.tabId) : (await activeTab()).id;
        await chrome.tabs.update(tabId, {pinned: Boolean(args.pinned)});
        result = {changed: true, tabId, pinned: Boolean(args.pinned)};
        break;
      }
      default:
        result = await pageCommand(message.action, args);
    }
    if (result?.ok === false) throw new Error(result.error || "Sayfa işlemi başarısız.");
    send({type: "result", id, ok: true, result: result?.result || result || {}});
    sendTabs();
  } catch (error) {
    send({type: "result", id, ok: false, error: String(error.message || error)});
  }
}

chrome.tabs.onCreated.addListener(sendTabs);
chrome.tabs.onRemoved.addListener(sendTabs);
chrome.tabs.onUpdated.addListener((_id, info) => {
  if (info.title || info.url || info.status === "complete") sendTabs();
});
chrome.tabs.onActivated.addListener(sendTabs);
chrome.runtime.onInstalled.addListener(() => {
  chrome.runtime.openOptionsPage();
  connect();
});
chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "reconnect") {
    socket?.close();
    setTimeout(connect, 250);
  }
});
chrome.alarms.create("jarvis-keepalive", {periodInMinutes: 0.5});
chrome.alarms.onAlarm.addListener(() => {
  if (!socket || socket.readyState > WebSocket.OPEN) connect();
  else send({type: "ping"});
});
connect();
