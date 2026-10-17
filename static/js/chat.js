document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const chatWindow = document.getElementById("chat-window");
  // Demo mode: the server stores nothing. The browser keeps the conversation
  // (per tab) and sends the last few messages with every request.
  const isDemo = document.body.dataset.demo === "1";
  const era = document.body.dataset.era === "2030" ? "2030" : "1996";
  const STORE_KEY = "zm-chat-" + era;
  const MAX_SENT = 10;
  let history = [];

  function loadHistory() {
    try {
      const raw = JSON.parse(sessionStorage.getItem(STORE_KEY) || "[]");
      if (Array.isArray(raw)) {
        history = raw.filter(function (m) {
          return m && (m.role === "user" || m.role === "model") && typeof m.text === "string";
        }).slice(-50);
      }
    } catch (e) {
      history = [];
    }
  }

  function remember(role, text) {
    if (!isDemo) return;
    history.push({ role: role, text: text });
    history = history.slice(-50);
    try {
      sessionStorage.setItem(STORE_KEY, JSON.stringify(history));
    } catch (e) {
      /* storage unavailable: chat still works, just not restored on reload */
    }
  }

  function appendLine(role, text) {
    const line = document.createElement("div");
    line.className = "chat-line chat-" + role;

    const label = document.createElement("span");
    label.className = "chat-label";
    label.textContent = role === "user" ? "SEN>" : "BOT>";

    const body = document.createElement("span");
    body.className = "chat-text";
    body.textContent = text;

    line.appendChild(label);
    line.appendChild(body);
    chatWindow.appendChild(line);
    chatWindow.scrollTop = chatWindow.scrollHeight;

    if (role === "model" && window.updateHologramCaption) {
      window.updateHologramCaption(text);
    }
  }

  if (isDemo) {
    loadHistory();
    history.forEach(function (m) { appendLine(m.role, m.text); });
  }

  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) {
      return;
    }

    const sent = history.slice(-MAX_SENT).map(function (m) {
      return { role: m.role, text: m.text.slice(0, 500) };
    });
    appendLine("user", message);
    remember("user", message);
    input.value = "";
    input.disabled = true;

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          isDemo ? { message: message, history: sent, era: era } : { message: message }
        ),
      });

      // Demo errors (429/503/...) carry an in-character message in "reply".
      let data = null;
      try {
        data = await response.json();
      } catch (e) {
        data = null;
      }
      if (!response.ok && !(data && typeof data.reply === "string")) {
        throw new Error("HTTP " + response.status);
      }

      appendLine("model", data.reply);
      if (response.ok) {
        remember("model", data.reply);
      }
    } catch (err) {
      appendLine("model", "⚠ BAGLANTI KOPTU ⚠ Modeminizi kontrol edip tekrar deneyin...");
    } finally {
      input.disabled = false;
      input.focus();
    }
  });
});
