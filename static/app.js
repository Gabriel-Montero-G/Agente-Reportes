"use strict";

/* Every number and label in this UI is derived from the SSE contract emitted by
   app/server.py (token, step, step_done, report, error, done) or from the plain
   markdown/HTML those events carry. Nothing here is fabricated. */

const els = {
  topicTitle: document.getElementById("topic-title"),
  copyBtn: document.getElementById("copy-md"),
  downloadBtn: document.getElementById("download"),

  elapsed: document.getElementById("elapsed"),
  pill: document.getElementById("status-pill"),

  planStep: document.getElementById("step-plan"),
  planSub: document.getElementById("plan-sub"),

  searchStep: document.getElementById("step-search"),
  searchSub: document.getElementById("search-sub"),
  queryList: document.getElementById("query-list"),

  sourcesStep: document.getElementById("step-sources"),
  sourcesSub: document.getElementById("sources-sub"),
  sourceChips: document.getElementById("source-chips"),

  reportStep: document.getElementById("step-report"),
  reportSub: document.getElementById("report-sub"),

  note: document.getElementById("agent-note"),
  noteText: document.getElementById("note-text"),

  errorBanner: document.getElementById("error-banner"),

  form: document.getElementById("composer"),
  prompt: document.getElementById("prompt"),
  send: document.getElementById("send"),
  depth: document.getElementById("depth"),
  lang: document.getElementById("lang"),

  historyNav: document.getElementById("history-nav"),
  historyPrev: document.getElementById("history-prev"),
  historyNext: document.getElementById("history-next"),
  historyPos: document.getElementById("history-pos"),

  empty: document.getElementById("empty"),
  reportView: document.getElementById("report-view"),
  reportMeta: document.getElementById("report-meta"),
  report: document.getElementById("report"),
};

const MAX_CHIPS = 10;
const TITLE_MAX_CHARS = 70;

const sessionId = (() => {
  let id = sessionStorage.getItem("session_id");
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem("session_id", id);
  }
  return id;
})();

const history = []; // { title, markdown, html, meta: {date, sources, words, seconds} }
let historyIndex = -1;
let displayedMarkdown = "";

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

