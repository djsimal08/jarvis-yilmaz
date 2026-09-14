const $ = (id) => document.getElementById(id);
const state = {
  recording: false,
  recorder: null,
  chunks: [],
  pendingTask: null,
  pendingRisk: 0,
  voiceEnabled: true,
  voiceName: "",
  miniVisible: false,
};

function setConnection(prefix, connected, yes = "Bağlı", no = "Bağlı değil") {
  $(prefix + "-dot").className = connected ? "ok" : "bad";
  $(prefix + "-status").textContent = connected ? yes : no;
}

function setOrbMode(mode, message) {
  const normalized = String(mode || "IDLE").toLowerCase();
  $("orb").className = "orb " + normalized;
  $("mode-label").textContent = String(mode || "IDLE");
  if (message) $("jarvis-message").textContent = message;
}

function setBar(name, value) {
  const safe = Math.max(0, Math.min(Number(value || 0), 100));
  $(name + "-value").textContent = Math.round(safe) + "%";
  $(name + "-bar").style.width = safe + "%";
}

function makeListItem(title, detail, className = "") {
  const item = document.createElement("div");
  item.className = "list-item";
  const strong = document.createElement("strong");
  const small = document.createElement("small");
  strong.textContent = title;
  small.textContent = detail;
  if (className) small.className = className;
  item.append(strong, small);
  return item;
}

async function getJson(url, options = {}) {
  const response = await fetch(url, options);
  let payload = {};
  try { payload = await response.json(); } catch (_) {}
  if (!response.ok) throw new Error(payload.detail || "İstek başarısız.");
  return payload;
}

async function refreshStatus() {
  try {
    const data = await getJson("/api/status");
    setConnection("agent", data.agent_connected);
    setConnection("chrome", data.chrome_connected);
    setConnection("ai", data.ollama_connected, "Hazır", "Yerel model yok");
    setOrbMode(data.mode, data.last_message);

    const system = data.system || {};
    setBar("cpu", system.cpu_percent);
    setBar("ram", system.ram_percent);
    setBar("disk", system.disk_percent);
    $("process-count").textContent = system.process_count ?? "--";
    $("network-value").textContent = system.network_connected ? "ÇEVRİMİÇİ" : "KAPALI";

    const active = data.active_window || {};
    $("active-window").textContent = active.title || "Aktif pencere okunamadı";
    $("active-pid").textContent = active.pid ? "PID " + active.pid : "PID —";

    state.voiceEnabled = Boolean(data.profile?.enable_voice_reply);
    state.voiceName = data.profile?.voice_name || "";
    $("voice-enabled").checked = state.voiceEnabled;
    populateVoices();
    if (document.activeElement !== $("user-name")) {
      $("user-name").value = data.profile?.user_name || "";
    }
    const openai = data.openai || {};
    $("openai-enabled").checked = Boolean(openai.enabled);
    $("openai-consent").value = openai.consent || "local";
    $("openai-model").value = openai.model || "gpt-5-mini";
    $("openai-state").textContent = openai.enabled ? "Etkin" : (openai.configured ? "Anahtar kayıtlı" : "Kapalı");

    const user = data.profile?.user_name;
    $("greeting").textContent = user && user !== "Kullanıcı" ? "Hazırım, " + user + "." : "Hazırım.";

    $("pair-code").textContent = data.pairing?.code || "------";
    $("pair-time").textContent = "Yaklaşık " + Math.ceil((data.pairing?.expires_seconds || 0) / 60) + " dakika geçerli";

    renderTabs(data.tabs || [], data.chrome_connected);
  } catch (error) {
    setConnection("agent", false);
    setOrbMode("IDLE", "Yerel yardımcı uygulamaya ulaşılamıyor: " + error.message);
  }
}

function renderTabs(tabs, connected) {
  const list = $("tabs-list");
  list.replaceChildren();
  $("tab-count").textContent = tabs.length;
  if (!connected || !tabs.length) {
    list.className = "list empty";
    list.textContent = connected ? "Açık sekme bilgisi bekleniyor." : "Chrome eklentisi bağlı değil.";
    return;
  }
  list.className = "list";
  tabs.slice(0, 20).forEach((tab, index) => {
    list.append(makeListItem((index + 1) + ". " + (tab.title || "Adsız sekme"), tab.url || ""));
  });
}

