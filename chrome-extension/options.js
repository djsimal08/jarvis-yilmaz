const code = document.getElementById("code");
const status = document.getElementById("status");
document.getElementById("pair").addEventListener("click", async () => {
  const value = code.value.trim();
  if (!/^\d{6}$/.test(value)) {
    status.textContent = "6 haneli kodu girin.";
    return;
  }
  status.textContent = "Eşleştiriliyor…";
  try {
    const response = await fetch("http://127.0.0.1:8765/api/pair", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({code: value})
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Eşleştirme başarısız.");
    await chrome.storage.local.set({jarvisToken: result.token});
    status.textContent = "Bağlantı kuruldu. Bu sayfayı kapatabilirsiniz.";
    chrome.runtime.sendMessage({type: "reconnect"});
  } catch (error) {
    status.textContent = error.message;
  }
});