function formatDate(date) {
  const parts = new Intl.DateTimeFormat("es-ES", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).formatToParts(date);
  const get = (type) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("day")} ${get("month").replace(".", "")} ${get("year")}`.toUpperCase();
}

function extractDomains(markdown) {
  const idx = markdown.search(/##\s*fuentes/i);
  const block = idx >= 0 ? markdown.slice(idx) : markdown;
  const urls = [...block.matchAll(/https?:\/\/[^\s)\]]+/g)].map((m) => m[0]);
  const seen = new Set();
  const domains = [];
  for (const url of urls) {
    try {
      const host = new URL(url).hostname.replace(/^www\./, "");
      if (!seen.has(host)) {
        seen.add(host);
        domains.push(host);
      }
    } catch {
      /* malformed URL, skip */
    }
  }
  return domains;
}

function numberSections(root) {
  let count = 0;
  const titles = [];
  root.querySelectorAll("h2").forEach((h2) => {
    if (/fuentes/i.test(h2.textContent)) return;
    count += 1;
    titles.push(h2.textContent.trim());
    h2.prepend(document.createTextNode(`${String(count).padStart(2, "0")} — `));
  });
  return { count, titles };
}

function enhanceCitations(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const targets = [];
  let node;
  while ((node = walker.nextNode())) {
    if (/\[\d{1,2}\]/.test(node.nodeValue)) targets.push(node);
  }
  for (const textNode of targets) {
    const parts = textNode.nodeValue.split(/(\[\d{1,2}\])/g);
    if (parts.length < 2) continue;
    const frag = document.createDocumentFragment();
    for (const part of parts) {
      const match = part.match(/^\[(\d{1,2})\]$/);
      if (match) {
        const sup = document.createElement("sup");
        sup.textContent = `[${match[1]}]`;
        frag.appendChild(sup);
      } else if (part) {
        frag.appendChild(document.createTextNode(part));
      }
    }
    textNode.parentNode.replaceChild(frag, textNode);
  }
}

function wordCount(markdown) {
  return markdown.trim().split(/\s+/).filter(Boolean).length;
}

function truncate(text, max) {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function setPill(state) {
  const labels = { idle: "en espera", active: "en curso", done: "completado", error: "error" };
  els.pill.className = `pill pill--${state}`;
  els.pill.textContent = labels[state];
}

function setTimelineState(el, state) {
  el.classList.remove("timeline__item--active", "timeline__item--done", "timeline__item--error");
  if (state) el.classList.add(`timeline__item--${state}`);
}

function setBusy(busy) {
  els.prompt.disabled = busy;
  els.send.disabled = busy;
  els.depth.disabled = busy;
  els.lang.disabled = busy;
  if (!busy) els.prompt.focus();
}

function renderReportView(entry) {
  els.empty.hidden = true;
  els.reportView.hidden = false;
  els.report.innerHTML = entry.html;
  numberSections(els.report);
  enhanceCitations(els.report);

  const meta = entry.meta;
  els.reportMeta.innerHTML = "";
  const parts = [meta.date, `${meta.sources} FUENTES`, `${meta.words} PALABRAS`, `${meta.seconds} S`];
  parts.forEach((text, i) => {
    if (i > 0) {
      const sep = document.createElement("span");
      sep.className = "sep";
      sep.textContent = "·";
      els.reportMeta.appendChild(sep);
    }
    els.reportMeta.appendChild(document.createTextNode(text));
  });

  els.topicTitle.textContent = entry.title;
  displayedMarkdown = entry.markdown;
  els.copyBtn.disabled = false;
  els.downloadBtn.disabled = false;
}

function updateHistoryNav() {
  if (history.length < 2) {
    els.historyNav.hidden = true;
    return;
  }
  els.historyNav.hidden = false;
  els.historyPos.textContent = `${historyIndex + 1} / ${history.length}`;
  els.historyPrev.disabled = historyIndex <= 0;
  els.historyNext.disabled = historyIndex >= history.length - 1;
}

els.historyPrev.addEventListener("click", () => {
  if (historyIndex <= 0) return;
  historyIndex -= 1;
  renderReportView(history[historyIndex]);
  updateHistoryNav();
});

els.historyNext.addEventListener("click", () => {
  if (historyIndex >= history.length - 1) return;
  historyIndex += 1;
  renderReportView(history[historyIndex]);
  updateHistoryNav();
});

document.querySelectorAll(".chip-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    els.prompt.value = btn.dataset.prompt;
    els.prompt.focus();
  });
});

function composeMessage(topic, depth, lang) {
  const depthPhrase = {
    baja: "con un nivel de detalle bajo, breve y muy resumido",
    media: "con el nivel de detalle habitual",
    alta: "con un nivel de detalle alto, profundizando más de lo habitual",
  }[depth];
  const langPhrase = lang === "en" ? " Redacta el informe en inglés." : "";
  return `${topic}\n\n(Preferencia de estilo: genera el informe ${depthPhrase}.${langPhrase})`;
}

els.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const topic = els.prompt.value.trim();
  if (!topic) return;

  const depth = els.depth.value;
  const lang = els.lang.value;
  els.prompt.value = "";
  setBusy(true);

  // --- reset the process timeline for this run ---
  els.errorBanner.hidden = true;
  els.note.hidden = true;
  els.noteText.textContent = "";

  setTimelineState(els.planStep, "active");
  els.planSub.textContent = "Analizando el tema…";

  els.searchStep.hidden = true;
  els.queryList.innerHTML = "";
  const queries = new Map(); // run_id -> { liEl, statusEl, countEl, resultCount, failed }

  els.sourcesStep.hidden = true;
  els.sourceChips.innerHTML = "";

  els.reportStep.hidden = true;

  setPill("active");
  const startedAt = performance.now();
  let elapsedSeconds = 0;
  const timerHandle = setInterval(() => {
    elapsedSeconds = (performance.now() - startedAt) / 1000;
    els.elapsed.textContent = `${elapsedSeconds.toFixed(1)} s`;
  }, 200);

  let planMarked = false;
  const markPlanProgressed = () => {
    if (planMarked) return;
    planMarked = true;
    setTimelineState(els.planStep, "done");
  };

  function recomputeSearchSummary() {
    const list = [...queries.values()];
    const totalResults = list.reduce((sum, q) => sum + (q.failed ? 0 : q.resultCount), 0);
    els.searchSub.textContent = `${list.length} consulta${list.length === 1 ? "" : "s"} · ${totalResults} resultado${totalResults === 1 ? "" : "s"}`;
  }

  let reportMarkdown = "";
  let reportHtml = "";
  let reportProduced = false;
  let sawError = false;

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: composeMessage(topic, depth, lang) }),
    });
    if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);

    els.topicTitle.textContent = truncate(topic, TITLE_MAX_CHARS);

    for await (const event of readSSE(response.body)) {
      if (event.type === "step") {
        markPlanProgressed();
        if (event.tool === "tavily_search") {
          els.searchStep.hidden = false;
          setTimelineState(els.searchStep, "active");
          const li = document.createElement("li");
          const statusEl = document.createElement("span");
          statusEl.className = "query-status";
          statusEl.textContent = "…";
          const textEl = document.createElement("span");
          textEl.className = "query-text";
          textEl.textContent = event.input;
          const countEl = document.createElement("span");
          countEl.className = "query-count";
          countEl.textContent = "";
          li.append(statusEl, textEl, countEl);
          els.queryList.appendChild(li);
          queries.set(event.run_id, { liEl: li, statusEl, countEl, resultCount: 0, failed: false });
          recomputeSearchSummary();
        } else if (event.tool === "write_report") {
          els.reportStep.hidden = false;
          setTimelineState(els.reportStep, "active");
          els.reportSub.textContent = "Redactando el informe…";
        }
      } else if (event.type === "step_done") {
        if (event.tool === "tavily_search") {
          const q = queries.get(event.run_id);
          if (q) {
            const failed = typeof event.summary === "string" && event.summary.startsWith("Búsqueda fallida");
            const match = !failed && event.summary.match(/^(\d+)\s+resultados/);
            q.failed = failed;
            q.resultCount = match ? parseInt(match[1], 10) : 0;
            q.liEl.classList.toggle("query--error", failed);
            q.statusEl.textContent = failed ? "⚠" : "✓";
            q.countEl.textContent = failed ? "0" : String(q.resultCount);
          }
          recomputeSearchSummary();
        } else if (event.tool === "write_report") {
          setTimelineState(els.reportStep, "done");
        }
      } else if (event.type === "report") {
        reportProduced = true;
        reportMarkdown = event.markdown;
        reportHtml = event.html;

        const tempRoot = document.createElement("div");
        tempRoot.innerHTML = reportHtml;
        const { count: sectionCount, titles } = numberSections(tempRoot);
        const domains = extractDomains(reportMarkdown);
        const words = wordCount(reportMarkdown);
        const h1 = tempRoot.querySelector("h1");

        els.sourcesStep.hidden = false;
        setTimelineState(els.sourcesStep, "done");
        const searchTotal = [...queries.values()].reduce((sum, q) => sum + (q.failed ? 0 : q.resultCount), 0);
        const pool = Math.max(searchTotal, domains.length);
        els.sourcesSub.textContent = `${domains.length} de ${pool}`;
        els.sourceChips.innerHTML = "";
        domains.slice(0, MAX_CHIPS).forEach((domain) => {
          const chip = document.createElement("span");
          chip.className = "chip";
          chip.textContent = domain;
          els.sourceChips.appendChild(chip);
        });

        els.reportStep.hidden = false;
        els.reportSub.textContent = `${words} palabras · ${sectionCount} sección${sectionCount === 1 ? "" : "es"} · ${domains.length} cita${domains.length === 1 ? "" : "s"}`;

        if (titles.length) {
          els.planSub.textContent = `Ejes: ${titles.join(", ")}.`;
        }

        if (h1) els.topicTitle.textContent = truncate(h1.textContent.trim(), TITLE_MAX_CHARS);

        renderReportView({
          title: h1 ? h1.textContent.trim() : truncate(topic, TITLE_MAX_CHARS),
          markdown: reportMarkdown,
          html: reportHtml,
          meta: {
            date: formatDate(new Date()),
            sources: domains.length,
            words,
            seconds: Math.round(elapsedSeconds),
          },
        });
      } else if (event.type === "token") {
        els.note.hidden = false;
        els.noteText.textContent += event.text;
      } else if (event.type === "error") {
        sawError = true;
        els.errorBanner.hidden = false;
        els.errorBanner.textContent = event.message;
      }
    }
  } catch (err) {
    sawError = true;
    els.errorBanner.hidden = false;
    els.errorBanner.textContent = `No se pudo contactar con el servidor: ${err.message}`;
  } finally {
    clearInterval(timerHandle);
    elapsedSeconds = (performance.now() - startedAt) / 1000;
    els.elapsed.textContent = `${elapsedSeconds.toFixed(1)} s`;
    markPlanProgressed();
    if (els.searchStep.hidden === false) setTimelineState(els.searchStep, "done");
    setPill(sawError && !reportProduced ? "error" : "done");

    if (reportProduced) {
      const words = wordCount(reportMarkdown);
      const domains = extractDomains(reportMarkdown);
      const entry = {
        title: els.topicTitle.textContent,
        markdown: reportMarkdown,
        html: reportHtml,
        meta: {
          date: formatDate(new Date()),
          sources: domains.length,
          words,
          seconds: Math.round(elapsedSeconds),
        },
      };
      history.push(entry);
      historyIndex = history.length - 1;
      renderReportView(entry);
      updateHistoryNav();
      els.prompt.placeholder = "¿Qué quieres ajustar del informe? p. ej. «amplía la sección 2»";
    }

    setBusy(false);
  }
});

els.copyBtn.addEventListener("click", async () => {
  if (!displayedMarkdown) return;
  try {
    await navigator.clipboard.writeText(displayedMarkdown);
  } catch (err) {
    els.errorBanner.hidden = false;
    els.errorBanner.textContent = `No se pudo copiar al portapapeles: ${err.message}`;
  }
});

els.downloadBtn.addEventListener("click", () => {
  if (!displayedMarkdown) return;
  const blob = new Blob([displayedMarkdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "informe.md";
  link.click();
  URL.revokeObjectURL(url);
});

els.prompt.focus();
