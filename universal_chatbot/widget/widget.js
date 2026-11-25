(function () {
  "use strict";

  // Find host script tag and extract parameters (supports website-id, project-id, role, user-id)
  const currentScript = document.currentScript || document.querySelector("script[data-website-id], script[data-project-id]");
  const websiteId = currentScript ? (currentScript.getAttribute("data-project-id") || currentScript.getAttribute("data-website-id") || "site_demo") : "site_demo";
  let candidateRole = (currentScript ? (currentScript.getAttribute("data-role") || "user") : "user").toLowerCase();
  let candidateId = currentScript ? (currentScript.getAttribute("data-user-id") || currentScript.getAttribute("data-candidate-id")) : null;
  const apiBase = currentScript ? (new URL(currentScript.src)).origin : window.location.origin;

  let activeLang = "en";
  let activeConvId = null;
  let activeSessionId = "sess_" + Math.random().toString(36).substring(2, 10);
  let widgetConfig = {
    bot_name: "Universal Assistant",
    primary_color: "#2563eb",
    welcome_message_en: "Hello! How can I help you today? You can ask questions, query records, or attach a document.",
    welcome_message_ta: "வணக்கம்! இன்று நான் உங்களுக்கு எவ்வாறு உதவ முடியும்? நீங்கள் கேள்விகள் கேட்கலாம், பதிவுகளைப் பார்க்கலாம் அல்லது ஆவணங்களை இணைக்கலாம்.",
    available_languages: ["en", "ta"],
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
        <span class="chat-title" id="botHeader">${widgetConfig.bot_name}</span>
        <select class="lang-select" id="langSelect">
          <option value="en">English</option>
          <option value="ta">தமிழ்</option>
        </select>
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
        <input type="text" class="chat-input" id="userInput" placeholder="Ask a question or request records..." />
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
            admin: "👑 Admin Questions",
            worker: "🛠️ Worker Questions",
            user: "💡 Suggested Questions"
          };
          suggTitle.textContent = roleLabels[data.role] || (data.package_name || "💡 Suggested Questions");
          suggList.innerHTML = "";
          data.suggested_questions.forEach(q => {
            const chip = document.createElement("button");
            chip.className = "sugg-chip";
            chip.textContent = q;
            chip.onclick = () => {
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
    chatWin.classList.toggle("open");
    if (chatWin.classList.contains("open")) userInput.focus();
  };

  // Language switch
  langSelect.onchange = (e) => {
    activeLang = e.target.value;
    userInput.placeholder = activeLang === "ta" ? "உங்கள் கேள்வியைக் கேளுங்கள்..." : "Ask a question...";
    appendMessage("bot", activeLang === "ta" ? "மொழி தமிழுக்கு மாற்றப்பட்டது." : "Language changed to English.");
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
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    if (currentPlayingBtn) {
      currentPlayingBtn.innerHTML = "🔊 Listen";
      currentPlayingBtn.classList.remove("playing");
      currentPlayingBtn = null;
    }
  }

  function toggleSpeech(text, lang, btn) {
    if (currentPlayingBtn === btn) {
      stopCurrentAudio();
      return;
    }

    stopCurrentAudio();
    btn.innerHTML = "⏹️ Stop";
    btn.classList.add("playing");
    currentPlayingBtn = btn;

    // Call High-Definition Native Neural Audio Stream
    const ttsUrl = `${apiBase}/api/v1/voice/tts?text=${encodeURIComponent(text)}&language=${lang}`;
    const audio = new Audio(ttsUrl);
    currentAudio = audio;

    audio.onended = () => stopCurrentAudio();
    audio.onerror = () => {
      // Fallback to browser SpeechSynthesis if server audio is blocked
      console.warn("Backend neural audio stream unavailable, using browser voice fallback.");
      playBrowserSpeech(text, lang, btn);
    };

    audio.play().catch(err => {
      console.warn("Audio playback error, using browser fallback:", err);
      playBrowserSpeech(text, lang, btn);
    });
  }

  function playBrowserSpeech(text, lang, btn) {
    if (!window.speechSynthesis) {
      stopCurrentAudio();
      return;
    }
    window.speechSynthesis.cancel();
    const cleanText = text.replace(/[*#_`|]/g, " ").replace(/\s+/g, " ").trim();
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = lang === "ta" ? "ta-IN" : "en-US";

    if (lang === "ta") {
      const voices = window.speechSynthesis.getVoices();
      const taVoice = voices.find(v => v.lang.startsWith("ta") || v.name.toLowerCase().includes("tamil"));
      if (taVoice) utterance.voice = taVoice;
    }

    utterance.onend = () => stopCurrentAudio();
    utterance.onerror = () => stopCurrentAudio();
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
        session_id: activeSessionId,
        language: activeLang,
        is_voice: isVoice,
      }),
    })
      .then(r => r.json())
      .then(data => {
        loadingDiv.remove();
        activeConvId = data.conversation_id;

        // Auto-synchronize UI language if query was detected in another language (e.g. Tamil voice)
        if (data.language && data.language !== activeLang) {
          activeLang = data.language;
          langSelect.value = activeLang;
          userInput.placeholder = activeLang === "ta" ? "உங்கள் கேள்வியைக் கேளுங்கள்..." : "Ask a question...";
        }

        const msgRes = appendMessage("bot", data.reply, data.citations, data.action);

        // Execute website action if command detected
        if (data.action) {
          executeWebsiteAction(data.action);
        }

        // Auto-reply in voice if queried by voice or backend signaled is_voice
        if (isVoice || data.is_voice) {
          if (msgRes && msgRes.speakBtn) {
            toggleSpeech(data.reply, data.language, msgRes.speakBtn);
          }
        }

        if (data.escalate_to_human && window.Tawk_API) {
          window.Tawk_API.maximize();
        }
      })
      .catch(() => {
        loadingDiv.remove();
        appendMessage("bot", activeLang === "ta" ? "சேவையகப் பிழை ஏற்பட்டது." : "Could not connect to server.");
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
        userInput.placeholder = activeLang === "ta" ? "உங்கள் கேள்வியைக் கேளுங்கள்..." : "Ask a question...";
        sendMessage(true);
      } else if (interim) {
        userInput.value = interim;
      }
    };

    recognition.onerror = () => {
      micBtn.classList.remove("recording");
      userInput.placeholder = activeLang === "ta" ? "உங்கள் கேள்வியைக் கேளுங்கள்..." : "Ask a question...";
    };

    recognition.onend = () => {
      micBtn.classList.remove("recording");
      userInput.placeholder = activeLang === "ta" ? "உங்கள் கேள்வியைக் கேளுங்கள்..." : "Ask a question...";
    };

    micBtn.onclick = () => {
      if (micBtn.classList.contains("recording")) {
        recognition.stop();
        micBtn.classList.remove("recording");
        return;
      }
      stopCurrentAudio();
      recognition.lang = activeLang === "ta" ? "ta-IN" : "en-US";
      userInput.value = "";
      userInput.placeholder = activeLang === "ta" ? "🎙️ தமிழில் பேசுங்கள்... கேட்கிறேன்..." : "🎙️ Listening... please speak...";
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

  // Expose global controller for host application testing & role switching
  window.UniversalChatbot = {
    setRole: function (role, id = null) {
      candidateRole = (role || "user").toLowerCase();
      candidateId = id;
      loadRoleSuggestions();
    },
    getRole: function () {
      return candidateRole;
    },
    open: function () {
      chatWin.classList.add("open");
    },
    close: function () {
      chatWin.classList.remove("open");
    },
  };
})();