async function refreshHistory() {
  try {
    const data = await getJson("/api/history?limit=25");
    const list = $("history-list");
    list.replaceChildren();
    if (!data.items?.length) {
      list.className = "list empty";
      list.textContent = "Henüz işlem yok.";
      return;
    }
    list.className = "list";
    data.items.forEach((entry) => {
      const time = new Date(entry.created_at).toLocaleString("tr-TR");
      list.append(makeListItem(entry.command, time + " · " + entry.status, "status-" + entry.status));
    });
  } catch (_) {}
}

async function submitCommand(commandText) {
  const command = String(commandText || $("command-input").value).trim();
  if (!command) return;
  $("command-input").value = "";
  setOrbMode("UNDERSTANDING", "Komut gönderiliyor…");
  try {
    const result = await getJson("/api/command", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({command}),
    });
    handleResult(result);
  } catch (error) {
    setOrbMode("IDLE", error.message);
    speak("İşlem başarısız. " + error.message);
  } finally {
    refreshHistory();
    refreshStatus();
  }
}

function handleResult(result) {
  if (result.status === "approval_waiting") {
    state.pendingTask = result.task_id;
    state.pendingRisk = result.risk;
    $("approval-text").textContent =
      (result.action?.explanation || "Bu işlem") + " — Henüz uygulanmadı.";
    $("final-confirm-wrap").hidden = result.risk !== 3;
    $("final-confirm-input").value = "";
    $("approval-modal").hidden = false;
    setOrbMode("IDLE", "Onay bekleniyor.");
    return;
  }
  setOrbMode(result.status === "success" ? "SPEAKING" : "IDLE", result.message);
  if (state.voiceEnabled && result.message) speak(result.message);
}

async function confirmPending(approve) {
  if (!state.pendingTask) return;
  try {
    const result = await getJson("/api/confirm/" + state.pendingTask, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        approve,
        confirmation: $("final-confirm-input").value,
      }),
    });
    $("approval-modal").hidden = true;
    state.pendingTask = null;
    handleResult(result);
  } catch (error) {
    $("jarvis-message").textContent = error.message;
  }
  refreshHistory();
}

function populateVoices() {
  if (!("speechSynthesis" in window)) return;
  const select = $("voice-name");
  const current = state.voiceName || select.value;
  const turkish = speechSynthesis.getVoices().filter((voice) => voice.lang.toLowerCase().startsWith("tr"));
  select.replaceChildren(new Option("Otomatik Türkçe ses", ""));
  turkish.forEach((voice) => select.add(new Option(voice.name + " — " + voice.lang, voice.name)));
  select.value = [...select.options].some((option) => option.value === current) ? current : "";
}

function speak(text) {
  if (!state.voiceEnabled || !("speechSynthesis" in window)) return;
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "tr-TR";
  const voices = speechSynthesis.getVoices();
  utterance.voice = voices.find((v) => v.name === state.voiceName)
    || voices.find((v) => v.lang.toLowerCase().startsWith("tr")) || null;
  utterance.rate = 1.02;
  utterance.pitch = 0.92;
  utterance.onstart = () => setOrbMode("SPEAKING");
  utterance.onend = () => {
    setOrbMode("IDLE");
    fetch("/api/speech-finished", {method: "POST"}).catch(() => {});
  };
  speechSynthesis.speak(utterance);
}

async function toggleRecording() {
  const button = $("mic-button");
  if (state.recording) {
    state.recorder.stop();
    state.recording = false;
    button.classList.remove("recording");
    button.querySelector("b").textContent = "Dinlemeyi Başlat";
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio: {
      echoCancellation: true, noiseSuppression: true, autoGainControl: true
    }});
    state.chunks = [];
    state.recorder = new MediaRecorder(stream);
    state.recorder.ondataavailable = (event) => {
      if (event.data.size) state.chunks.push(event.data);
    };
    state.recorder.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop());
      const blob = new Blob(state.chunks, {type: state.recorder.mimeType || "audio/webm"});
      const form = new FormData();
      form.append("audio", blob, "speech.webm");
      setOrbMode("UNDERSTANDING", "Türkçe konuşma çözümleniyor…");
      try {
        const result = await getJson("/api/transcribe", {method: "POST", body: form});
        $("command-input").value = result.text || "";
        if (result.text) submitCommand(result.text);
        else setOrbMode("IDLE", "Konuşma algılanamadı.");
      } catch (error) {
        setOrbMode("IDLE", error.message);
      }
    };
    state.recorder.start();
    state.recording = true;
    button.classList.add("recording");
    button.querySelector("b").textContent = "Dinlemeyi Bitir";
    setOrbMode("LISTENING", "Sizi dinliyorum… Bitirmek için tekrar basın.");
  } catch (error) {
    setOrbMode("IDLE", "Mikrofon izni alınamadı: " + error.message);
  }
}

