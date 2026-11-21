const $ = (id) => document.getElementById(id);

const state = {
  history: [],
  attachments: [],
  busy: false
};

const ALLOWED_EXTENSIONS = new Set([
  ".txt", ".md", ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
  ".html", ".htm", ".css", ".json", ".xml", ".yaml", ".yml", ".sql",
  ".sh", ".java", ".kt", ".php", ".go", ".rs", ".c", ".h", ".cpp",
  ".hpp", ".cs", ".toml", ".ini", ".log", ".csv", ".vue", ".svelte"
]);

const EXT_BY_LANGUAGE = {
  html: "html", htm: "html", python: "py", py: "py", javascript: "js", js: "js",
  typescript: "ts", ts: "ts", css: "css", json: "json", xml: "xml", sql: "sql",
  bash: "sh", sh: "sh", java: "java", kotlin: "kt", php: "php", go: "go",
  rust: "rs", c: "c", cpp: "cpp", csharp: "cs", yaml: "yml", markdown: "md",
  text: "txt", plaintext: "txt"
};

function setConnection(ok, label) {
  $("connectionDot").classList.toggle("online", !!ok);
  $("connectionText").textContent = label;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) }
  });
  let data = {};
  try { data = await response.json(); } catch (_) {}
  if (!response.ok) throw new Error(data.detail || `İstek başarısız (${response.status})`);
  return data;
}

async function refreshStatus() {
  try {
    const data = await api("/api/status");
    const rows = $("modelList").querySelectorAll(".model-row");
    data.providers.forEach((provider, index) => {
      const row = rows[index];
      if (!row) return;
      const dot = row.querySelector(".model-state");
      dot.classList.toggle("ready", provider.configured);
      dot.title = provider.configured ? "API anahtarı ayarlı" : "API anahtarı eksik";
    });
    const gemini = data.providers.find((item) => item.id === "gemini_analyst");
    if (gemini && !gemini.configured) setConnection(true, "Gemini API anahtarı bekleniyor");
    else setConnection(true, "CODETURK hazır");
  } catch (_) {
    setConnection(false, "Bağlantı sorunu");
  }
}

function languageAndFilename(info, index) {
  const clean = (info || "text").trim();
  const language = (clean.split(/\s+/)[0] || "text").toLowerCase();
  const nameMatch = clean.match(/(?:filename|file)\s*=\s*["']?([^\s"']+)["']?/i)
    || clean.match(/\b([A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,8})\b/);
  let filename = nameMatch ? nameMatch[1] : "";
  if (!filename) {
    const ext = EXT_BY_LANGUAGE[language] || "txt";
    filename = index === 0 ? `main.${ext}` : `file-${index + 1}.${ext}`;
  }
  filename = filename.split(/[\\/]/).pop().replace(/[^A-Za-z0-9._-]/g, "_");
  return { language, filename: filename || `file-${index + 1}.txt` };
}

async function copyText(text, button) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand("copy");
      area.remove();
      if (!ok) throw new Error("Kopyalama başarısız");
    }
    const old = button.textContent;
    button.textContent = "Kopyalandı ✓";
    setTimeout(() => { button.textContent = old; }, 1400);
  } catch (_) {
    button.textContent = "Kopyalanamadı";
  }
}

