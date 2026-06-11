const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send-btn");
const clearBtn = document.getElementById("clear-btn");
const statusBadge = document.getElementById("status-badge");
const modelNameEl = document.getElementById("model-name");

let isSending = false;

// --- Status polling ---

// The top badge shows the voice pipeline state (see setVoiceState). This poll
// only manages the send button and the model-name indicator.
async function checkStatus() {
    try {
        const res = await fetch("/status");
        const data = await res.json();
        if (data.connected) {
            modelNameEl.textContent = data.model || "";
            if (!isSending) sendBtn.disabled = false;
        } else {
            modelNameEl.textContent = "Ollama offline";
            sendBtn.disabled = true;
        }
    } catch {
        modelNameEl.textContent = "Server offline";
        sendBtn.disabled = true;
    }
}

checkStatus();
setInterval(checkStatus, 10000);

// --- Message rendering ---

function addMessage(role, text) {
    // Remove welcome message on first interaction
    const welcome = messagesEl.querySelector(".welcome-msg");
    if (welcome) welcome.remove();

    const div = document.createElement("div");
    div.className = "msg msg-" + role;
    div.textContent = text;
    messagesEl.appendChild(div);
    scrollToBottom();
    return div;
}

function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

// --- Chat ---

async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text || isSending) return;

    isSending = true;
    sendBtn.disabled = true;
    inputEl.value = "";
    autoResize();

    addMessage("user", text);

    // Add typing indicator
    const typing = document.createElement("div");
    typing.className = "typing";
    typing.textContent = "Reachy is thinking";
    messagesEl.appendChild(typing);
    scrollToBottom();

    let botDiv = null;
    let botText = "";

    try {
        const res = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text }),
        });

        // Remove typing indicator
        typing.remove();

        const reader = res.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split("\n");

            for (const line of lines) {
                if (!line.startsWith("data: ")) continue;
                const data = line.slice(6);

                if (data === "[DONE]") continue;

                // Tool call markers
                if (data.startsWith("\n[Tool: ") || data.startsWith("[Tool: ")) {
                    // Flush current bot message
                    if (botDiv && botText.trim()) {
                        botDiv = null;
                        botText = "";
                    }
                    addMessage("tool", data.trim());
                    continue;
                }

                if (data.startsWith("[Result: ") || data.startsWith("\n[Result: ")) {
                    addMessage("tool", data.trim());
                    continue;
                }

                // Error from LLM
                if (data.startsWith("[LLM error:")) {
                    addMessage("error", data);
                    continue;
                }

                // Regular text token
                if (!botDiv) {
                    botDiv = addMessage("bot", "");
                }
                botText += data;
                botDiv.textContent = botText;
                scrollToBottom();
            }
        }
    } catch (err) {
        typing.remove();
        addMessage("error", "Connection error: " + err.message);
    }

    // Getippte Nachrichten werden NICHT vorgelesen — TTS nur im Sprach-Flow
    // (serverseitige Wake-Word-Pipeline). Reine Textantwort hier.

    isSending = false;
    sendBtn.disabled = false;
    inputEl.focus();
}

// --- Input handling ---

function autoResize() {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + "px";
}

inputEl.addEventListener("input", autoResize);

inputEl.addEventListener("keydown", function(e) {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

sendBtn.addEventListener("click", sendMessage);

// --- Clear ---

clearBtn.addEventListener("click", async function() {
    try {
        await fetch("/clear", { method: "POST" });
    } catch (e) {}

    messagesEl.innerHTML =
        '<div class="welcome-msg">' +
        '<p>Chat with Reachy Mini. The robot can dance, show emotions, and move its head.</p>' +
        '</div>';
});

// --- Voice (WebSocket status channel for the wake-word pipeline) ---

const muteBtn = document.getElementById("mute-btn");

let voiceWs = null;
let voiceMuted = false;

// Pipeline-Zustand → Badge-Text (Deutsch) + Farbklasse.
const VOICE_STATES = {
    idle:       { text: "Warte auf Hey Jarvis…", cls: "badge-idle" },
    wake_word:  { text: "Wake-Word erkannt",     cls: "badge-wake" },
    listening:  { text: "Höre zu…",              cls: "badge-listening" },
    processing: { text: "Verarbeite…",           cls: "badge-processing" },
    speaking:   { text: "Spricht…",              cls: "badge-speaking" },
};

function setVoiceState(value) {
    const state = VOICE_STATES[value] || VOICE_STATES.idle;
    statusBadge.textContent = state.text;
    statusBadge.className = "badge " + state.cls;
}

function connectVoiceWs() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    voiceWs = new WebSocket(`${proto}://${location.host}/ws/voice`);

    voiceWs.onopen = function() {
        // Aktuellen Mute-Zustand mit dem Server synchronisieren.
        voiceWs.send(JSON.stringify({ type: "set_mute", value: voiceMuted }));
    };

    voiceWs.onmessage = function(event) {
        let msg;
        try { msg = JSON.parse(event.data); } catch { return; }

        if (msg.type === "status") {
            setVoiceState(msg.value);
        } else if (msg.type === "chat" && msg.text) {
            addMessage(msg.role === "user" ? "user" : "bot", msg.text);
        }
    };

    voiceWs.onclose = function() {
        voiceWs = null;
        statusBadge.textContent = "Sprachkanal getrennt";
        statusBadge.className = "badge badge-error";
        setTimeout(connectVoiceWs, 2000);  // Reconnect
    };

    voiceWs.onerror = function() {
        if (voiceWs) voiceWs.close();
    };
}

connectVoiceWs();

muteBtn.addEventListener("click", function() {
    voiceMuted = !voiceMuted;
    muteBtn.textContent = voiceMuted ? "🔇" : "🔊";
    muteBtn.classList.toggle("muted", voiceMuted);
    muteBtn.title = voiceMuted ? "TTS einschalten" : "TTS stumm schalten";
    if (voiceWs && voiceWs.readyState === WebSocket.OPEN) {
        voiceWs.send(JSON.stringify({ type: "set_mute", value: voiceMuted }));
    }
});
