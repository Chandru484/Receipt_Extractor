(function () {
  "use strict";

  // Find host script tag and extract parameters
  const currentScript = document.currentScript || document.querySelector("script[data-website-id]");
  const websiteId = currentScript ? currentScript.getAttribute("data-website-id") : "site_demo";
  const apiBase = currentScript ? (new URL(currentScript.src)).origin : window.location.origin;

  let activeLang = "en";
  let activeConvId = null;
  let widgetConfig = {
    bot_name: "AI Assistant",
    primary_color: "#2563eb",
    welcome_message_en: "Hello! How can I help you today?",
    welcome_message_ta: "வணக்கம்! இன்று நான் உங்களுக்கு எவ்வாறு உதவ முடியும்?",
    available_languages: ["en", "ta"],
    allow_voice_input: true,
    allow_speech_output: true,
    enable_tawk_to: false,
    tawk_to_property_id: null,
  };

  // Host container
  const hostDiv = document.createElement("div");
  hostDiv.id = "universal-ai-chatbot-root";
  document.body.appendChild(hostDiv);

  // Shadow DOM for complete CSS isolation
  const shadow = hostDiv.attachShadow({ mode: "open" });

  const styles = `
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    .chat-btn { position: fixed; bottom: 24px; right: 24px; width: 60px; height: 60px; border-radius: 50%; background: ${widgetConfig.primary_color}; color: #fff; border: none; cursor: pointer; box-shadow: 0 4px 16px rgba(0,0,0,0.2); display: flex; align-items: center; justify-content: center; z-index: 999999; transition: transform 0.2s; }
    .chat-btn:hover { transform: scale(1.06); }
    .chat-btn svg { width: 30px; height: 30px; fill: currentColor; }
    .chat-window { position: fixed; bottom: 96px; right: 24px; width: 380px; height: 560px; max-width: calc(100vw - 32px); max-height: calc(100vh - 120px); background: #ffffff; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.18); display: none; flex-direction: column; overflow: hidden; z-index: 999999; border: 1px solid #e5e7eb; }
    .chat-window.open { display: flex; }
    .chat-header { background: ${widgetConfig.primary_color}; color: #fff; padding: 14px 16px; display: flex; align-items: center; justify-content: space-between; }
    .chat-title { font-weight: 600; font-size: 15px; }
    .lang-select { background: rgba(255,255,255,0.2); color: #fff; border: 1px solid rgba(255,255,255,0.4); border-radius: 6px; padding: 4px 8px; font-size: 12px; cursor: pointer; outline: none; }
    .lang-select option { color: #111; }
    .chat-messages { flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; background: #f9fafb; }
    .msg { max-width: 82%; padding: 10px 14px; border-radius: 14px; font-size: 13.5px; line-height: 1.45; word-wrap: break-word; }
    .msg.user { align-self: flex-end; background: ${widgetConfig.primary_color}; color: #fff; border-bottom-right-radius: 4px; }
    .msg.bot { align-self: flex-start; background: #ffffff; color: #1f2937; border: 1px solid #e5e7eb; border-bottom-left-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .msg-actions { display: flex; gap: 6px; margin-top: 4px; font-size: 11px; }
    .speak-btn { background: none; border: none; cursor: pointer; color: #6b7280; display: inline-flex; align-items: center; padding: 2px; }
    .speak-btn:hover { color: ${widgetConfig.primary_color}; }
    .chat-input-area { padding: 10px 12px; background: #fff; border-top: 1px solid #e5e7eb; display: flex; align-items: center; gap: 8px; }
    .chat-input { flex: 1; border: 1px solid #d1d5db; border-radius: 20px; padding: 8px 14px; font-size: 13.5px; outline: none; transition: border-color 0.2s; }
    .chat-input:focus { border-color: ${widgetConfig.primary_color}; }
    .action-btn { background: none; border: none; cursor: pointer; color: #6b7280; display: flex; align-items: center; justify-content: center; width: 34px; height: 34px; border-radius: 50%; transition: background 0.15s; }
    .action-btn:hover { background: #f3f4f6; color: #1f2937; }
    .action-btn.recording { color: #ef4444; animation: pulse 1s infinite; }
    .send-btn { background: ${widgetConfig.primary_color}; color: #fff; width: 34px; height: 34px; border-radius: 50%; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; }
    .send-btn:hover { opacity: 0.9; }
    .support-bar { padding: 6px 12px; background: #f3f4f6; border-top: 1px solid #e5e7eb; text-align: center; font-size: 11.5px; }
    .support-link { color: ${widgetConfig.primary_color}; text-decoration: none; cursor: pointer; font-weight: 500; }
    @keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.15); } 100% { transform: scale(1); } }
  `;

  const template = `
    <style>${styles}</style>
    <button class="chat-btn" id="toggleBtn" aria-label="Open chat">
      <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>
    </button>
    <div class="chat-window" id="chatWin">
      <div class="chat-header">
        <span class="chat-title" id="botHeader">${widgetConfig.bot_name}</span>
        <select class="lang-select" id="langSelect">
          <option value="en">English</option>
          <option value="ta">தமிழ்</option>
        </select>
      </div>
      <div class="chat-messages" id="msgList"></div>
      <div class="chat-input-area">
        <button class="action-btn" id="micBtn" title="Speak in Tamil or English">
          <svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>
        </button>
        <input type="text" class="chat-input" id="userInput" placeholder="Ask a question..." />
        <button class="send-btn" id="sendBtn">
          <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
        </button>
      </div>
      <div class="support-bar" id="supportBar">
        Need help? <a class="support-link" id="humanAgentBtn">Talk to a Human Agent</a>
      </div>
    </div>
  `;

  shadow.innerHTML = template;

  const toggleBtn = shadow.getElementById("toggleBtn");
  const chatWin = shadow.getElementById("chatWin");
  const msgList = shadow.getElementById("msgList");
  const userInput = shadow.getElementById("userInput");
  const sendBtn = shadow.getElementById("sendBtn");
  const micBtn = shadow.getElementById("micBtn");
  const langSelect = shadow.getElementById("langSelect");
  const humanAgentBtn = shadow.getElementById("humanAgentBtn");
  const botHeader = shadow.getElementById("botHeader");

  // Fetch website config
  fetch(`${apiBase}/api/v1/chat/widget-config/${websiteId}`)
    .then(r => r.json())
    .then(cfg => {
      Object.assign(widgetConfig, cfg);
      botHeader.textContent = widgetConfig.bot_name;
      appendMessage("bot", activeLang === "ta" ? widgetConfig.welcome_message_ta : widgetConfig.welcome_message_en);
    })
    .catch(() => {
      appendMessage("bot", widgetConfig.welcome_message_en);
    });

  // Toggle open/close
  toggleBtn.onclick = () => {
    chatWin.classList.toggle("open");
    if (chatWin.classList.contains("open")) userInput.focus();
  };

  // Language switch
  langSelect.onchange = (e) => {
    activeLang = e.target.value;
    userInput.placeholder = activeLang === "ta" ? "உங்கள் கேள்வியைக் கேளுங்கள்..." : "Ask a question...";
    appendMessage("bot", activeLang === "ta" ? "மொழி தமிழுக்கு மாற்றப்பட்டது." : "Language changed to English.");
  };

  // Append message to UI
  function appendMessage(role, text) {
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    div.textContent = text;

    if (role === "bot" && widgetConfig.allow_speech_output) {
      const actions = document.createElement("div");
      actions.className = "msg-actions";
      const speakBtn = document.createElement("button");
      speakBtn.className = "speak-btn";
      speakBtn.innerHTML = "🔊 Listen";
      speakBtn.onclick = () => speakText(text, activeLang);
      actions.appendChild(speakBtn);
      div.appendChild(actions);
    }

    msgList.appendChild(div);
    msgList.scrollTop = msgList.scrollHeight;
  }

  // Text to Speech
  function speakText(text, lang) {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const cleanText = text.replace(/[*#_`]/g, "");
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = lang === "ta" ? "ta-IN" : "en-US";
    window.speechSynthesis.speak(utterance);
  }

  // Send message
  function sendMessage() {
    const text = userInput.value.trim();
    if (!text) return;
    appendMessage("user", text);
    userInput.value = "";

    const loadingDiv = document.createElement("div");
    loadingDiv.className = "msg bot";
    loadingDiv.textContent = activeLang === "ta" ? "சிந்திக்கிறது..." : "Thinking...";
    msgList.appendChild(loadingDiv);
    msgList.scrollTop = msgList.scrollHeight;

    fetch(`${apiBase}/api/v1/chat/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        website_id: websiteId,
        message: text,
        conversation_id: activeConvId,
        language: activeLang,
      }),
    })
      .then(r => r.json())
      .then(data => {
        loadingDiv.remove();
        activeConvId = data.conversation_id;
        appendMessage("bot", data.reply);
        if (data.escalate_to_human && window.Tawk_API) {
          window.Tawk_API.maximize();
        }
      })
      .catch(() => {
        loadingDiv.remove();
        appendMessage("bot", activeLang === "ta" ? "சேவையகப் பிழை ஏற்பட்டது." : "Could not connect to server.");
      });
  }

  sendBtn.onclick = sendMessage;
  userInput.onkeydown = (e) => { if (e.key === "Enter") sendMessage(); };

  // Microphone Voice Input
  let recognition = null;
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onresult = (e) => {
      const transcript = e.results[0][0].transcript;
      userInput.value = transcript;
      micBtn.classList.remove("recording");
      sendMessage();
    };

    recognition.onerror = () => micBtn.classList.remove("recording");
    recognition.onend = () => micBtn.classList.remove("recording");

    micBtn.onclick = () => {
      recognition.lang = activeLang === "ta" ? "ta-IN" : "en-US";
      micBtn.classList.add("recording");
      recognition.start();
    };
  } else {
    micBtn.style.display = "none";
  }

  // Tawk.to human agent handoff button
  humanAgentBtn.onclick = () => {
    if (window.Tawk_API) {
      window.Tawk_API.maximize();
    } else {
      userInput.value = activeLang === "ta" ? "வாடிக்கையாளர் சேவை முகவரிடம் பேச வேண்டும்" : "I want to talk to human support";
      sendMessage();
    }
  };
})();
