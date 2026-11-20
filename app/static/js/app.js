const $ = (id) => document.getElementById(id);

const state = {
  history: [],
  busy: false
};

function setConnection(ok, label) {
  $("connectionDot").classList.toggle("online", !!ok);
  $("connectionText").textContent = label;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });

  let data = {};

  try {
    data = await response.json();
  } catch (_) {}

  if (!response.ok) {
    throw new Error(
      data.detail || `İstek başarısız (${response.status})`
    );
  }

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
      dot.title = provider.configured
        ? "API anahtarı ayarlı"
        : "API anahtarı eksik";
    });

    setConnection(true, "CODETURK hazır");

  } catch (_) {
    setConnection(false, "Bağlantı sorunu");
  }
}

function addMessage(role, text) {
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
  }

  body.appendChild(document.createTextNode(text));

  row.append(avatar, body);

  $("messages").appendChild(row);
  $("messages").scrollTop = $("messages").scrollHeight;
}

function updatePipeline(steps, busy = false) {
  $("pipeline").classList.remove("hidden");

  $("pipelineTitle").textContent = busy
    ? "Model ekibi çalışıyor"
    : "İşlem özeti";

  $("pipelineSteps").replaceChildren();

  (steps || []).forEach((step) => {
    const item = document.createElement("span");

    item.className =
      `pipeline-step ${
        step.status === "ok" || step.status === "fallback"
          ? "ok"
          : step.status === "error" || step.status === "missing_key"
            ? "error"
            : ""
      }`;

    const status =
      step.status === "ok"
        ? "tamamlandı"
        : step.status === "fallback"
          ? "yedek"
          : step.status === "missing_key"
            ? "anahtar eksik"
            : "hata";

    item.textContent = `${step.name}: ${status}`;

    $("pipelineSteps").appendChild(item);
  });
}

async function sendMessage(text) {
  const message = (text || $("messageInput").value).trim();

  if (!message || state.busy) return;

  state.busy = true;

  $("welcome").classList.add("hidden");
  $("chatTitle").textContent = "Sohbet";

  $("messageInput").value = "";
  $("messageInput").style.height = "auto";

  $("sendBtn").disabled = true;

  $("pipeline").classList.remove("hidden");
  $("pipelineTitle").textContent = "İstek analiz ediliyor";
  $("pipelineSteps").replaceChildren();

  addMessage("user", message);

  try {
    const result = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        mode: $("modeSelect").value,
        history: state.history.slice(-12)
      })
    });

    state.history.push({
      role: "user",
      content: message
    });

    state.history.push({
      role: "assistant",
      content: result.reply
    });

    state.history = state.history.slice(-20);

    addMessage("assistant", result.reply);

    updatePipeline(result.pipeline, false);

    if (result.degraded) {
      const note = document.createElement("div");

      note.className = "error-banner";

      note.textContent =
        "Not: Bazı modeller yanıt veremedi veya yedek model kullanıldı. İşlem özetini kontrol et.";

      $("messages").appendChild(note);
    }

  } catch (error) {
    addMessage(
      "assistant",
      `İstek tamamlanamadı: ${error.message}`
    );

    updatePipeline([
      {
        name: "İstek",
        status: "error"
      }
    ], false);

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

  input.style.height =
    `${Math.min(input.scrollHeight, 160)}px`;
});

$("messageInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    $("chatForm").requestSubmit();
  }
});

$("newChatBtn").addEventListener("click", () => {
  state.history = [];

  $("messages").replaceChildren();

  $("pipeline").classList.add("hidden");
  $("welcome").classList.remove("hidden");

  $("chatTitle").textContent =
    "Nasıl yardımcı olabilirim?";
});

document.querySelectorAll(".suggestion").forEach((button) => {
  button.addEventListener("click", () => {
    sendMessage(button.dataset.prompt);
  });
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
