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
    bot_name: "AI Assistant",
    primary_color: "#2563eb",
    welcome_message_en: "வணக்கம்! சொல்லுங்க, உங்களுக்கு நான் எப்படி உதவலாம்?",
    welcome_message_ta: "வணக்கம்! சொல்லுங்க, உங்களுக்கு நான் எப்படி உதவலாம்?",
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
    .chat-header { background: ${widgetConfig.primary_color}; color: #fff; padding: 14px 16px; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .chat-title { font-weight: 600; font-size: 15px; }
    .header-btn { background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.35); color: #fff; border-radius: 14px; padding: 4px 9px; font-size: 11px; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; transition: all 0.15s; font-weight: 500; }
    .header-btn:hover { background: rgba(255,255,255,0.3); }
    .header-btn.active { background: #16a34a !important; border-color: #22c55e !important; color: #fff !important; font-weight: 700; box-shadow: 0 0 10px rgba(34, 197, 94, 0.5); }
    .call-banner { background: #0f172a; color: #f8fafc; padding: 8px 14px; font-size: 11.5px; display: flex; align-items: center; justify-content: space-between; gap: 8px; border-bottom: 1px solid #1e293b; transition: all 0.2s; }
    .audio-waveform { display: inline-flex; align-items: center; gap: 3.5px; height: 18px; padding: 0 2px; }
    .wave-bar { width: 3.5px; height: 5px; border-radius: 4px; background: #64748b; transition: height 0.15s ease, background 0.2s ease; }
    
    .call-banner.speaking .wave-bar {
      background: linear-gradient(180deg, #38bdf8, #2563eb);
      animation: waveJump 0.75s infinite ease-in-out alternate;
    }
    .call-banner.listening .wave-bar {
      background: linear-gradient(180deg, #4ade80, #16a34a);
      animation: waveJump 0.55s infinite ease-in-out alternate;
    }
    .call-banner.thinking .wave-bar {
      background: linear-gradient(180deg, #c084fc, #7c3aed);
      animation: wavePulse 0.9s infinite ease-in-out alternate;
    }
    .call-banner.speaking .bar-1 { animation-delay: 0.0s; }
    .call-banner.speaking .bar-2 { animation-delay: 0.18s; }
    .call-banner.speaking .bar-3 { animation-delay: 0.35s; }
    .call-banner.speaking .bar-4 { animation-delay: 0.12s; }
    .call-banner.speaking .bar-5 { animation-delay: 0.26s; }

    .call-banner.listening .bar-1 { animation-delay: 0.05s; }
    .call-banner.listening .bar-2 { animation-delay: 0.22s; }
    .call-banner.listening .bar-3 { animation-delay: 0.10s; }
    .call-banner.listening .bar-4 { animation-delay: 0.32s; }
    .call-banner.listening .bar-5 { animation-delay: 0.18s; }

    .call-banner.thinking .bar-1 { animation-delay: 0.0s; }
    .call-banner.thinking .bar-2 { animation-delay: 0.15s; }
    .call-banner.thinking .bar-3 { animation-delay: 0.3s; }
    .call-banner.thinking .bar-4 { animation-delay: 0.15s; }
    .call-banner.thinking .bar-5 { animation-delay: 0.0s; }

    @keyframes waveJump {
      0% { height: 4px; }
      50% { height: 18px; }
      100% { height: 7px; }
    }
    @keyframes wavePulse {
      0% { height: 5px; opacity: 0.5; }
      100% { height: 13px; opacity: 1; }
    }

    .mini-waveform { display: inline-flex; align-items: center; gap: 2px; height: 12px; margin-right: 3px; }
    .mbar { width: 2.5px; height: 4px; background: currentColor; border-radius: 2px; animation: miniWave 0.7s infinite alternate ease-in-out; }
    .mbar:nth-child(1) { animation-delay: 0.0s; }
    .mbar:nth-child(2) { animation-delay: 0.2s; }
    .mbar:nth-child(3) { animation-delay: 0.4s; }
    @keyframes miniWave { 0% { height: 3px; } 100% { height: 11px; } }

    .end-call-btn { background: #dc2626; color: #fff; border: none; border-radius: 10px; padding: 3px 8px; font-size: 10.5px; cursor: pointer; font-weight: 600; transition: background 0.15s; }
    .end-call-btn:hover { background: #b91c1c; }
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
          <div style="font-size: 11px; color: #dbeafe; display: flex; align-items: center; gap: 4px; margin-top: 2px;">
            <span style="width: 7px; height: 7px; border-radius: 50%; background: #22c55e; display: inline-block;"></span>
            <span>🇮🇳 தமிழ் குரல் AI (Tamil Voice AI)</span>
          </div>
        </div>
        <div style="display: flex; align-items: center; gap: 6px;">
          <button class="header-btn" id="voiceEngineBtn" title="Switch Voice Engine: ⚡ Instant (0s Delay) vs 🎧 HD Cloud Voice">
            <span id="voiceEngineIcon">⚡</span>
            <span id="voiceEngineLabel">Instant</span>
          </button>
          <button class="header-btn" id="callModeBtn" title="Start Hands-Free Voice Call (தொடர் குரல் அழைப்பு)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M20.01 15.38c-1.23 0-2.42-.2-3.53-.56a.977.977 0 00-1.01.24l-1.57 1.97c-2.83-1.44-5.15-3.75-6.59-6.59l1.97-1.57c.28-.28.36-.67.25-1.02A11.36 11.36 0 018.96 4.3c0-.55-.45-1-1-1H4.45c-.55 0-1 .45-1 1 0 9.39 7.61 17 17 17 .55 0 1-.45 1-1v-3.56c0-.55-.45-.96-.44-.96z"/></svg>
            <span id="callModeLabel">Voice Call</span>
          </button>
          <button class="header-btn" id="newChatBtn" title="Start New Conversation (புதிய அரட்டை)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
            <span>New Chat</span>
          </button>
        </div>
      </div>
      <div class="call-banner" id="callBanner" style="display: none;">
        <div style="display: flex; align-items: center; gap: 10px;">
          <div class="audio-waveform" id="callWaveform">
            <span class="wave-bar bar-1"></span>
            <span class="wave-bar bar-2"></span>
            <span class="wave-bar bar-3"></span>
            <span class="wave-bar bar-4"></span>
            <span class="wave-bar bar-5"></span>
          </div>
          <span id="callBannerText" style="font-weight: 500;">📞 நேரலை குரல் அழைப்பு (Live Call Active)</span>
        </div>
        <button id="endCallBtn" class="end-call-btn">End Call</button>
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
        <span id="supportText">Need help? <a class="support-link" id="humanAgentBtn">Talk to a Human Agent</a></span>
        <span id="tawkActiveControls" style="display:none; align-items:center; justify-content:center; gap:8px;">
          <span>💬 Live Support Active</span>
          <button id="hideTawkBtn" style="background:#fee2e2; color:#b91c1c; border:1px solid #fca5a5; border-radius:10px; padding:2px 8px; font-size:11px; cursor:pointer; font-weight:600;">❌ Remove Live Chat</button>
        </span>
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
  const supportText = shadow.getElementById("supportText");
  const tawkActiveControls = shadow.getElementById("tawkActiveControls");
  const hideTawkBtn = shadow.getElementById("hideTawkBtn");
  const botHeader = shadow.getElementById("botHeader");
  const newChatBtn = shadow.getElementById("newChatBtn");
  const callModeBtn = shadow.getElementById("callModeBtn");
  const callModeLabel = shadow.getElementById("callModeLabel");
  const callBanner = shadow.getElementById("callBanner");
  const callBannerText = shadow.getElementById("callBannerText");
  const endCallBtn = shadow.getElementById("endCallBtn");
  const voiceEngineBtn = shadow.getElementById("voiceEngineBtn");
  const voiceEngineIcon = shadow.getElementById("voiceEngineIcon");
  const voiceEngineLabel = shadow.getElementById("voiceEngineLabel");

  let voiceEngine = localStorage.getItem("chat_voice_engine") || "instant"; // default to instant for zero latency

  function updateVoiceEngineUI() {
    if (!voiceEngineBtn) return;
    if (voiceEngine === "instant") {
      if (voiceEngineIcon) voiceEngineIcon.textContent = "⚡";
      if (voiceEngineLabel) voiceEngineLabel.textContent = "Instant";
      voiceEngineBtn.title = "Current: ⚡ Instant Device Voice (Zero Delay). Click to switch to 🎧 HD Cloud Voice.";
    } else {
      if (voiceEngineIcon) voiceEngineIcon.textContent = "🎧";
      if (voiceEngineLabel) voiceEngineLabel.textContent = "HD Voice";
      voiceEngineBtn.title = "Current: 🎧 HD Cloud Voice (Edge Neural). Click to switch to ⚡ Instant Device Voice.";
    }
  }
  updateVoiceEngineUI();

  if (voiceEngineBtn) {
    voiceEngineBtn.onclick = () => {
      voiceEngine = voiceEngine === "instant" ? "hd" : "instant";
      localStorage.setItem("chat_voice_engine", voiceEngine);
      updateVoiceEngineUI();
    };
  }

  let isCallModeActive = false;
  let isSpeaking = false;
  let isProcessingMessage = false;

  function playListeningChime() {
    try {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return;
      const ctx = new AudioContextClass();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = "sine";
      // Gentle two-tone chime: D5 (587.33Hz) then A5 (880Hz)
      osc.frequency.setValueAtTime(587.33, ctx.currentTime);
      osc.frequency.setValueAtTime(880, ctx.currentTime + 0.08);
      gain.gain.setValueAtTime(0.1, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.25);
    } catch (_) {}
  }

  function toggleCallMode() {
    unlockAudioPlayback();
    if (isCallModeActive) {
      endCallMode();
    } else {
      startCallMode();
    }
  }

  function startCallMode() {
    isCallModeActive = true;
    if (callModeBtn) callModeBtn.classList.add("active");
    if (callBanner) {
      callBanner.style.display = "flex";
      callBanner.classList.remove("listening");
    }
    if (callBannerText) callBannerText.textContent = "📞 நேரலை குரல் அழைப்பு துவங்கியது...";
    appendMessage(
      "system-note",
      activeLang === "ta"
        ? "📞 நேரலை தொடர் குரல் அழைப்பு துவங்கப்பட்டுள்ளது. நீங்கள் இனி எதையும் அழுத்தாமல் தொடர்ச்சியாக தமிழில் பேசலாம்!"
        : "📞 Hands-Free Voice Call active. You can now speak back and forth continuously without clicking any buttons!"
    );

    const firstSpeakBtn = msgList.querySelector(".speak-btn");
    const welcomeVoiceText = activeLang === "ta" ? "சொல்லுங்க, கேட்கிறேன்..." : "I'm listening, please go ahead...";
    playSpeech(welcomeVoiceText, activeLang, firstSpeakBtn);
  }

  function endCallMode() {
    isCallModeActive = false;
    isSpeaking = false;
    if (callModeBtn) callModeBtn.classList.remove("active");
    if (callBanner) {
      callBanner.style.display = "none";
      callBanner.classList.remove("speaking", "listening", "thinking");
    }
    stopCurrentAudio();
    if (recognition) {
      try { recognition.stop(); } catch (_) {}
    }
    if (micBtn) micBtn.classList.remove("recording");
  }

  if (callModeBtn) callModeBtn.onclick = toggleCallMode;
  if (endCallBtn) endCallBtn.onclick = endCallMode;

  function removeTawkTo(notify = true) {
    if (window.Tawk_API && typeof window.Tawk_API.hideWidget === "function") {
      try { window.Tawk_API.hideWidget(); } catch (_) {}
    }
    // Visually hide any injected Tawk elements or iframes in the host DOM
    document.querySelectorAll('iframe[src*="tawk.to"], div[id*="tawk"], div[class*="tawk"]').forEach(el => {
      try {
        el.style.setProperty("display", "none", "important");
      } catch (_) {
        el.style.display = "none";
      }
    });

    if (tawkActiveControls) tawkActiveControls.style.display = "none";
    if (supportText) supportText.style.display = "inline";

    if (notify) {
      appendMessage(
        "system-note",
        activeLang === "ta"
          ? "✅ Tawk.to நேரடி அரட்டை விட்ஜெட் திரையிலிருந்து அகற்றப்பட்டது."
          : "✅ Tawk.to live chat widget removed from screen."
      );
    }
  }

  if (hideTawkBtn) {
    hideTawkBtn.onclick = () => removeTawkTo(true);
  }

  function resetConversation(clearMessages = true, welcomeText = null) {
    stopCurrentAudio();
    endCallMode();
    removeTawkTo(false);
    activeConvId = null;
    activeSessionId = "sess_" + Math.random().toString(36).substring(2, 10);
    welcomeSpoken = false;
    if (filePicker) filePicker.value = "";
    if (clearMessages) {
      msgList.innerHTML = "";
      const greeting = welcomeText || widgetConfig.welcome_message_ta || "வணக்கம்! சொல்லுங்க, உங்களுக்கு நான் எப்படி உதவலாம்?";
      appendMessage("bot", greeting);
    }
  }

  if (newChatBtn) {
    newChatBtn.onclick = () => {
      unlockAudioPlayback();
      resetConversation(true);
      speakWelcomeGreeting();
    };
  }

  // Render initial welcome message immediately so it is available before async fetches
  appendMessage("bot", widgetConfig.welcome_message_ta || "வணக்கம்! சொல்லுங்க, உங்களுக்கு நான் எப்படி உதவலாம்?");

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

  // Welcome voice greeting trigger on initial widget open
  function speakWelcomeGreeting() {
    if (welcomeSpoken || msgList.children.length > 2) return;
    welcomeSpoken = true;
    unlockAudioPlayback();
    const welcomeVoiceText = activeLang === "ta" ? "வணக்கம்! சொல்லுங்க, என்ன உதவி வேணும்?" : "Hello! How can I help you today?";
    const firstSpeakBtn = msgList.querySelector(".speak-btn");
    playSpeech(welcomeVoiceText, activeLang, firstSpeakBtn);
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

  function sanitizeTamilTextForSpeech(text) {
    if (!text) return "";
    let cleaned = text
      .replace(/[*#_`|]/g, " ")
      .replace(/https?:\/\/\S+/g, "")
      .replace(/உங்களுக்கு\s*வேற\s*ஏதாச்சும்\s*உதவி\s*வேணுமா[?.]?/gi, "")
      .replace(/\bBuyer\s*\(\s*Bill\s*to\s*\)\s*details\b/gi, "வாங்குபவர் விவரங்கள்:")
      .replace(/\bBuyer\s*details\b/gi, "வாங்குபவர் விவரங்கள்:")
      .replace(/\bSeller\s*details\b/gi, "விற்பனையாளர் விவரங்கள்:")
      .replace(/\bCompany\s*:/gi, "நிறுவனம்:")
      .replace(/\bAddress\s*:/gi, "முகவரி:")
      .replace(/\bGSTIN\s*\/\s*UIN\s*:/gi, "ஜி.எஸ்.டி எண்:")
      .replace(/\bGSTIN\s*:/gi, "ஜி.எஸ்.டி எண்:")
      .replace(/\bErode\b/gi, "ஈரோடு")
      .replace(/\bEerodu\b/gi, "ஈரோடு")
      .replace(/\bCoimbatore\b/gi, "கோயம்புத்தூர்")
      .replace(/\bCovai\b/gi, "கோவை")
      .replace(/\bSalem\b/gi, "சேலம்")
      .replace(/\bChennai\b/gi, "சென்னை")
      .replace(/\bMadurai\b/gi, "மதுரை")
      .replace(/\bTirupur\b/gi, "திருப்பூர்")
      .replace(/\bTrichy\b/gi, "திருச்சி")
      .replace(/\bTamil\s*Nadu\b/gi, "தமிழ்நாடு")
      .replace(/(?<=\d),(?=\d)/g, "")
      .replace(/₹\s*([\d,]+)\.\d+/g, "₹ $1")
      .replace(/Rs\.?\s*([\d,]+)\.\d+/g, "Rs $1")
      .replace(/([\d,]+)\.00\b/g, "$1")
      .replace(/₹/g, " ரூபாய் ")
      .replace(/Rs\.?/g, " ரூபாய் ")
      .replace(/%/g, " சதவீதம் ")
      .replace(/\bபண்ணியிருக்கீங்க\b/g, "பண்ணி இருக்கீங்க")
      .replace(/\bபண்ணியிருக்கேன்\b/g, "பண்ணி இருக்கேன்")
      .replace(/\bசெலவாகியிருக்குங்க\b/g, "செலவாகி இருக்குங்க")
      .replace(/\bசெலவாகியிருக்கு\b/g, "செலவாகி இருக்கு")
      .replace(/\bபில்கள்ல\b/g, "பில்களில்")
      .replace(/\bNo\s*[:.]?\s*(\d+)/gi, "எண் $1")
      .replace(/\bBus\s*Stand\b/gi, "பஸ் ஸ்டாண்ட்")
      .replace(/\bComplex\b/gi, "காம்ப்ளக்ஸ்")
      .replace(/\bRoad\b/gi, "ரோடு")
      .replace(/\bStreet\b/gi, "தெரு")
      .replace(/\bTechnologies\b/gi, "டெக்னாலஜிஸ்")
      .replace(/\bSoftwares\b/gi, "சாப்ட்வேர்ஸ்")
      .replace(/\bSurya\b/gi, "சூர்யா")
      .replace(/\bAgency\b/gi, "ஏஜென்சி")
      .replace(/\bElectricals\b/gi, "எலக்ட்ரிக்கல்ஸ்")
      .replace(/\bAI\b/g, "ஏ.ஐ")
      .replace(/\bPDF\b/g, "பி.டி.எஃப்")
      .replace(/\bG\s*Pay\b/gi, "ஜி பே")
      .replace(/[-\u2010-\u2015\u2212]\s*(\d{6})\b/g, " பின்கோடு $1")
      .replace(/ஜி\.எஸ்\.டி எண்:?\s*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1})/g, (m, g) => "ஜி.எஸ்.டி எண் " + g.split("").join(" "))
      .replace(/[:;]/g, " ")
      .replace(/\//g, " அல்லது ")
      .replace(/[()]/g, ", ")
      .replace(/\s+/g, " ")
      .trim();
    return cleaned.substring(0, 800);
  }

  function playSpeech(text, lang, btn = null, onEndedCallback = null) {
    if (btn && currentPlayingBtn === btn) {
      stopCurrentAudio();
      return;
    }

    stopCurrentAudio();
    const cleanText = sanitizeTamilTextForSpeech(text);
    const targetLang = lang || activeLang;

    // Instant Mode: Start speaking immediately in 20ms with local native device engine
    if (voiceEngine === "instant") {
      playBrowserSpeech(cleanText, targetLang, btn, onEndedCallback);
      return;
    }

    // HD Cloud Mode: Microsoft Edge Neural TTS with pre-warmed streaming & 1.1s watchdog
    if (btn) {
      btn.innerHTML = '<span class="mini-waveform"><span class="mbar"></span><span class="mbar"></span><span class="mbar"></span></span> ⏳ Loading...';
      btn.classList.add("playing");
      currentPlayingBtn = btn;
    }

    const ttsUrl = `${apiBase}/api/v1/voice/tts?text=${encodeURIComponent(cleanText)}&language=${targetLang}`;
    sharedAudio.src = ttsUrl;
    currentAudio = sharedAudio;

    let watchdogTimer = setTimeout(() => {
      if (!isSpeaking) {
        console.warn("HD Cloud voice buffering, switching to instant voice to avoid delay");
        playBrowserSpeech(cleanText, targetLang, btn, onEndedCallback);
      }
    }, 1100);

    sharedAudio.onplay = () => {
      clearTimeout(watchdogTimer);
      isSpeaking = true;
      if (btn) btn.innerHTML = '<span class="mini-waveform"><span class="mbar"></span><span class="mbar"></span><span class="mbar"></span></span> ⏹️ Stop';
      if (isCallModeActive) {
        if (callBanner) {
          callBanner.classList.remove("listening", "thinking");
          callBanner.classList.add("speaking");
        }
        if (callBannerText) callBannerText.textContent = "🔊 AI பேசுகிறது... (AI Speaking...)";
      }
    };

    sharedAudio.onended = () => {
      clearTimeout(watchdogTimer);
      isSpeaking = false;
      stopCurrentAudio();
      if (onEndedCallback) onEndedCallback();
      if (isCallModeActive) {
        if (callBanner) {
          callBanner.classList.remove("speaking", "thinking");
          callBanner.classList.add("listening");
        }
        if (callBannerText) callBannerText.textContent = "🎙️ உங்களைக் கேட்கிறது... (Listening to you...)";
        playListeningChime();
        setTimeout(() => {
          if (isCallModeActive && !isSpeaking && !isProcessingMessage) {
            startListening();
          }
        }, 380);
      }
    };

    sharedAudio.onerror = (err) => {
      clearTimeout(watchdogTimer);
      console.warn("sharedAudio stream error, falling back to browser speech:", err);
      playBrowserSpeech(cleanText, targetLang, btn, onEndedCallback);
    };

    const playPromise = sharedAudio.play();
    if (playPromise !== undefined) {
      playPromise.catch(playErr => {
        clearTimeout(watchdogTimer);
        console.warn("sharedAudio play blocked, using browser fallback:", playErr);
        playBrowserSpeech(cleanText, targetLang, btn, onEndedCallback);
      });
    }
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
    const cleanText = sanitizeTamilTextForSpeech(text);
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = lang === "ta" ? "ta-IN" : "en-IN";
    utterance.rate = 1.0;

    if (lang === "ta") {
      const voices = window.speechSynthesis.getVoices();
      const taVoice = voices.find(v => (v.lang && v.lang.replace("_", "-").startsWith("ta")) || (v.name && (v.name.toLowerCase().includes("tamil") || v.name.toLowerCase().includes("heera") || v.name.toLowerCase().includes("valluvar"))));
      if (taVoice) utterance.voice = taVoice;
    }

    if (btn) {
      btn.innerHTML = '<span class="mini-waveform"><span class="mbar"></span><span class="mbar"></span><span class="mbar"></span></span> ⏹️ Stop';
      btn.classList.add("playing");
      currentPlayingBtn = btn;
    }

    utterance.onstart = () => {
      isSpeaking = true;
      if (isCallModeActive) {
        if (callBanner) {
          callBanner.classList.remove("listening", "thinking");
          callBanner.classList.add("speaking");
        }
        if (callBannerText) callBannerText.textContent = "🔊 AI பேசுகிறது... (AI Speaking...)";
      }
    };

    utterance.onend = () => {
      isSpeaking = false;
      stopCurrentAudio();
      if (onEndedCallback) onEndedCallback();
      if (isCallModeActive) {
        if (callBanner) {
          callBanner.classList.remove("speaking", "thinking");
          callBanner.classList.add("listening");
        }
        if (callBannerText) callBannerText.textContent = "🎙️ உங்களைக் கேட்கிறது... (Listening to you...)";
        playListeningChime();
        setTimeout(() => {
          if (isCallModeActive && !isSpeaking && !isProcessingMessage) {
            startListening();
          }
        }, 380);
      }
    };
    utterance.onerror = () => {
      isSpeaking = false;
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
    isProcessingMessage = true;
    if (isCallModeActive) {
      if (callBanner) {
        callBanner.classList.remove("speaking", "listening");
        callBanner.classList.add("thinking");
      }
      if (callBannerText) callBannerText.textContent = "⏳ சிந்திக்கிறது... (Thinking...)";
    }

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
        isProcessingMessage = false;
        loadingDiv.remove();
        activeConvId = data.conversation_id;

        const msgRes = appendMessage("bot", data.reply, data.citations, data.action);

        // Execute website action if command detected
        if (data.action) {
          executeWebsiteAction(data.action);
        }

        // Auto-speak reply in authentic Tamil neural voice
        if (msgRes && msgRes.speakBtn) {
          playSpeech(data.reply, "ta", msgRes.speakBtn);
        }

        if (data.escalate_to_human) {
          loadAndOpenTawkTo(data.tawk_property_id, data.tawk_widget_id, data.tawk_direct_url);
        }
      })
      .catch(() => {
        isProcessingMessage = false;
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
    if (isCallModeActive) {
      if (callBanner) {
        callBanner.classList.remove("speaking", "thinking");
        callBanner.classList.add("listening");
      }
      if (callBannerText) callBannerText.textContent = "🎙️ உங்களைக் கேட்கிறது... (Listening to you...)";
    }
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
        if (isCallModeActive) {
          if (callBanner) callBanner.classList.remove("listening");
          if (callBannerText) callBannerText.textContent = "⏳ சிந்திக்கிறது... (Thinking...)";
        }
        sendMessage(true);
      } else if (interim) {
        userInput.value = interim;
        if (isCallModeActive && callBannerText) {
          callBannerText.textContent = `🎙️ "${interim}"...`;
        }
      }
    };

    recognition.onerror = (e) => {
      micBtn.classList.remove("recording");
      console.warn("Speech recognition error:", e.error);
      if (e.error === "no-speech") {
        if (isCallModeActive && !isSpeaking && !isProcessingMessage) {
          if (callBannerText) callBannerText.textContent = "🎙️ மீண்டும் பேசவும்... (Listening...)";
          setTimeout(() => {
            if (isCallModeActive && !isSpeaking && !isProcessingMessage && !micBtn.classList.contains("recording")) {
              startListening();
            }
          }, 1200);
          return;
        }
        userInput.placeholder = "பேச்சு கேட்கவில்லை, மீண்டும் பேசவும்...";
        setTimeout(() => {
          userInput.placeholder = "உங்கள் கேள்வியைக் கேளுங்கள் (Ask in Tamil or English)...";
        }, 3000);
      } else if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        if (isCallModeActive) endCallMode();
        appendMessage("system-note", "⚠️ Microphone permission denied. Please allow microphone access in your browser settings (look for the lock/tune icon in the address bar).");
      } else if (e.error === "network") {
        if (isCallModeActive) endCallMode();
        appendMessage("system-note", "⚠️ Speech recognition service unreachable. Please check internet access or type your question.");
      } else {
        userInput.placeholder = "உங்கள் கேள்வியைக் கேளுங்கள் (Ask in Tamil or English)...";
      }
    };

    recognition.onend = () => {
      micBtn.classList.remove("recording");
      if (!userInput.value.trim()) {
        userInput.placeholder = "உங்கள் கேள்வியைக் கேளுங்கள் (Ask in Tamil or English)...";
      }
      if (isCallModeActive && !isSpeaking && !isProcessingMessage) {
        setTimeout(() => {
          if (isCallModeActive && !isSpeaking && !isProcessingMessage && !micBtn.classList.contains("recording")) {
            startListening();
          }
        }, 1200);
      }
    };

    micBtn.onclick = () => {
      unlockAudioPlayback();
      if (isSpeaking) {
        stopCurrentAudio();
      }
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

    // Switch support bar to active controls
    if (tawkActiveControls) tawkActiveControls.style.display = "inline-flex";
    if (supportText) supportText.style.display = "none";

    // Restore visibility if previously hidden
    document.querySelectorAll('iframe[src*="tawk.to"], div[id*="tawk"], div[class*="tawk"]').forEach(el => {
      try {
        el.style.removeProperty("display");
      } catch (_) {
        el.style.display = "";
      }
    });

    // 1. Prepare Tawk.to API callbacks & prevent overlapping when minimized
    window.Tawk_API = window.Tawk_API || {};
    window.Tawk_LoadStart = new Date();

    // When user minimizes Tawk chat, hide widget completely so it NEVER covers our chatbot!
    window.Tawk_API.onChatMinimized = function () {
      try {
        if (typeof window.Tawk_API.hideWidget === "function") {
          window.Tawk_API.hideWidget();
        }
      } catch (_) {}
    };

    window.Tawk_API.onLoad = function () {
      try {
        if (typeof window.Tawk_API.showWidget === "function") {
          window.Tawk_API.showWidget();
        }
        if (typeof window.Tawk_API.maximize === "function") {
          window.Tawk_API.maximize();
        }
      } catch (_) {}
    };

    // If already loaded, show and maximize immediately
    if (typeof window.Tawk_API.showWidget === "function") {
      try {
        window.Tawk_API.showWidget();
        if (typeof window.Tawk_API.maximize === "function") {
          window.Tawk_API.maximize();
        }
        return;
      } catch (_) {}
    }

    // 2. Dynamically inject Tawk.to script into document if not already loaded
    const scriptSelector = `script[src*="tawk.to/${propId}"]`;
    if (!document.querySelector(scriptSelector)) {
      const s1 = document.createElement("script");
      s1.async = true;
      s1.src = `https://embed.tawk.to/${propId}/${widId}`;
      s1.charset = "UTF-8";
      s1.setAttribute("crossorigin", "*");
      document.head.appendChild(s1);
    }

    // 3. Also provide a direct 1-click fallback link in the conversation
    appendMessage(
      "system-note",
      activeLang === "ta"
        ? `💬 நேரடி மனித வாடிக்கையாளர் சேவை இணைக்கப்படுகிறது... (<a href="${chatUrl}" target="_blank" style="font-weight:bold;color:#0369a1;text-decoration:underline;">இங்கே கிளிக் செய்து நேரலையாகப் பேசலாம்</a>)`
        : `💬 Connecting to live support agent on Tawk.to... (<a href="${chatUrl}" target="_blank" style="font-weight:bold;color:#0369a1;text-decoration:underline;">Click Here to Open Direct Chat</a>)`
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
      const displayName = name || (id ? `${role} (${id})` : role);
      // Clean previous messages and session context for strict candidate data isolation
      resetConversation(true);
      loadRoleSuggestions();
      appendMessage(
        "system-note",
        `🔄 பயனர் கணக்கு மாற்றப்பட்டது: ${displayName}. Strict user isolation active.`
      );
    },
    newChat: function () {
      unlockAudioPlayback();
      resetConversation(true);
      speakWelcomeGreeting();
    },
    startCall: function () {
      if (!isCallModeActive) toggleCallMode();
    },
    endCall: function () {
      if (isCallModeActive) endCallMode();
    },
    isCallActive: function () {
      return isCallModeActive;
    },
    removeTawkTo: function () {
      removeTawkTo(true);
    },
    hideTawkTo: function () {
      removeTawkTo(false);
    },
    showTawkTo: function () {
      loadAndOpenTawkTo();
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
    close: function () {
      chatWin.classList.remove("open");
    },
  };
})();
