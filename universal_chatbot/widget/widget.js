(function () {
  "use strict";

  // Find host script tag and extract parameters (supports website-id, project-id, role, user-id)
  const currentScript = document.currentScript || document.querySelector("script[data-website-id], script[data-project-id]");
  const websiteId = currentScript ? (currentScript.getAttribute("data-project-id") || currentScript.getAttribute("data-website-id") || "site_demo") : "site_demo";
  let candidateRole = (currentScript ? (currentScript.getAttribute("data-role") || "user") : "user").toLowerCase();
  let candidateId = currentScript ? (currentScript.getAttribute("data-user-id") || currentScript.getAttribute("data-candidate-id")) : null;
  const apiBase = currentScript ? (new URL(currentScript.src)).origin : window.location.origin;

  let activeLang = "ta";
  let activeConvId = null;
  let activeSessionId = "sess_" + Math.random().toString(36).substring(2, 10);
  let welcomeSpoken = false;
  let widgetConfig = {
    bot_name: "Universal Assistant",
    primary_color: "#2563eb",
    welcome_message_en: "வணக்கம்! நான் உங்களுக்கு எப்படி உதவலாம்?",
    welcome_message_ta: "வணக்கம்! நான் உங்களுக்கு எப்படி உதவலாம்?",
    available_languages: ["ta"],
    allow_file_uploads: true,
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
    .chat-window { position: fixed; bottom: 96px; right: 24px; width: 390px; height: 580px; max-width: calc(100vw - 32px); max-height: calc(100vh - 120px); background: #ffffff; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.18); display: none; flex-direction: column; overflow: hidden; z-index: 999999; border: 1px solid #e5e7eb; }
    .chat-window.open { display: flex; }
    .chat-header { background: ${widgetConfig.primary_color}; color: #fff; padding: 14px 16px; display: flex; align-items: center; justify-content: space-between; }
    .chat-title { font-weight: 600; font-size: 15px; }
    .lang-select { background: rgba(255,255,255,0.2); color: #fff; border: 1px solid rgba(255,255,255,0.4); border-radius: 6px; padding: 4px 8px; font-size: 12px; cursor: pointer; outline: none; }
    .lang-select option { color: #111; }
    .chat-messages { flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; background: #f9fafb; }
    .msg { max-width: 84%; padding: 10px 14px; border-radius: 14px; font-size: 13.5px; line-height: 1.45; word-wrap: break-word; }
    .msg.user { align-self: flex-end; background: ${widgetConfig.primary_color}; color: #fff; border-bottom-right-radius: 4px; }
    .msg.bot { align-self: flex-start; background: #ffffff; color: #1f2937; border: 1px solid #e5e7eb; border-bottom-left-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .msg.bot h3, .msg.bot h4 { font-size: 13.5px; font-weight: 700; margin: 8px 0 4px 0; color: #111827; }
    .msg.bot ul { margin: 4px 0 6px 18px; }
    .msg.bot li { margin-bottom: 2px; }
    .msg-table-wrap { overflow-x: auto; margin: 6px 0; border: 1px solid #e5e7eb; border-radius: 6px; }
    .msg.bot table { width: 100%; border-collapse: collapse; font-size: 11.5px; }
    .msg.bot th, .msg.bot td { padding: 5px 7px; border-bottom: 1px solid #e5e7eb; text-align: left; white-space: nowrap; }
    .msg.bot th { background: #f3f4f6; font-weight: 600; color: #374151; }
    .msg.bot code { background: #f3f4f6; padding: 1px 4px; border-radius: 3px; font-size: 12px; }
    .msg.system-note { align-self: center; background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; font-size: 12px; border-radius: 8px; max-width: 90%; text-align: center; }
    .msg-actions { display: flex; gap: 8px; margin-top: 6px; font-size: 11px; align-items: center; flex-wrap: wrap; }
    .speak-btn { background: none; border: none; cursor: pointer; color: #6b7280; display: inline-flex; align-items: center; gap: 4px; font-size: 11px; padding: 2px 6px; border-radius: 4px; transition: all 0.15s; }
    .speak-btn:hover { color: ${widgetConfig.primary_color}; background: #f3f4f6; }
    .speak-btn.playing { color: #ef4444; background: #fee2e2; font-weight: 600; }
    .citation-tag { background: #f3f4f6; color: #4b5563; padding: 2px 6px; border-radius: 4px; font-size: 10.5px; display: inline-flex; align-items: center; gap: 3px; border: 1px solid #e5e7eb; }
    .chat-input-area { padding: 10px 12px; background: #fff; border-top: 1px solid #e5e7eb; display: flex; align-items: center; gap: 6px; }
    .chat-input { flex: 1; border: 1px solid #d1d5db; border-radius: 20px; padding: 8px 14px; font-size: 13.5px; outline: none; transition: border-color 0.2s; }
    .chat-input:focus { border-color: ${widgetConfig.primary_color}; }
    .action-btn { background: none; border: none; cursor: pointer; color: #6b7280; display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 50%; transition: background 0.15s; }
    .action-btn:hover { background: #f3f4f6; color: #1f2937; }
    .action-btn.recording { color: #ef4444; animation: pulse 1s infinite; }
    .send-btn { background: ${widgetConfig.primary_color}; color: #fff; width: 32px; height: 32px; border-radius: 50%; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; }
    .send-btn:hover { opacity: 0.9; }
    .support-bar { padding: 6px 12px; background: #f3f4f6; border-top: 1px solid #e5e7eb; text-align: center; font-size: 11.5px; }
    .support-link { color: ${widgetConfig.primary_color}; text-decoration: none; cursor: pointer; font-weight: 500; }
    .suggestions-container { background: #f8fafc; border-top: 1px solid #e5e7eb; padding: 7px 12px; display: none; flex-direction: column; gap: 5px; }
    .suggestions-header { display: flex; align-items: center; justify-content: space-between; font-size: 11px; font-weight: 600; color: #64748b; }
    .suggestions-list { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 3px; scrollbar-width: thin; }
    .suggestions-list::-webkit-scrollbar { height: 4px; }
    .suggestions-list::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
    .sugg-chip { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 14px; padding: 4px 10px; font-size: 11.5px; color: #1e293b; white-space: nowrap; cursor: pointer; transition: all 0.15s; flex-shrink: 0; box-shadow: 0 1px 2px rgba(0,0,0,0.03); }
    .sugg-chip:hover { border-color: ${widgetConfig.primary_color}; color: ${widgetConfig.primary_color}; background: #eff6ff; }
    @keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.15); } 100% { transform: scale(1); } }
  `;

  const template = `
    <style>${styles}</style>
    <button class="chat-btn" id="toggleBtn" aria-label="Open chat">
      <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>
    </button>
    <div class="chat-window" id="chatWin">
      <div class="chat-header">
        <div>
          <span class="chat-title" id="botHeader">${widgetConfig.bot_name}</span>
          <div id="callStatusIndicator" style="font-size: 11px; color: #dbeafe; display: flex; align-items: center; gap: 4px; margin-top: 2px;">
            <span id="callPulseDot" style="width: 7px; height: 7px; border-radius: 50%; background: #22c55e; display: inline-block;"></span>
            <span id="callStatusText">🇮🇳 தமிழ் குரல் AI (Tamil Voice AI)</span>
          </div>
        </div>
        <div style="display: flex; align-items: center; gap: 6px;">
          <button id="callToggleBtn" class="call-btn" style="background: rgba(255,255,255,0.2); border: 1px solid rgba(255,255,255,0.45); color: #fff; border-radius: 14px; padding: 4px 10px; font-size: 11.5px; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 4px; transition: all 0.2s;">
            📞 Voice Call
          </button>
        </div>
      </div>
      <div class="chat-messages" id="msgList"></div>
      <div class="suggestions-container" id="suggBox">
        <div class="suggestions-header">
          <span id="suggTitle">💡 Suggested Questions</span>
        </div>
        <div class="suggestions-list" id="suggList"></div>
      </div>
      <div class="chat-input-area">
        <input type="file" id="filePicker" style="display:none" accept=".pdf,.docx,.xlsx,.pptx,.txt,.csv,.json,.md,.xml,.html,.log,.png,.jpg,.jpeg,.webp,.tiff,.bmp" />
        <button class="action-btn" id="attachBtn" title="Attach any file (PDF, Word, Excel, PowerPoint, Image, TXT, CSV)">
          <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"/></svg>
        </button>
        <button class="action-btn" id="micBtn" title="Speak in Tamil or English">
          <svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>
        </button>
        <input type="text" class="chat-input" id="userInput" placeholder="உங்கள் கேள்வியைக் கேளுங்கள் (Ask in Tamil or English)..." />
        <button class="send-btn" id="sendBtn">
          <svg width="15" height="15" fill="currentColor" viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
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
  const attachBtn = shadow.getElementById("attachBtn");
  const filePicker = shadow.getElementById("filePicker");
  const humanAgentBtn = shadow.getElementById("humanAgentBtn");
  const botHeader = shadow.getElementById("botHeader");
  const callToggleBtn = shadow.getElementById("callToggleBtn");
  const callStatusText = shadow.getElementById("callStatusText");
  const callPulseDot = shadow.getElementById("callPulseDot");

  // Render initial welcome message immediately so it is available before async fetches
  appendMessage("bot", widgetConfig.welcome_message_ta || "வணக்கம்! நான் உங்களுக்கு எப்படி உதவலாம்?");

  // Fetch website config
  fetch(`${apiBase}/api/v1/chat/widget-config/${websiteId}`)
    .then(r => r.json())
    .then(cfg => {
      Object.assign(widgetConfig, cfg);
      botHeader.textContent = widgetConfig.bot_name;
    })
    .catch(() => {});

  // Pre-unlocked HTML5 Audio element for seamless auto-speech without browser autoplay blocks
  let sharedAudio = new Audio();
  let audioUnlocked = false;
  let isCallModeActive = false;

  function unlockAudioPlayback() {
    if (audioUnlocked) return;
    audioUnlocked = true;
    try {
      sharedAudio.src = "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA";
      sharedAudio.play().then(() => {
        sharedAudio.pause();
      }).catch(() => {});
    } catch (_) {}
  }

  // Welcome voice greeting trigger on open
  function speakWelcomeGreeting() {
    if (welcomeSpoken) return;
    welcomeSpoken = true;
    unlockAudioPlayback();
    const welcomeVoiceText = "வணக்கம்! நான் உங்களுக்கு எப்படி உதவலாம்?";
    const firstSpeakBtn = msgList.querySelector(".speak-btn");
    playSpeech(welcomeVoiceText, "ta", firstSpeakBtn, () => {
      if (isCallModeActive) {
        startListening();
      }
    });
  }

  // Fetch candidate's role-specific package questions (Admin, Worker, User)
  const suggBox = shadow.getElementById("suggBox");
  const suggList = shadow.getElementById("suggList");
  const suggTitle = shadow.getElementById("suggTitle");

  function loadRoleSuggestions() {
    const roleParam = encodeURIComponent(candidateRole || "user");
    const idParam = candidateId ? `&candidate_id=${encodeURIComponent(candidateId)}` : "";
    fetch(`${apiBase}/api/v1/projects/${encodeURIComponent(websiteId)}/suggestions?role=${roleParam}${idParam}`)
      .then(r => r.json())
      .then(data => {
        if (data.suggested_questions && data.suggested_questions.length > 0) {
          const roleLabels = {
            admin: "👑 நிர்வாகக் கேள்விகள் / Admin Questions",
            worker: "🛠️ பணியாளர் கேள்விகள் / Worker Questions",
            user: "💡 பரிந்துரைக்கப்பட்ட கேள்விகள் / Suggested Questions"
          };
          suggTitle.textContent = roleLabels[data.role] || (data.package_name || "💡 Suggested Questions");
          suggList.innerHTML = "";
          data.suggested_questions.forEach(q => {
            const chip = document.createElement("button");
            chip.className = "sugg-chip";
            chip.textContent = q;
            chip.onclick = () => {
              unlockAudioPlayback();
              userInput.value = q;
              sendMessage();
            };
            suggList.appendChild(chip);
          });
          suggBox.style.display = "flex";
        }
      })
      .catch(err => console.log("Suggestion package note:", err));
  }
  loadRoleSuggestions();

  // Toggle open/close
  toggleBtn.onclick = () => {
    unlockAudioPlayback();
    chatWin.classList.toggle("open");
    if (chatWin.classList.contains("open")) {
      userInput.focus();
      speakWelcomeGreeting();
    }
  };

  // Toggle live voice call mode
  function setCallMode(active) {
    isCallModeActive = active;
    unlockAudioPlayback();
    if (isCallModeActive) {
      callToggleBtn.innerHTML = "⏹️ End Call";
      callToggleBtn.style.background = "#ef4444";
      callToggleBtn.style.borderColor = "#f87171";
      callStatusText.textContent = "அழைப்பில் உள்ளது (Live Call Active)";
      callPulseDot.style.background = "#ef4444";
      callPulseDot.style.animation = "pulse 1s infinite";
      appendMessage("system-note", "📞 நேரலை குரல் அழைப்பு இணைக்கப்பட்டது. பேசி உரையாடலாம்! (Live Voice Call active. Speak freely!)");
      
      if (!welcomeSpoken) {
        speakWelcomeGreeting();
      } else {
        startListening();
      }
    } else {
      callToggleBtn.innerHTML = "📞 Voice Call";
      callToggleBtn.style.background = "rgba(255,255,255,0.2)";
      callToggleBtn.style.borderColor = "rgba(255,255,255,0.45)";
      callStatusText.textContent = "🇮🇳 தமிழ் குரல் AI (Tamil Voice AI)";
      callPulseDot.style.background = "#22c55e";
      callPulseDot.style.animation = "none";
      stopCurrentAudio();
      if (recognition && micBtn.classList.contains("recording")) {
        try { recognition.stop(); } catch (_) {}
        micBtn.classList.remove("recording");
      }
      appendMessage("system-note", "⏹️ குரல் அழைப்பு நிறைவுற்றது. (Voice call ended.)");
    }
  }

  callToggleBtn.onclick = () => {
    setCallMode(!isCallModeActive);
  };

  // Safe Markdown to HTML formatter (supports bold, italic, headings, lists, and tables)
  function formatMarkdown(text) {
    let escaped = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Parse markdown tables line-by-line
    const lines = escaped.split("\n");
    const out = [];
    let i = 0;
    while (i < lines.length) {
      if (lines[i].trim().startsWith("|") && i + 1 < lines.length && /^\s*\|[\s\-:|]+\|\s*$/.test(lines[i + 1])) {
        const headerCells = lines[i].trim().slice(1, -1).split("|").map(c => c.trim());
        let tbl = '<div class="msg-table-wrap"><table><thead><tr>' +
          headerCells.map(c => `<th>${c}</th>`).join("") +
          '</tr></thead><tbody>';
        i += 2;
        while (i < lines.length && lines[i].trim().startsWith("|")) {
          const rowCells = lines[i].trim().slice(1, -1).split("|").map(c => c.trim());
          tbl += '<tr>' + rowCells.map(c => `<td>${c}</td>`).join("") + '</tr>';
          i++;
        }
        tbl += '</tbody></table></div>';
        out.push(tbl);
      } else {
        out.push(lines[i]);
        i++;
      }
    }

    let html = out.join("\n");
    html = html.replace(/^###\s+(.*)$/gm, "<h3>$1</h3>");
    html = html.replace(/^####\s+(.*)$/gm, "<h4>$1</h4>");
    html = html.replace(/^---$/gm, "<hr style='border:none;border-top:1px solid #e5e7eb;margin:6px 0;'>");
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*(.*?)\*/g, "<em>$1</em>");
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color:#2563eb;font-weight:600;text-decoration:underline;">$1</a>');
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/^\s*[-*]\s+(.*)$/gm, "<li>$1</li>");
    html = html.replace(/(<li>.*<\/li>\n?)+/g, m => `<ul>${m.replace(/\n/g, "")}</ul>`);
    html = html.replace(/\n/g, "<br>");
    return html;
  }

  // Append message to UI
  function appendMessage(role, text, citations = [], action = null) {
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    if (role === "bot") {
      const contentSpan = document.createElement("div");
      contentSpan.innerHTML = formatMarkdown(text);
      div.appendChild(contentSpan);

      if (action) {
        const actionBadge = document.createElement("div");
        actionBadge.style.cssText = "margin-top: 6px; padding: 4px 8px; background: #dbeafe; color: #1e40af; border-radius: 6px; font-size: 11.5px; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;";
        actionBadge.innerHTML = `⚡ Website Action: <span>${action.label || action.action_type}</span>`;
        div.appendChild(actionBadge);
      }
    } else {
      div.textContent = text;
    }

    let createdSpeakBtn = null;
    if (role === "bot") {
      const actions = document.createElement("div");
      actions.className = "msg-actions";

      if (widgetConfig.allow_speech_output) {
        const speakBtn = document.createElement("button");
        speakBtn.className = "speak-btn";
        speakBtn.innerHTML = "🔊 Listen";
        speakBtn.onclick = () => toggleSpeech(text, activeLang, speakBtn);
        actions.appendChild(speakBtn);
        createdSpeakBtn = speakBtn;
      }

      if (citations && citations.length > 0) {
        citations.forEach(c => {
          const citTag = document.createElement("span");
          citTag.className = "citation-tag";
          citTag.textContent = `📌 ${c.title || "Source"}`;
          citTag.title = c.snippet || "";
          actions.appendChild(citTag);
        });
      }

      if (actions.children.length > 0) {
        div.appendChild(actions);
      }
    }

    msgList.appendChild(div);
    msgList.scrollTop = msgList.scrollHeight;
    return { element: div, speakBtn: createdSpeakBtn };
  }

  // High-Definition Neural Speech & Audio Controls
  let currentAudio = null;
  let currentPlayingBtn = null;

  function stopCurrentAudio() {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
      currentAudio = null;
    }
    try {
      sharedAudio.pause();
      sharedAudio.currentTime = 0;
    } catch (_) {}
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    if (currentPlayingBtn) {
      currentPlayingBtn.innerHTML = "🔊 Listen";
      currentPlayingBtn.classList.remove("playing");
      currentPlayingBtn = null;
    }
  }

  function playSpeech(text, lang, btn = null, onEndedCallback = null) {
    if (btn && currentPlayingBtn === btn) {
      stopCurrentAudio();
      return;
    }

    stopCurrentAudio();
    if (btn) {
      btn.innerHTML = "⏳ Loading...";
      btn.classList.add("playing");
      currentPlayingBtn = btn;
    }

    // Clean text before sending to avoid URL/markdown issues
    const cleanText = text
      .replace(/[*#_`|]/g, " ")
      .replace(/https?:\/\/\S+/g, "")
      .replace(/\s+/g, " ")
      .trim()
      .substring(0, 800);

    const targetLang = lang || activeLang;
    const ttsUrl = `${apiBase}/api/v1/voice/tts?text=${encodeURIComponent(cleanText)}&language=${targetLang}`;

    fetch(ttsUrl)
      .then(res => {
        if (!res.ok) throw new Error(`TTS server error (${res.status})`);
        return res.blob();
      })
      .then(blob => {
        if (btn && currentPlayingBtn !== btn) return;
        const blobUrl = URL.createObjectURL(blob);
        
        sharedAudio.src = blobUrl;
        currentAudio = sharedAudio;

        if (btn) btn.innerHTML = "⏹️ Stop";

        sharedAudio.onended = () => {
          URL.revokeObjectURL(blobUrl);
          stopCurrentAudio();
          if (onEndedCallback) onEndedCallback();
        };

        sharedAudio.onerror = (err) => {
          console.warn("sharedAudio error, falling back to browser speech:", err);
          URL.revokeObjectURL(blobUrl);
          playBrowserSpeech(cleanText, targetLang, btn, onEndedCallback);
        };

        const playPromise = sharedAudio.play();
        if (playPromise !== undefined) {
          playPromise.catch(playErr => {
            console.warn("sharedAudio play blocked, using browser fallback:", playErr);
            playBrowserSpeech(cleanText, targetLang, btn, onEndedCallback);
          });
        }
      })
      .catch(err => {
        console.warn("TTS fetch error, using browser fallback:", err);
        playBrowserSpeech(cleanText, targetLang, btn, onEndedCallback);
      });
  }

  function toggleSpeech(text, lang, btn = null) {
    playSpeech(text, lang, btn, null);
  }

  function playBrowserSpeech(text, lang, btn = null, onEndedCallback = null) {
    if (!window.speechSynthesis) {
      stopCurrentAudio();
      if (onEndedCallback) onEndedCallback();
      return;
    }
    window.speechSynthesis.cancel();
    const cleanText = text.replace(/[*#_`|]/g, " ").replace(/\s+/g, " ").trim();
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = lang === "ta" ? "ta-IN" : "en-IN";

    if (lang === "ta") {
      const voices = window.speechSynthesis.getVoices();
      const taVoice = voices.find(v => v.lang.startsWith("ta") || v.name.toLowerCase().includes("tamil"));
      if (taVoice) utterance.voice = taVoice;
    }

    if (btn) {
      btn.innerHTML = "⏹️ Stop";
      btn.classList.add("playing");
      currentPlayingBtn = btn;
    }

    utterance.onend = () => {
      stopCurrentAudio();
      if (onEndedCallback) onEndedCallback();
    };
    utterance.onerror = () => {
      stopCurrentAudio();
      if (onEndedCallback) onEndedCallback();
    };
    window.speechSynthesis.speak(utterance);
  }

  // Execute website actions triggered by voice or text commands
  function executeWebsiteAction(action) {
    if (!action || !action.action_type) return;

    // 1. Dispatch custom DOM event for the host website
    try {
      window.dispatchEvent(new CustomEvent("chatbot:action", { detail: action }));
    } catch (_) {}

    // 2. Built-in website actions
    if (action.action_type === "show_latest_report") {
      const outCard = document.getElementById("outputCard");
      if (outCard) {
        outCard.style.display = "block";
        outCard.scrollIntoView({ behavior: "smooth", block: "start" });
        outCard.style.outline = "3px solid #2563eb";
        outCard.style.transition = "outline 0.4s ease";
        setTimeout(() => { outCard.style.outline = "none"; }, 3000);
      }
      if (typeof window.renderOutput === "function" && action.data) {
        window.renderOutput({ data: action.data });
      }
    } else if (action.action_type === "open_upload") {
      const fileInput = document.getElementById("fileInput");
      const dropZone = document.getElementById("dropZone");
      if (fileInput) fileInput.click();
      else if (dropZone) dropZone.click();
    } else if (action.action_type === "navigate") {
      if (action.target && action.target.startsWith("#")) {
        const targetEl = document.querySelector(action.target);
        if (targetEl) targetEl.scrollIntoView({ behavior: "smooth" });
      } else if (action.url && window.location.pathname !== action.url) {
        window.location.href = action.url;
      }
    }
  }

  // Send message
  function sendMessage(isVoice = false) {
    const text = userInput.value.trim();
    if (!text) return;
    appendMessage("user", text);
    userInput.value = "";
    unlockAudioPlayback();

    const loadingDiv = document.createElement("div");
    loadingDiv.className = "msg bot";
    loadingDiv.textContent = "சிந்திக்கிறது...";
    msgList.appendChild(loadingDiv);
    msgList.scrollTop = msgList.scrollHeight;

    fetch(`${apiBase}/api/v1/chat/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        website_id: websiteId,
        message: text,
        conversation_id: activeConvId,
        session_id: activeSessionId,
        language: activeLang,
        is_voice: isVoice,
        user_id: candidateId,
        role: candidateRole,
      }),
    })
      .then(r => r.json())
      .then(data => {
        loadingDiv.remove();
        activeConvId = data.conversation_id;

        const msgRes = appendMessage("bot", data.reply, data.citations, data.action);

        // Execute website action if command detected
        if (data.action) {
          executeWebsiteAction(data.action);
        }

        // ALWAYS auto-speak every reply in authentic Tamil neural voice!
        if (msgRes && msgRes.speakBtn) {
          playSpeech(data.reply, "ta", msgRes.speakBtn, () => {
            // In Call Mode, automatically activate the mic for the user's turn
            if (isCallModeActive) {
              startListening();
            }
          });
        }

        if (data.escalate_to_human) {
          loadAndOpenTawkTo(data.tawk_property_id, data.tawk_widget_id, data.tawk_direct_url);
        }
      })
      .catch(() => {
        loadingDiv.remove();
        appendMessage("bot", "சேவையகப் பிழை ஏற்பட்டது. மீண்டும் முயற்சிக்கவும்.");
      });
  }

  sendBtn.onclick = () => sendMessage(false);
  userInput.onkeydown = (e) => { if (e.key === "Enter") sendMessage(false); };

  // File Upload Handling
  attachBtn.onclick = () => filePicker.click();
  filePicker.onchange = () => {
    const file = filePicker.files[0];
    if (!file) return;

    const uploadingNote = document.createElement("div");
    uploadingNote.className = "msg system-note";
    uploadingNote.textContent = `⏳ Uploading & indexing '${file.name}'...`;
    msgList.appendChild(uploadingNote);
    msgList.scrollTop = msgList.scrollHeight;

    const formData = new FormData();
    formData.append("file", file);
    formData.append("website_id", websiteId);
    if (activeConvId) formData.append("conversation_id", activeConvId);
    formData.append("session_id", activeSessionId);

    fetch(`${apiBase}/api/v1/documents/upload`, {
      method: "POST",
      body: formData,
    })
      .then(r => r.json())
      .then(res => {
        uploadingNote.remove();
        appendMessage(
          "system-note",
          activeLang === "ta"
            ? `📄 '${file.name}' ஆவணம் இணைக்கப்பட்டது (${res.chunk_count} பிரிவுகள்). இப்போது நீங்கள் இதைப் பற்றிக் கேட்கலாம்!`
            : `📄 Attached '${file.name}' (${res.chunk_count} chunks indexed). You can now ask questions about it!`
        );
      })
      .catch(() => {
        uploadingNote.remove();
        appendMessage("system-note", "❌ File upload failed.");
      });

    filePicker.value = "";
  };

  // Microphone Voice Input (High-Precision STT)
  let recognition = null;
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  function startListening() {
    if (!recognition) return;
    if (micBtn.classList.contains("recording")) return;
    stopCurrentAudio();
    recognition.lang = "ta-IN";
    userInput.value = "";
    userInput.placeholder = "🎙️ தமிழில் பேசவும்... கேட்கிறேன் (Listening... speak)...";
    micBtn.classList.add("recording");
    try {
      recognition.start();
    } catch (err) {
      console.warn("Recognition start note:", err);
      micBtn.classList.remove("recording");
    }
  }

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onresult = (e) => {
      let interim = "";
      let final = "";
      for (let i = e.resultIndex; i < e.results.length; ++i) {
        if (e.results[i].isFinal) {
          final += e.results[i][0].transcript;
        } else {
          interim += e.results[i][0].transcript;
        }
      }

      if (final) {
        userInput.value = final;
        micBtn.classList.remove("recording");
        userInput.placeholder = "உங்கள் கேள்வியைக் கேளுங்கள் (Ask in Tamil or English)...";
        sendMessage(true);
      } else if (interim) {
        userInput.value = interim;
      }
    };

    recognition.onerror = (e) => {
      micBtn.classList.remove("recording");
      console.warn("Speech recognition error:", e.error);
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        appendMessage("system-note", "⚠️ Microphone permission denied. Please allow microphone access in your browser settings (look for the lock/tune icon in the address bar).");
      } else if (e.error === "network") {
        appendMessage("system-note", "⚠️ Speech recognition service unreachable. Please check internet access or type your question.");
      } else if (e.error === "no-speech") {
        if (isCallModeActive) {
          // In Call Mode, if no speech detected after turn, keep listening or prompt gently
          setTimeout(() => { if (isCallModeActive) startListening(); }, 1500);
        } else {
          userInput.placeholder = "பேச்சு கேட்கவில்லை, மீண்டும் பேசவும்...";
          setTimeout(() => {
            userInput.placeholder = "உங்கள் கேள்வியைக் கேளுங்கள் (Ask in Tamil or English)...";
          }, 3000);
        }
      } else {
        userInput.placeholder = "உங்கள் கேள்வியைக் கேளுங்கள் (Ask in Tamil or English)...";
      }
    };

    recognition.onend = () => {
      micBtn.classList.remove("recording");
      if (!userInput.value.trim()) {
        userInput.placeholder = "உங்கள் கேள்வியைக் கேளுங்கள் (Ask in Tamil or English)...";
      }
    };

    micBtn.onclick = () => {
      unlockAudioPlayback();
      if (micBtn.classList.contains("recording")) {
        try { recognition.stop(); } catch (_) {}
        micBtn.classList.remove("recording");
        return;
      }
      startListening();
    };
  } else {
    micBtn.onclick = () => {
      appendMessage("system-note", "⚠️ Voice recognition requires Google Chrome, Microsoft Edge, or Safari over localhost or HTTPS.");
    };
  }

  // Dynamic Tawk.to Live Support Loader & Opener
  function loadAndOpenTawkTo(propertyId, widgetId, directUrl) {
    const propId = propertyId || widgetConfig.tawk_to_property_id || "6afff70e6c90d43c92f4c111";
    const widId = widgetId || widgetConfig.tawk_to_widget_id || "1k7rtq4pg";
    const chatUrl = directUrl || `https://tawk.to/chat/${propId}/${widId}`;

    // 1. If Tawk.to is already active on the host page, maximize it immediately
    if (window.Tawk_API && typeof window.Tawk_API.maximize === "function") {
      try {
        window.Tawk_API.maximize();
        return;
      } catch (_) {}
    }

    // 2. Prepare Tawk.to API callbacks
    window.Tawk_API = window.Tawk_API || {};
    window.Tawk_LoadStart = new Date();
    window.Tawk_API.onLoad = function () {
      try {
        if (typeof window.Tawk_API.maximize === "function") {
          window.Tawk_API.maximize();
        }
      } catch (_) {}
    };

    // 3. Dynamically inject Tawk.to script into document if not already loaded
    const scriptSelector = `script[src*="tawk.to/${propId}"]`;
    if (!document.querySelector(scriptSelector)) {
      const s1 = document.createElement("script");
      s1.async = true;
      s1.src = `https://embed.tawk.to/${propId}/${widId}`;
      s1.charset = "UTF-8";
      s1.setAttribute("crossorigin", "*");
      document.head.appendChild(s1);
    }

    // 4. Also provide a direct 1-click fallback link in the conversation
    appendMessage(
      "system-note",
      activeLang === "ta"
        ? `💬 நேரடி மனித வாடிக்கையாளர் சேவை இணைக்கப்படுகிறது... தானாகத் திறக்கவில்லை என்றால் <a href="${chatUrl}" target="_blank" style="font-weight:bold;color:#0369a1;text-decoration:underline;">இங்கே கிளிக் செய்து நேரலையாகப் பேசலாம்</a>.`
        : `💬 Connecting to live support agent on Tawk.to... If the widget doesn't pop up automatically, <a href="${chatUrl}" target="_blank" style="font-weight:bold;color:#0369a1;text-decoration:underline;">Click Here to Open Direct Chat</a>.`
    );
  }

  // Tawk.to human agent handoff button
  humanAgentBtn.onclick = () => {
    loadAndOpenTawkTo(widgetConfig.tawk_to_property_id, widgetConfig.tawk_to_widget_id);
    userInput.value = activeLang === "ta" ? "வாடிக்கையாளர் சேவை முகவரிடம் பேச வேண்டும்" : "I want to talk to human support";
    sendMessage();
  };

  // Expose global controller for host application testing & role switching
  window.UniversalChatbot = {
    setRole: function (role, id = null, name = null) {
      unlockAudioPlayback();
      candidateRole = (role || "user").toLowerCase();
      candidateId = id;
      activeConvId = null; // Start a clean conversation context for the new candidate profile
      welcomeSpoken = false; // Reset so next open can greet
      loadRoleSuggestions();
      const displayName = name || (id ? `${role} (${id})` : role);
      appendMessage(
        "system-note",
        `🔄 பயனர் கணக்கு மாற்றப்பட்டது: ${displayName}. Strict user isolation active.`
      );
    },
    getRole: function () {
      return candidateRole;
    },
    getUserId: function () {
      return candidateId;
    },
    open: function () {
      unlockAudioPlayback();
      chatWin.classList.add("open");
      userInput.focus();
      speakWelcomeGreeting();
    },
    startCall: function () {
      unlockAudioPlayback();
      chatWin.classList.add("open");
      setCallMode(true);
    },
    close: function () {
      chatWin.classList.remove("open");
    },
  };
})();