function downloadText(filename, content) {
  const extension = filename.includes(".") ? filename.split(".").pop().toLowerCase() : "txt";
  const mime = extension === "html" || extension === "htm" ? "text/html"
    : extension === "css" ? "text/css"
    : extension === "json" ? "application/json"
    : extension === "js" ? "text/javascript"
    : "text/plain";
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function appendCodeBlock(body, info, source, index) {
  const meta = languageAndFilename(info, index);
  const card = document.createElement("section");
  card.className = "code-file-card";
  const header = document.createElement("div");
  header.className = "code-file-header";
  const filename = document.createElement("span");
  filename.className = "code-file-name";
  filename.textContent = `📄 ${meta.filename}`;
  const actions = document.createElement("div");
  actions.className = "code-file-actions";
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "code-action";
  copy.textContent = "Kopyala";
  copy.addEventListener("click", () => copyText(source, copy));
  const download = document.createElement("button");
  download.type = "button";
  download.className = "code-action primary";
  download.textContent = "Dosyayı indir";
  download.addEventListener("click", () => downloadText(meta.filename, source));
  actions.append(copy, download);
  header.append(filename, actions);
  const pre = document.createElement("pre");
  const code = document.createElement("code");
  code.className = `language-${meta.language}`;
  code.textContent = source;
  pre.appendChild(code);
  card.append(header, pre);
  body.appendChild(card);
}

function renderAssistantText(body, text) {
  const pattern = /```([^\n`]*)\n([\s\S]*?)```/g;
  let cursor = 0;
  let match;
  let codeIndex = 0;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) body.appendChild(document.createTextNode(text.slice(cursor, match.index)));
    appendCodeBlock(body, match[1], match[2].replace(/\n$/, ""), codeIndex++);
    cursor = pattern.lastIndex;
  }
  if (codeIndex === 0) {
    body.appendChild(document.createTextNode(text));
    return;
  }
  if (cursor < text.length) body.appendChild(document.createTextNode(text.slice(cursor)));
}

function addMessage(role, text, fileNames = []) {
  const row = document.createElement("div");
  row.className = `message ${role}`;
  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = role === "user" ? "SEN" : "CT";
  const body = document.createElement("div");
  body.className = "message-body";
  if (role === "assistant") {
    const label = document.createElement("div");
    label.className = "message-label";
    label.textContent = "CODETURK";
    body.appendChild(label);
    renderAssistantText(body, text);
  } else {
    body.appendChild(document.createTextNode(text));
    if (fileNames.length) {
      const names = document.createElement("div");
      names.className = "sent-file-list";
      names.textContent = `📎 ${fileNames.join(", ")}`;
      body.appendChild(names);
    }
  }
  row.append(avatar, body);
  $("messages").appendChild(row);
  $("messages").scrollTop = $("messages").scrollHeight;
}

function updatePipeline(steps, busy = false) {
  $("pipeline").classList.remove("hidden");
  $("pipelineTitle").textContent = busy ? "Model ekibi çalışıyor" : "İşlem özeti";
  $("pipelineSteps").replaceChildren();
  (steps || []).forEach((step) => {
    const item = document.createElement("span");
    item.className = `pipeline-step ${step.status === "ok" || step.status === "fallback" ? "ok" : step.status === "error" || step.status === "missing_key" ? "error" : ""}`;
    const status = step.status === "ok" ? "tamamlandı"
      : step.status === "fallback" ? "yedek"
      : step.status === "missing_key" ? "anahtar eksik" : "hata";
    item.textContent = `${step.name}: ${status}`;
    $("pipelineSteps").appendChild(item);
  });
}

function renderAttachments() {
  const holder = $("attachmentList");
  holder.replaceChildren();
  state.attachments.forEach((file, index) => {
    const chip = document.createElement("span");
    chip.className = "attachment-chip";
    const label = document.createElement("span");
    label.textContent = file.name;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", `${file.name} dosyasını kaldır`);
    remove.textContent = "×";
    remove.addEventListener("click", () => {
      state.attachments.splice(index, 1);
      renderAttachments();
    });
    chip.append(label, remove);
    holder.appendChild(chip);
  });
}

$("fileInput").addEventListener("change", (event) => {
  const incoming = Array.from(event.target.files || []);
  for (const file of incoming) {
    const ext = "." + file.name.split(".").pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS.has(ext)) {
      alert(`${file.name}: Bu dosya türü desteklenmiyor.`);
      continue;
    }
    if (file.size > 200 * 1024) {
      alert(`${file.name}: Dosya 200 KB sınırından büyük.`);
      continue;
    }
    if (state.attachments.length >= 5) {
      alert("En fazla 5 dosya ekleyebilirsin.");
      break;
    }
    if (!state.attachments.some((item) => item.name === file.name)) state.attachments.push(file);
  }
  event.target.value = "";
  renderAttachments();
});

async function sendMessage(text) {
  let message = (text || $("messageInput").value).trim();
  if (!message && state.attachments.length) message = "Eklediğim dosyaları incele ve dosyalardaki isteğime göre yardımcı ol.";
  if ((!message && !state.attachments.length) || state.busy) return;

  state.busy = true;
  const filesToSend = [...state.attachments];
  const fileNames = filesToSend.map((file) => file.name);
  $("welcome").classList.add("hidden");
  $("chatTitle").textContent = "Sohbet";
  $("messageInput").value = "";
  $("messageInput").style.height = "auto";
  $("sendBtn").disabled = true;
  $("pipeline").classList.remove("hidden");
  $("pipelineTitle").textContent = "İstek analiz ediliyor";
  $("pipelineSteps").replaceChildren();
  addMessage("user", message, fileNames);

  try {
    const attachments = await Promise.all(filesToSend.map(async (file) => ({
      name: file.name,
      content: await file.text()
    })));
    const result = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        mode: $("modeSelect").value,
        history: state.history.slice(-12).map((item) => ({ ...item, content: item.content.slice(0, 7000) })),
        attachments
      })
    });
    state.history.push({ role: "user", content: message });
    state.history.push({ role: "assistant", content: result.reply.slice(0, 7000) });
    state.history = state.history.slice(-20);
    addMessage("assistant", result.reply);
    updatePipeline(result.pipeline, false);
    state.attachments = [];
    renderAttachments();
    if (result.degraded) {
      const note = document.createElement("div");
      note.className = "error-banner";
      note.textContent = "Not: Bazı modeller yanıt veremedi veya yedek model kullanıldı. İşlem özetini kontrol et.";
      $("messages").appendChild(note);
    }
  } catch (error) {
    addMessage("assistant", `İstek tamamlanamadı: ${error.message}`);
    updatePipeline([{ name: "İstek", status: "error" }], false);
  } finally {
    state.busy = false;
    $("sendBtn").disabled = false;
    $("messageInput").focus();
  }
}

$("chatForm").addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage();
});

$("messageInput").addEventListener("input", () => {
  const input = $("messageInput");
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
});

$("messageInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    $("chatForm").requestSubmit();
  }
});

$("newChatBtn").addEventListener("click", () => {
  state.history = [];
  state.attachments = [];
  renderAttachments();
  $("messages").replaceChildren();
  $("pipeline").classList.add("hidden");
  $("welcome").classList.remove("hidden");
  $("chatTitle").textContent = "Nasıl yardımcı olabilirim?";
});

document.querySelectorAll(".suggestion").forEach((button) => {
  button.addEventListener("click", () => sendMessage(button.dataset.prompt));
});

(async function init() {
  try {
    const health = await api("/api/health");
    setConnection(true, `${health.app} hazır`);
    await refreshStatus();
  } catch (_) {
    setConnection(false, "Sunucuya ulaşılamıyor");
  }
})();