async function emergencyStop() {
  speechSynthesis?.cancel();
  if (state.recording) state.recorder.stop();
  try {
    const result = await getJson("/api/cancel", {method: "POST"});
    setOrbMode("IDLE", result.message);
  } catch (error) {
    setOrbMode("IDLE", error.message);
  }
}

async function toggleMiniOrb() {
  const operation = state.miniVisible ? "hide" : "show";
  try {
    const result = await getJson("/api/mini-orb/" + operation, {method: "POST"});
    state.miniVisible = result.visible;
    $("mini-orb-button").textContent = state.miniVisible ? "Mini orb'u gizle" : "Mini orb'u göster";
  } catch (error) {
    setOrbMode("IDLE", error.message);
  }
}

async function saveProfile() {
  try {
    await getJson("/api/profile", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        user_name: $("user-name").value.trim() || "Kullanıcı",
        enable_voice_reply: $("voice-enabled").checked,
        voice_name: $("voice-name").value,
      }),
    });
    $("jarvis-message").textContent = "Ayarlar yalnızca bu bilgisayara kaydedildi.";
    refreshStatus();
  } catch (error) {
    $("jarvis-message").textContent = error.message;
  }
}

async function saveOpenAI() {
  try {
    const result = await getJson("/api/openai", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        enabled: $("openai-enabled").checked,
        consent: $("openai-consent").value,
        model: $("openai-model").value.trim() || "gpt-5-mini",
        api_key: $("openai-key").value.trim(),
        remove_key: false,
      }),
    });
    $("openai-key").value = "";
    $("openai-message").textContent = result.enabled
      ? "OpenAI etkin. Yalnızca seçtiğiniz kapsam API'ye gönderilebilir."
      : "Ayar kaydedildi; planlama yerel çalışıyor.";
    refreshStatus();
  } catch (error) {
    $("openai-message").textContent = error.message;
  }
}

async function testOpenAI() {
  $("openai-message").textContent = "Bağlantı doğrulanıyor…";
  try {
    const result = await getJson("/api/openai/test", {method: "POST"});
    $("openai-message").textContent = result.message;
  } catch (error) {
    $("openai-message").textContent = error.message;
  }
}

document.querySelectorAll("[data-command]").forEach((button) => {
  button.addEventListener("click", () => submitCommand(button.dataset.command));
});
document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    const target = button.dataset.target;
    const settings = target === "settings-panel";
    $("main-panel").classList.toggle("active", !settings);
    $("settings-panel").classList.toggle("active", settings);
    if (!settings && target !== "main-panel") {
      setTimeout(() => document.getElementById(target)?.scrollIntoView({behavior: "smooth", block: "center"}), 50);
    }
  });
});
$("send-command").addEventListener("click", () => submitCommand());
$("command-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter") submitCommand();
});
$("mic-button").addEventListener("click", toggleRecording);
$("emergency-stop").addEventListener("click", emergencyStop);
$("mini-orb-button").addEventListener("click", toggleMiniOrb);
$("refresh-history").addEventListener("click", refreshHistory);
$("save-profile").addEventListener("click", saveProfile);
$("save-openai").addEventListener("click", saveOpenAI);
$("test-openai").addEventListener("click", testOpenAI);
speechSynthesis?.addEventListener?.("voiceschanged", populateVoices);
populateVoices();
$("reject-action").addEventListener("click", () => confirmPending(false));
$("approve-action").addEventListener("click", () => confirmPending(true));

try {
  const socket = new WebSocket("ws://" + location.host + "/ws/dashboard");
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "state") setOrbMode(data.mode, data.message);
    if (data.type === "connection") setConnection("chrome", Boolean(data.chrome));
  };
  setInterval(() => socket.readyState === 1 && socket.send(JSON.stringify({type: "ping"})), 20000);
} catch (_) {}

refreshStatus();
refreshHistory();
setInterval(refreshStatus, 1800);
setInterval(refreshHistory, 7000);
