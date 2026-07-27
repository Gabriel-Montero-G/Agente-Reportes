"use strict";

const chatEl = document.getElementById("chat");
const formEl = document.getElementById("composer");
const inputEl = document.getElementById("prompt");
const sendEl = document.getElementById("send");
const reportEl = document.getElementById("report");
const emptyEl = document.getElementById("empty");
const titleEl = document.getElementById("report-title");
const downloadEl = document.getElementById("download");

const sessionId = (() => {
  let id = sessionStorage.getItem("session_id");
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem("session_id", id);
  }
  return id;
})();

let hasReport = false;

function addBubble(role, text) {
  const el = document.createElement("div");
  el.className = `bubble bubble--${role}`;
  el.textContent = text || "";
  chatEl.appendChild(el);
  chatEl.scrollTop = chatEl.scrollHeight;
  return el;
}

function addStep(tool, input) {
  const el = document.createElement("div");
  el.className = "step";
  el.textContent = tool === "write_report" ? "✍️ Escribiendo el informe" : `🔍 Buscando: ${input}`;
  chatEl.appendChild(el);
  chatEl.scrollTop = chatEl.scrollHeight;
  return el;
}

async function* readSSE(stream) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index;
    while ((index = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, index);
      buffer = buffer.slice(index + 2);
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data:")) continue;
        try {
          yield JSON.parse(line.slice(5).trim());
        } catch (err) {
          console.warn("frame SSE ilegible", line);
        }
      }
    }
  }
}

function showReport(html, markdown) {
  reportEl.innerHTML = html;
  emptyEl.hidden = true;
  hasReport = true;
  downloadEl.disabled = false;
  const heading = reportEl.querySelector("h1");
  titleEl.textContent = heading ? heading.textContent : "Informe";
}

function setBusy(busy) {
  inputEl.disabled = busy;
  sendEl.disabled = busy;
  if (!busy) inputEl.focus();
}

formEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = inputEl.value.trim();
  if (!message) return;
  inputEl.value = "";
  setBusy(true);
  addBubble("user", message);

  let assistantEl = null;
  const openSteps = new Map();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);

    for await (const event of readSSE(response.body)) {
      if (event.type === "token") {
        if (!assistantEl) assistantEl = addBubble("assistant", "");
        assistantEl.textContent += event.text;
        chatEl.scrollTop = chatEl.scrollHeight;
      } else if (event.type === "step") {
        openSteps.set(event.run_id, addStep(event.tool, event.input));
      } else if (event.type === "step_done") {
        const stepEl = openSteps.get(event.run_id);
        if (stepEl) {
          const failed = typeof event.summary === "string" && event.summary.startsWith("Búsqueda fallida");
          stepEl.textContent = failed ? `⚠ ${event.summary}` : `✓ ${event.summary}`;
          stepEl.classList.add(failed ? "step--error" : "step--done");
          openSteps.delete(event.run_id);
        }
      } else if (event.type === "report") {
        showReport(event.html, event.markdown);
      } else if (event.type === "error") {
        addBubble("error", event.message);
      }
    }
  } catch (err) {
    addBubble("error", `No se pudo contactar con el servidor: ${err.message}`);
  } finally {
    setBusy(false);
  }
});

downloadEl.addEventListener("click", async () => {
  if (!hasReport) return;
  const response = await fetch(`/api/report/${sessionId}`);
  if (!response.ok) {
    addBubble("error", "No hay informe disponible para descargar.");
    return;
  }
  const blob = new Blob([await response.text()], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "informe.md";
  link.click();
  URL.revokeObjectURL(url);
});

inputEl.focus();
