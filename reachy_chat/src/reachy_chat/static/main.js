const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send-btn");
const clearBtn = document.getElementById("clear-btn");
const statusBadge = document.getElementById("status-badge");
const modelNameEl = document.getElementById("model-name");

let isSending = false;

// --- Status polling ---

async function checkStatus() {
    try {
        const res = await fetch("/status");
        const data = await res.json();
        if (data.connected) {
            statusBadge.textContent = "connected";
            statusBadge.className = "badge badge-ok";
            modelNameEl.textContent = data.model || "";
            if (!isSending) sendBtn.disabled = false;
        } else {
            statusBadge.textContent = "disconnected";
            statusBadge.className = "badge badge-error";
            sendBtn.disabled = true;
        }
    } catch {
        statusBadge.textContent = "offline";
        statusBadge.className = "badge badge-error";
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

    // Trigger TTS via voice WebSocket if active and not muted
    if (voiceWs && voiceWs.readyState === WebSocket.OPEN && !voiceMuted && botText) {
        voiceWs.send(JSON.stringify({ type: "speak", text: botText }));
    }

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

// --- Voice (WebSocket, Push-to-Talk) ---

const micBtn = document.getElementById("mic-btn");
const muteBtn = document.getElementById("mute-btn");
const voiceStatusBar = document.getElementById("voice-status-bar");
const voiceStatusText = document.getElementById("voice-status-text");

let voiceWs = null;
let voiceMuted = false;
let voiceRecording = false;
let micPressed = false;

const VOICE_STATUS_LABELS = {
    listening:  "🎤 Aufnahme …",
    processing: "⚙️ Verarbeite …",
    speaking:   "🔊 Reachy spricht …",
};

function setVoiceStatus(value) {
    const label = VOICE_STATUS_LABELS[value] || "";
    if (label) {
        voiceStatusText.textContent = label;
        voiceStatusBar.classList.remove("hidden");
    } else {
        voiceStatusBar.classList.add("hidden");
    }
    micBtn.className = "btn-mic " + (value || "");
}

function connectVoiceWs(onOpen) {
    if (voiceWs && (voiceWs.readyState === WebSocket.OPEN || voiceWs.readyState === WebSocket.CONNECTING)) {
        if (voiceWs.readyState === WebSocket.OPEN) {
            if (onOpen) onOpen();
        } else if (onOpen) {
            voiceWs.addEventListener("open", onOpen, { once: true });
        }
        return;
    }
    const proto = location.protocol === "https:" ? "wss" : "ws";
    voiceWs = new WebSocket(`${proto}://${location.host}/ws/voice`);

    if (onOpen) {
        voiceWs.addEventListener("open", onOpen, { once: true });
    }

    voiceWs.onmessage = function(event) {
        let msg;
        try { msg = JSON.parse(event.data); } catch { return; }
        console.log("[voice] ←", msg);

        if (msg.type === "status") {
            setVoiceStatus(msg.value);
        } else if (msg.type === "transcript" && msg.text) {
            console.log("[voice] transcript:", msg.text);
            inputEl.value = msg.text;
            autoResize();
            setVoiceStatus(null);
            sendMessage();
        }
    };

    voiceWs.onclose = function() {
        voiceWs = null;
        voiceRecording = false;
        micBtn.className = "btn-mic";
        setVoiceStatus(null);
    };

    voiceWs.onerror = function() {
        voiceWs = null;
        voiceRecording = false;
        micBtn.className = "btn-mic";
        setVoiceStatus(null);
    };
}

function startRecording() {
    connectVoiceWs(function() {
        if (!micPressed) { console.log("[voice] released before WS open, skip"); return; }
        console.log("[voice] → start_recording");
        voiceWs.send(JSON.stringify({ type: "start_recording" }));
        voiceRecording = true;
    });
}

function stopRecording() {
    micPressed = false;
    console.log("[voice] stopRecording called, voiceRecording=", voiceRecording, "wsState=", voiceWs?.readyState);
    if (voiceWs && voiceWs.readyState === WebSocket.OPEN && voiceRecording) {
        console.log("[voice] → stop_recording");
        voiceWs.send(JSON.stringify({ type: "stop_recording" }));
        voiceRecording = false;
    }
}

// Push-to-talk: press = start recording, release anywhere = stop + transcribe
micBtn.addEventListener("mousedown", function(e) {
    e.preventDefault();
    micPressed = true;
    startRecording();
});
document.addEventListener("mouseup", stopRecording);

micBtn.addEventListener("touchstart", function(e) {
    e.preventDefault();
    micPressed = true;
    startRecording();
}, { passive: false });
document.addEventListener("touchend", stopRecording);
document.addEventListener("touchcancel", stopRecording);

muteBtn.addEventListener("click", function() {
    voiceMuted = !voiceMuted;
    muteBtn.textContent = voiceMuted ? "🔇" : "🔊";
    muteBtn.classList.toggle("muted", voiceMuted);
    muteBtn.title = voiceMuted ? "TTS einschalten" : "TTS stumm schalten";
});
