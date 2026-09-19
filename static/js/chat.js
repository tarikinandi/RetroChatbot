document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const chatWindow = document.getElementById("chat-window");

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

    appendLine("user", message);
    input.value = "";
    input.disabled = true;

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message }),
      });

      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }

      const data = await response.json();
      appendLine("model", data.reply);
    } catch (err) {
      appendLine("model", "⚠ BAGLANTI KOPTU ⚠ Modeminizi kontrol edip tekrar deneyin...");
    } finally {
      input.disabled = false;
      input.focus();
    }
  });
});
