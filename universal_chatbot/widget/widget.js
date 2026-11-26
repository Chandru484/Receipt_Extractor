(function () {
  "use strict";

  // Find host script tag and extract parameters (supports website-id, project-id, role, user-id)
  const currentScript = document.currentScript || document.querySelector("script[data-website-id], script[data-project-id]");
  const websiteId = currentScript ? (currentScript.getAttribute("data-project-id") || currentScript.getAttribute("data-website-id") || "site_demo") : "site_demo";
  let candidateRole = (currentScript ? (currentScript.getAttribute("data-role") || "user") : "user").toLowerCase();
  let candidateId = currentScript ? (currentScript.getAttribute("data-user-id") || currentScript.getAttribute("data-candidate-id")) : null;
  const apiBase = currentScript ? (new URL(currentScript.src)).origin : window.location.origin;

  let activeLang = "ta";
  let activeSessionId = null;
  try { activeSessionId = localStorage.getItem("chat_session_id"); } catch (_) {}
  if (!activeSessionId) {
    activeSessionId = "sess_" + Math.random().toString(36).substring(2, 10);
    try { localStorage.setItem("chat_session_id", activeSessionId); } catch (_) {}
  }
  let activeConvId = null;
  try { activeConvId = localStorage.getItem("chat_active_conv_id"); } catch (_) {}
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
    .msg-group { display: flex; flex-direction: column; max-width: 84%; position: relative; }
    .msg-group.user { align-self: flex-end; align-items: flex-end; }
    .msg-group.bot { align-self: flex-start; align-items: flex-start; }
    .msg-group.system-note { align-self: center; align-items: center; max-width: 90%; }
    .msg { width: 100%; padding: 10px 14px; border-radius: 14px; font-size: 13.5px; line-height: 1.45; word-wrap: break-word; box-sizing: border-box; position: relative; transition: opacity 0.2s ease, transform 0.2s ease; }
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
    
    /* Sleek Action Toolbar for Edit, Delete, Copy */
    .msg-toolbar { display: flex; align-items: center; gap: 4px; margin-top: 3px; opacity: 0; transition: opacity 0.2s ease; font-size: 11px; flex-wrap: wrap; }
    .msg-group:hover .msg-toolbar, .msg-group:focus-within .msg-toolbar, .msg-group.active-toolbar .msg-toolbar { opacity: 1; }
    .msg-tool-btn { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 5px; padding: 2px 6px; font-size: 10.5px; color: #64748b; cursor: pointer; display: inline-flex; align-items: center; gap: 3px; box-shadow: 0 1px 2px rgba(0,0,0,0.03); transition: all 0.15s; }
    .msg-tool-btn:hover { background: #f1f5f9; color: #0f172a; border-color: #cbd5e1; }
    .msg-tool-btn.danger:hover { background: #fee2e2; color: #dc2626; border-color: #fca5a5; }
    
    /* Inline Message Editor */
    .msg-edit-box { width: 100%; background: #ffffff; border: 1.5px solid ${widgetConfig.primary_color}; border-radius: 12px; padding: 8px 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); display: flex; flex-direction: column; gap: 6px; box-sizing: border-box; margin-top: 2px; }
    .msg-edit-textarea { width: 100%; border: none; outline: none; font-family: inherit; font-size: 13.5px; line-height: 1.4; resize: vertical; min-height: 44px; color: #1f2937; background: transparent; box-sizing: border-box; }
    .msg-edit-actions { display: flex; justify-content: flex-end; gap: 6px; }
    .msg-edit-btn { border: none; border-radius: 6px; padding: 4px 10px; font-size: 11px; cursor: pointer; font-weight: 500; transition: opacity 0.15s; }
    .msg-edit-save { background: ${widgetConfig.primary_color}; color: #fff; }
    .msg-edit-save:hover { opacity: 0.9; }
    .msg-edit-cancel { background: #f1f5f9; color: #475569; }
    .msg-edit-cancel:hover { background: #e2e8f0; }
    .edited-badge { font-size: 10px; opacity: 0.75; margin-left: 4px; font-style: italic; }
    .msg-fade-out { opacity: 0 !important; transform: scale(0.95) translateY(-4px) !important; transition: opacity 0.2s ease, transform 0.2s ease !important; }

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

    /* Past Chat History Drawer */
    .history-view {
      position: absolute;
      top: 52px;
      left: 0;
      right: 0;
      bottom: 0;
      background: #ffffff;
      z-index: 30;
      display: flex;
      flex-direction: column;
      animation: slideDown 0.2s ease-out;
    }
    @keyframes slideDown {
      from { opacity: 0; transform: translateY(-8px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .history-header {
      padding: 10px 14px;
      border-bottom: 1px solid #e2e8f0;
      background: #f8fafc;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .history-action-btn {
      background: ${widgetConfig.primary_color};
      color: #fff;
      border: none;
      border-radius: 6px;
      padding: 4px 9px;
      font-size: 11px;
      cursor: pointer;
      font-weight: 500;
      transition: opacity 0.15s;
    }
    .history-action-btn:hover { opacity: 0.9; }
    .history-close-btn {
      background: none;
      border: none;
      font-size: 14px;
      cursor: pointer;
      color: #64748b;
      padding: 3px 7px;
      border-radius: 4px;
    }
    .history-close-btn:hover { background: #e2e8f0; color: #0f172a; }
    .history-list {
      flex: 1;
      overflow-y: auto;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 7px;
      background: #f9fafb;
    }
    .history-item {
      padding: 9px 12px;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      background: #ffffff;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: space-between;
      transition: all 0.15s ease;
      box-shadow: 0 1px 2px rgba(0,0,0,0.02);
    }
    .history-item:hover {
      border-color: ${widgetConfig.primary_color};
      background: #f0f7ff;
      transform: translateX(2px);
    }
    .history-item.active {
      border-color: ${widgetConfig.primary_color};
      background: #eff6ff;
      border-left: 3.5px solid ${widgetConfig.primary_color};
    }
    .history-item-info {
      flex: 1;
      overflow: hidden;
      margin-right: 8px;
    }
    .history-item-title {
      font-size: 12.5px;
      color: #1e293b;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .history-item-meta {
      font-size: 10.5px;
      color: #64748b;
      margin-top: 3px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .history-item-badge {
      background: #e2e8f0;
      color: #475569;
      padding: 1px 5px;
      border-radius: 4px;
      font-size: 9.5px;
      font-weight: 500;
    }
    .history-item-del {
      background: none;
      border: none;
      color: #94a3b8;
      cursor: pointer;
      padding: 4px 6px;
      border-radius: 5px;
      font-size: 12px;
      transition: all 0.15s;
    }
    .history-item-del:hover {
      background: #fee2e2;
      color: #dc2626;
    }
    .history-empty {
      padding: 36px 16px;
      text-align: center;
      color: #64748b;
      font-size: 12.5px;
      line-height: 1.5;
    }
  `;

  const template = `
    <style>${styles}</style>
    <button class="chat-btn" id="toggleBtn" aria-label="Open chat">
      <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>
    </button>
    <div class="chat-window" id="chatWin">
      <div class="chat-header">
        <div>
          <span class="chat-title" id="botHeader">${widgetConfig.bot_name || "AI Assistant"}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 6px;">
          <button class="header-btn" id="callModeBtn" title="Start Hands-Free Voice Call (தொடர் குரல் அழைப்பு)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M20.01 15.38c-1.23 0-2.42-.2-3.53-.56a.977.977 0 00-1.01.24l-1.57 1.97c-2.83-1.44-5.15-3.75-6.59-6.59l1.97-1.57c.28-.28.36-.67.25-1.02A11.36 11.36 0 018.96 4.3c0-.55-.45-1-1-1H4.45c-.55 0-1 .45-1 1 0 9.39 7.61 17 17 17 .55 0 1-.45 1-1v-3.56c0-.55-.45-.96-.44-.96z"/></svg>
            <span id="callModeLabel">Voice Call</span>
          </button>
          <button class="header-btn" id="historyBtn" title="View Past Chat History (முந்தைய உரையாடல்கள்)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
            <span id="historyBtnLabel">History</span>
          </button>
          <button class="header-btn" id="newChatBtn" title="Start New Conversation (புதிய அரட்டை)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
            <span>New Chat</span>
          </button>
        </div>
      </div>
      <div class="history-view" id="historyView" style="display: none;">
        <div class="history-header">
          <div style="display: flex; align-items: center; gap: 6px; font-weight: 600; font-size: 13px; color: #1e293b;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
            <span id="historyTitle">Past Conversations</span>
          </div>
          <div style="display: flex; align-items: center; gap: 6px;">
            <button class="history-action-btn" id="historyNewChatBtn" title="Start fresh conversation">
              + New Chat
            </button>
            <button class="history-close-btn" id="closeHistoryBtn" title="Close history">
              ✕
            </button>
          </div>
        </div>
        <div class="history-list" id="historyList"></div>
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
  const historyBtn = shadow.getElementById("historyBtn");
  const historyView = shadow.getElementById("historyView");
  const historyList = shadow.getElementById("historyList");
  const closeHistoryBtn = shadow.getElementById("closeHistoryBtn");
  const historyNewChatBtn = shadow.getElementById("historyNewChatBtn");
  const historyTitle = shadow.getElementById("historyTitle");
  const callModeBtn = shadow.getElementById("callModeBtn");
  const callModeLabel = shadow.getElementById("callModeLabel");
  const callBanner = shadow.getElementById("callBanner");
  const callBannerText = shadow.getElementById("callBannerText");
  const endCallBtn = shadow.getElementById("endCallBtn");
  try { localStorage.removeItem("chat_voice_engine"); } catch (_) {}
  let isCallModeActive = false;
  let isSpeaking = false;
  let isProcessingMessage = false;

  // Shared Audio, Pipeline, and Speech Engine state (declared upfront to prevent Temporal Dead Zone ReferenceErrors)
  let sharedAudio = new Audio();
  let audioUnlocked = false;
  let currentAudio = null;
  let currentPipelineAudio = null;
  let currentPlayingBtn = null;
  let pipelineActive = false;
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;

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
    try { localStorage.removeItem("chat_active_conv_id"); } catch (_) {}
    welcomeSpoken = false;
    if (filePicker) filePicker.value = "";
    if (clearMessages) {
      msgList.innerHTML = "";
      const greeting = welcomeText || widgetConfig.welcome_message_ta || "வணக்கம்! சொல்லுங்க, உங்களுக்கு நான் எப்படி உதவலாம்?";
      appendMessage("bot", greeting);
    }
  }

  function toggleHistoryView() {
    if (!historyView) return;
    if (historyView.style.display === "flex") {
      closeHistoryView();
    } else {
      openHistoryView();
    }
  }

  function openHistoryView() {
    endCallMode();
    stopCurrentAudio();
    if (!historyView) return;
    historyView.style.display = "flex";
    if (historyList) {
      historyList.innerHTML = `<div class="history-empty">⏳ ${activeLang === "ta" ? "முந்தைய உரையாடல்கள் ஏற்றப்படுகின்றன..." : "Loading past conversations..."}</div>`;
    }

    const q = new URLSearchParams({
      website_id: websiteId,
      session_id: activeSessionId,
    });
    if (candidateId) q.append("user_id", candidateId);

    fetch(`${apiBase}/api/v1/chat/conversations?${q.toString()}`)
      .then(r => r.json())
      .then(data => {
        if (!historyList) return;
        historyList.innerHTML = "";
        const convs = (data && data.conversations) ? data.conversations : [];
        if (convs.length === 0) {
          historyList.innerHTML = `<div class="history-empty">${activeLang === "ta" ? "முந்தைய உரையாடல்கள் எதுவும் இல்லை.<br>நீங்கள் பேசத் தொடங்கும் புதிய உரையாடல்கள் இங்கே சேமிக்கப்படும்." : "No past conversations found yet.<br>New chats you start will appear here."}</div>`;
          return;
        }

        convs.forEach(c => {
          const item = document.createElement("div");
          item.className = "history-item" + (c.conversation_id === activeConvId ? " active" : "");
          item.dataset.convId = c.conversation_id;

          const info = document.createElement("div");
          info.className = "history-item-info";

          const title = document.createElement("div");
          title.className = "history-item-title";
          title.textContent = c.title || (activeLang === "ta" ? "உரையாடல்" : "Conversation");

          const meta = document.createElement("div");
          meta.className = "history-item-meta";
          meta.innerHTML = `
            <span>🕒 ${formatTimestamp(c.updated_at || c.created_at)}</span>
            <span class="history-item-badge">${c.message_count || 0} msgs</span>
            ${c.conversation_id === activeConvId ? `<span style="color:${widgetConfig.primary_color};font-weight:600;">● Active</span>` : ""}
          `;

          info.appendChild(title);
          info.appendChild(meta);
          item.appendChild(info);

          // Delete button
          const delBtn = document.createElement("button");
          delBtn.className = "history-item-del";
          delBtn.innerHTML = `🗑️`;
          delBtn.title = activeLang === "ta" ? "இந்த உரையாடலை நீக்கு" : "Delete this conversation";
          delBtn.onclick = (e) => {
            e.stopPropagation();
            deleteConversationFromHistory(c.conversation_id, item);
          };
          item.appendChild(delBtn);

          // Click to load conversation
          item.onclick = () => {
            loadConversation(c.conversation_id);
          };

          historyList.appendChild(item);
        });
      })
      .catch(() => {
        if (historyList) {
          historyList.innerHTML = `<div class="history-empty" style="color:#ef4444;">${activeLang === "ta" ? "வரலாற்றை ஏற்றுவதில் பிழை ஏற்பட்டது." : "Failed to load chat history."}</div>`;
        }
      });
  }

  function closeHistoryView() {
    if (historyView) historyView.style.display = "none";
  }

  function deleteConversationFromHistory(convId, itemElement) {
    if (!convId) return;
    fetch(`${apiBase}/api/v1/chat/conversations/${convId}`, { method: "DELETE" }).catch(() => {});
    if (itemElement) {
      itemElement.style.opacity = "0";
      itemElement.style.transform = "translateX(10px)";
      setTimeout(() => {
        itemElement.remove();
        if (historyList && historyList.children.length === 0) {
          historyList.innerHTML = `<div class="history-empty">${activeLang === "ta" ? "முந்தைய உரையாடல்கள் எதுவும் இல்லை." : "No past conversations found."}</div>`;
        }
      }, 200);
    }
    if (activeConvId === convId) {
      resetConversation(true);
    }
  }

  function loadConversation(convId) {
    if (!convId) return;
    stopCurrentAudio();
    endCallMode();
    closeHistoryView();

    activeConvId = convId;
    try { localStorage.setItem("chat_active_conv_id", convId); } catch (_) {}

    msgList.innerHTML = `<div class="msg-group system-note"><div class="msg system-note">⏳ ${activeLang === "ta" ? "உரையாடல் ஏற்றப்படுகிறது..." : "Loading conversation..."}</div></div>`;

    fetch(`${apiBase}/api/v1/chat/conversations/${convId}`)
      .then(r => r.json())
      .then(data => {
        msgList.innerHTML = "";
        const msgs = (data && data.messages) ? data.messages : [];
        if (msgs.length === 0) {
          appendMessage("bot", widgetConfig.welcome_message_ta || "வணக்கம்! சொல்லுங்க, உங்களுக்கு நான் எப்படி உதவலாம்?");
          return;
        }

        // Render each interaction
        msgs.forEach(m => {
          if (m.user_message) {
            appendMessage("user", m.user_message, [], null, m.message_id, "pair_" + m.message_id);
          }
          if (m.bot_reply) {
            appendMessage("bot", m.bot_reply, m.citations || [], m.action || null, m.message_id, "pair_" + m.message_id);
          }
        });

        appendMessage(
          "system-note",
          activeLang === "ta"
            ? `📜 முந்தைய உரையாடல் "${data.title || "உரையாடல்"}" திறக்கப்பட்டது (${msgs.length} பதில்கள்). நீங்கள் தொடர்ந்து பேசலாம்!`
            : `📜 Loaded past conversation: "${data.title || "Chat"}" (${msgs.length} replies). You can continue chatting!`
        );
        msgList.scrollTop = msgList.scrollHeight;
      })
      .catch(() => {
        msgList.innerHTML = "";
        appendMessage("system-note", activeLang === "ta" ? "❌ உரையாடலை ஏற்றுவதில் பிழை." : "❌ Failed to load conversation.");
      });
  }

  function formatTimestamp(ts) {
    if (!ts) return "";
    try {
      const d = new Date(ts.replace(" ", "T"));
      if (isNaN(d.getTime())) return ts.substring(0, 16);
      return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" }) + ", " + d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: true });
    } catch (_) {
      return ts.substring(0, 16);
    }
  }

  if (historyBtn) {
    historyBtn.onclick = () => toggleHistoryView();
  }
  if (closeHistoryBtn) {
    closeHistoryBtn.onclick = () => closeHistoryView();
  }
  if (historyNewChatBtn) {
    historyNewChatBtn.onclick = () => {
      closeHistoryView();
      resetConversation(true);
      speakWelcomeGreeting();
    };
  }

  if (newChatBtn) {
    newChatBtn.onclick = () => {
      unlockAudioPlayback();
      closeHistoryView();
      resetConversation(true);
      speakWelcomeGreeting();
    };
  }

  // Fetch website config
  fetch(`${apiBase}/api/v1/chat/widget-config/${websiteId}`)
    .then(r => r.json())
    .then(cfg => {
      Object.assign(widgetConfig, cfg);
      botHeader.textContent = (widgetConfig.bot_name === "Universal Assistant" || !widgetConfig.bot_name) ? "AI Assistant" : widgetConfig.bot_name;
    })
    .catch(() => {});

  // Pre-unlocked HTML5 Audio element for seamless auto-speech without browser autoplay blocks
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

  // Append message to UI with Edit and Delete options
  function appendMessage(role, text, citations = [], action = null, messageId = null, pairId = null) {
    const group = document.createElement("div");
    group.className = `msg-group ${role}`;
    if (messageId) group.dataset.messageId = messageId;
    if (pairId) group.dataset.pairId = pairId;

    const div = document.createElement("div");
    div.className = `msg ${role}`;

    const textSpan = document.createElement("div");
    textSpan.className = "msg-text";

    if (role === "bot") {
      textSpan.innerHTML = formatMarkdown(text);
      div.appendChild(textSpan);

      if (action) {
        const actionBadge = document.createElement("div");
        actionBadge.style.cssText = "margin-top: 6px; padding: 4px 8px; background: #dbeafe; color: #1e40af; border-radius: 6px; font-size: 11.5px; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;";
        actionBadge.innerHTML = `⚡ Website Action: <span>${action.label || action.action_type}</span>`;
        div.appendChild(actionBadge);
      }
    } else {
      textSpan.textContent = text;
      div.appendChild(textSpan);
    }
    group.appendChild(div);

    let createdSpeakBtn = null;
    if (role === "user" || role === "bot") {
      const toolbar = document.createElement("div");
      toolbar.className = "msg-toolbar";

      if (role === "bot") {
        if (widgetConfig.allow_speech_output) {
          const speakBtn = document.createElement("button");
          speakBtn.className = "msg-tool-btn";
          speakBtn.innerHTML = `🔊 Listen`;
          speakBtn.onclick = () => toggleSpeech(text, activeLang, speakBtn);
          toolbar.appendChild(speakBtn);
          createdSpeakBtn = speakBtn;
        }

        if (citations && citations.length > 0) {
          citations.forEach(c => {
            const citTag = document.createElement("span");
            citTag.className = "citation-tag";
            citTag.textContent = `📌 ${c.title || "Source"}`;
            citTag.title = c.snippet || "";
            toolbar.appendChild(citTag);
          });
        }
      }

      // Copy Button
      const copyBtn = document.createElement("button");
      copyBtn.className = "msg-tool-btn";
      copyBtn.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg> Copy`;
      copyBtn.title = activeLang === "ta" ? "நகலெடு" : "Copy text";
      copyBtn.onclick = () => {
        try {
          navigator.clipboard.writeText(text);
          copyBtn.innerHTML = `✓ Copied`;
          setTimeout(() => {
            copyBtn.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg> Copy`;
          }, 1500);
        } catch (_) {}
      };
      toolbar.appendChild(copyBtn);

      // Edit Button (Available for User messages)
      if (role === "user") {
        const editBtn = document.createElement("button");
        editBtn.className = "msg-tool-btn";
        editBtn.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg> Edit`;
        editBtn.title = activeLang === "ta" ? "செய்தியைத் திருத்து" : "Edit message";
        editBtn.onclick = () => openInlineEdit(group, div, textSpan);
        toolbar.appendChild(editBtn);
      }

      // Delete Button (Available for both User and Bot messages)
      const deleteBtn = document.createElement("button");
      deleteBtn.className = "msg-tool-btn danger";
      deleteBtn.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg> Delete`;
      deleteBtn.title = activeLang === "ta" ? "செய்தியை நீக்கு" : "Delete message";
      deleteBtn.onclick = () => deleteMessageElement(group);
      toolbar.appendChild(deleteBtn);

      group.appendChild(toolbar);
    }

    msgList.appendChild(group);
    msgList.scrollTop = msgList.scrollHeight;
    return { group, element: div, textSpan, speakBtn: createdSpeakBtn };
  }

  // Open inline editor for a user message
  function openInlineEdit(group, msgBubble, textSpan) {
    if (group.querySelector(".msg-edit-box")) return;

    const currentText = textSpan.textContent.replace(/\s*\(edited\)$/, "");
    msgBubble.style.display = "none";
    const toolbar = group.querySelector(".msg-toolbar");
    if (toolbar) toolbar.style.display = "none";

    const editBox = document.createElement("div");
    editBox.className = "msg-edit-box";

    const textarea = document.createElement("textarea");
    textarea.className = "msg-edit-textarea";
    textarea.value = currentText;
    textarea.placeholder = activeLang === "ta" ? "உங்கள் செய்தியைத் திருத்துங்கள்..." : "Edit your message...";

    const actions = document.createElement("div");
    actions.className = "msg-edit-actions";

    const cancelBtn = document.createElement("button");
    cancelBtn.className = "msg-edit-btn msg-edit-cancel";
    cancelBtn.textContent = activeLang === "ta" ? "ரத்து (Cancel)" : "Cancel";
    cancelBtn.onclick = () => {
      editBox.remove();
      msgBubble.style.display = "block";
      if (toolbar) toolbar.style.display = "flex";
    };

    const saveBtn = document.createElement("button");
    saveBtn.className = "msg-edit-btn msg-edit-save";
    saveBtn.textContent = activeLang === "ta" ? "மாற்றி அனுப்பு (Save & Send)" : "Save & Send";
    saveBtn.onclick = () => {
      const newText = textarea.value.trim();
      if (!newText) return;
      if (newText === currentText) {
        editBox.remove();
        msgBubble.style.display = "block";
        if (toolbar) toolbar.style.display = "flex";
        return;
      }

      // Update text in UI
      textSpan.textContent = newText;
      let badge = msgBubble.querySelector(".edited-badge");
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "edited-badge";
        badge.textContent = "(edited)";
        msgBubble.appendChild(badge);
      }
      editBox.remove();
      msgBubble.style.display = "block";
      if (toolbar) toolbar.style.display = "flex";

      const oldMsgId = group.dataset.messageId;
      const pairId = group.dataset.pairId;

      // Remove the previous bot response that answered this old question
      if (pairId) {
        const pairedBotMsg = msgList.querySelector(`.msg-group.bot[data-pair-id="${pairId}"]`);
        if (pairedBotMsg) {
          deleteMessageElement(pairedBotMsg, false);
        }
      }

      // Delete old message record in MongoDB
      if (oldMsgId) {
        fetch(`${apiBase}/api/v1/chat/messages/${oldMsgId}`, {
          method: "DELETE",
        }).catch(() => {});
      }

      // Generate a new fresh pairId for the updated interaction
      const newPairId = "pair_" + Date.now();
      group.dataset.pairId = newPairId;
      delete group.dataset.messageId;

      // Send the edited prompt to chatbot backend
      sendMessageWithText(newText, false, newPairId, group);
    };

    textarea.onkeydown = (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        saveBtn.click();
      } else if (e.key === "Escape") {
        cancelBtn.click();
      }
    };

    actions.appendChild(cancelBtn);
    actions.appendChild(saveBtn);
    editBox.appendChild(textarea);
    editBox.appendChild(actions);

    group.insertBefore(editBox, msgBubble);
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);
  }

  // Delete message element from UI and backend database
  function deleteMessageElement(group, notifyBackend = true) {
    const msgId = group.dataset.messageId;
    const pairId = group.dataset.pairId;
    const isUser = group.classList.contains("user");

    // Stop audio immediately if speaking
    stopCurrentAudio();

    group.classList.add("msg-fade-out");

    setTimeout(() => {
      group.remove();

      // If user deletes their question, also remove the paired bot response
      if (isUser && pairId) {
        const pairedBot = msgList.querySelector(`.msg-group.bot[data-pair-id="${pairId}"]`);
        if (pairedBot) {
          pairedBot.classList.add("msg-fade-out");
          setTimeout(() => pairedBot.remove(), 200);
        }
      }

      // Delete from backend MongoDB
      if (notifyBackend && msgId) {
        fetch(`${apiBase}/api/v1/chat/messages/${msgId}`, {
          method: "DELETE",
        }).catch(() => {});
      }
    }, 200);
  }


  // High-Definition Neural Speech & Audio Controls (Sentence-Level Pipelined)
  function stopCurrentAudio() {
    pipelineActive = false;
    if (currentPipelineAudio) {
      try {
        currentPipelineAudio.pause();
        currentPipelineAudio.currentTime = 0;
      } catch (_) {}
      currentPipelineAudio = null;
    }
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

  function splitIntoSentences(text) {
    if (!text) return [];
    // Split on sentence boundaries (. ? ! newline or comma in long clauses)
    const raw = text.split(/(?<=[.?!।\n])\s+/);
    return raw.map(s => s.trim()).filter(s => s.length > 1);
  }

  function sanitizeTamilTextForSpeech(text) {
    if (!text) return "";
    let cleaned = text
      .replace(/[\u00A0\u1680\u2000-\u200B\u202F\u205F\u3000]/g, " ")
      .replace(/[*#_`|]/g, " ")
      .replace(/https?:\/\/\S+/g, "")
      .replace(/(?:உங்களுக்கு\s*)?(?:வேற|வேறு)\s*(?:ஏதாச்சும்|ஏதாவது|எதாவது)\s*உதவி\s*(?:வேண்டுமா|வேணுமா|தேவையா)[?.]?/gi, "")
      .replace(/\bபார்க்கி\s*சொல்லுறேன்\b/gi, "பார்த்துச் சொல்றேன்")
      .replace(/\bபார்க்கி\b/gi, "பார்த்து")
      .replace(/\bசொல்லுறேன்\b/gi, "சொல்றேன்")
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
      .replace(/\bசேமிக்கப்பட்டுள்ளனங்க\b/g, "சேமிக்கப்பட்டிருக்கு")
      .replace(/\bகிடைக்கின்றனங்க\b/g, "கிடைக்குது")
      .replace(/\bகிடைக்கிறதுங்க\b/g, "கிடைக்குது")
      .replace(/\bஎடுக்கப்பட்டுள்ளனங்க\b/g, "எடுக்கப்பட்டிருக்கு")
      .replace(/\bஇருக்கின்றனங்க\b/g, "இருக்கு")
      .replace(/\bஉள்ளனங்க\b/g, "இருக்கு")
      .replace(/\bவருகின்றனங்க\b/g, "வருது")
      .replace(/\bகாட்டப்பட்டுள்ளனங்க\b/g, "காட்டப்பட்டிருக்கு")
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
      .replace(/\bTekis\b/gi, "டெக்கிஸ்")
      .replace(/\bAI\b/g, "ஏ.ஐ")
      .replace(/\bPDF\b/g, "பி.டி.எஃப்")
      .replace(/\bG\s*Pay\b/gi, "ஜி பே")
      .replace(/[-\u2010-\u2015\u2212]\s*(\d{6})\b/g, " பின்கோடு $1")
      .replace(/\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1})\b/g, (m) => m.split("").join(" "))
      // Numeric dates to Tamil month speech: e.g. 15/11/2024 or 2024-11-15 -> 15 நவம்பர் 2024
      .replace(/\b([0-3]?\d)[-/](0[1-9]|1[0-2])[-/](20\d\d|19\d\d)\b/g, (m, d, mo, y) => {
        const moMap = {"01":"ஜனவரி","1":"ஜனவரி","02":"பிப்ரவரி","2":"பிப்ரவரி","03":"மார்ச்","3":"மார்ச்","04":"ஏப்ரல்","4":"ஏப்ரல்","05":"மே","5":"மே","06":"ஜூன்","6":"ஜூன்","07":"ஜூலை","7":"ஜூலை","08":"ஆகஸ்ட்","8":"ஆகஸ்ட்","09":"செப்டம்பர்","9":"செப்டம்பர்","10":"அக்டோபர்","11":"நவம்பர்","12":"டிசம்பர்"};
        return `${d} ${moMap[mo] || mo} ${y}`;
      })
      .replace(/\b(20\d\d|19\d\d)[-/](0[1-9]|1[0-2])[-/]([0-3]?\d)\b/g, (m, y, mo, d) => {
        const moMap = {"01":"ஜனவரி","1":"ஜனவரி","02":"பிப்ரவரி","2":"பிப்ரவரி","03":"மார்ச்","3":"மார்ச்","04":"ஏப்ரல்","4":"ஏப்ரல்","05":"மே","5":"மே","06":"ஜூன்","6":"ஜூன்","07":"ஜூலை","7":"ஜூலை","08":"ஆகஸ்ட்","8":"ஆகஸ்ட்","09":"செப்டம்பர்","9":"செப்டம்பர்","10":"அக்டோபர்","11":"நவம்பர்","12":"டிசம்பர்"};
        return `${d} ${moMap[mo] || mo} ${y}`;
      })
      // Attached colloquial Tamil locative & dative suffixes: e.g. November-ல, Nov-ல -> நவம்பர்ல
      .replace(/\bJan(?:uary)?[- ]?(?:ல|ல்|இல்)\b/gi, "ஜனவரில")
      .replace(/\bFeb(?:ruary)?[- ]?(?:ல|ல்|இல்)\b/gi, "பிப்ரவரில")
      .replace(/\bMar(?:ch)?[- ]?(?:ல|ல்|இல்)\b/gi, "மார்ச்ல")
      .replace(/\bApr(?:il)?[- ]?(?:ல|ல்|இல்)\b/gi, "ஏப்ரல்ல")
      .replace(/\bMay[- ]?(?:ல|ல்|இல்)\b/gi, "மே மாசத்துல")
      .replace(/\bJun(?:e)?[- ]?(?:ல|ல்|இல்)\b/gi, "ஜூன்ல")
      .replace(/\bJul(?:y)?[- ]?(?:ல|ல்|இல்)\b/gi, "ஜூலைல")
      .replace(/\bAug(?:ust)?[- ]?(?:ல|ல்|இல்)\b/gi, "ஆகஸ்ட்ல")
      .replace(/\bSep(?:t(?:ember)?)?[- ]?(?:ல|ல்|இல்)\b/gi, "செப்டம்பர்ல")
      .replace(/\bOct(?:ober)?[- ]?(?:ல|ல்|இல்)\b/gi, "அக்டோபர்ல")
      .replace(/\bNov(?:ember)?[- ]?(?:ல|ல்|இல்)\b/gi, "நவம்பர்ல")
      .replace(/\bDec(?:ember)?[- ]?(?:ல|ல்|இல்)\b/gi, "டிசம்பர்ல")
      .replace(/\bJan(?:uary)?[- ]?க்கு\b/gi, "ஜனவரிக்கு")
      .replace(/\bFeb(?:ruary)?[- ]?க்கு\b/gi, "பிப்ரவரிக்கு")
      .replace(/\bMar(?:ch)?[- ]?க்கு\b/gi, "மார்ச்சுக்கு")
      .replace(/\bApr(?:il)?[- ]?க்கு\b/gi, "ஏப்ரலுக்கு")
      .replace(/\bMay[- ]?க்கு\b/gi, "மே மாதத்துக்கு")
      .replace(/\bJun(?:e)?[- ]?க்கு\b/gi, "ஜூனுக்கு")
      .replace(/\bJul(?:y)?[- ]?க்கு\b/gi, "ஜூலைக்கு")
      .replace(/\bAug(?:ust)?[- ]?க்கு\b/gi, "ஆகஸ்ட்டுக்கு")
      .replace(/\bSep(?:t(?:ember)?)?[- ]?க்கு\b/gi, "செப்டம்பருக்கு")
      .replace(/\bOct(?:ober)?[- ]?க்கு\b/gi, "அக்டோபருக்கு")
      .replace(/\bNov(?:ember)?[- ]?க்கு\b/gi, "நவம்பருக்கு")
      .replace(/\bDec(?:ember)?[- ]?க்கு\b/gi, "டிசம்பருக்கு")
      // Dates with day + month + year: e.g. 15-Nov-2024, 15/Nov/2024, 15 Nov 2024
      .replace(/\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Jan(?:uary)?[-\s/]+(\d{2,4})\b/gi, "$1 ஜனவரி $2")
      .replace(/\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Feb(?:ruary)?[-\s/]+(\d{2,4})\b/gi, "$1 பிப்ரவரி $2")
      .replace(/\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Mar(?:ch)?[-\s/]+(\d{2,4})\b/gi, "$1 மார்ச் $2")
      .replace(/\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Apr(?:il)?[-\s/]+(\d{2,4})\b/gi, "$1 ஏப்ரல் $2")
      .replace(/\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+May[-\s/]+(\d{2,4})\b/gi, "$1 மே $2")
      .replace(/\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Jun(?:e)?[-\s/]+(\d{2,4})\b/gi, "$1 ஜூன் $2")
      .replace(/\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Jul(?:y)?[-\s/]+(\d{2,4})\b/gi, "$1 ஜூலை $2")
      .replace(/\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Aug(?:ust)?[-\s/]+(\d{2,4})\b/gi, "$1 ஆகஸ்ட் $2")
      .replace(/\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Sep(?:t(?:ember)?)?[-\s/]+(\d{2,4})\b/gi, "$1 செப்டம்பர் $2")
      .replace(/\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Oct(?:ober)?[-\s/]+(\d{2,4})\b/gi, "$1 அக்டோபர் $2")
      .replace(/\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Nov(?:ember)?[-\s/]+(\d{2,4})\b/gi, "$1 நவம்பர் $2")
      .replace(/\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Dec(?:ember)?[-\s/]+(\d{2,4})\b/gi, "$1 டிசம்பர் $2")
      // Month + Day format: e.g. Nov 15 or November 15
      .replace(/\bJan(?:uary)?\s+(\d{1,2})(?:st|nd|rd|th)?\b/gi, "$1 ஜனவரி")
      .replace(/\bFeb(?:ruary)?\s+(\d{1,2})(?:st|nd|rd|th)?\b/gi, "$1 பிப்ரவரி")
      .replace(/\bMar(?:ch)?\s+(\d{1,2})(?:st|nd|rd|th)?\b/gi, "$1 மார்ச்")
      .replace(/\bApr(?:il)?\s+(\d{1,2})(?:st|nd|rd|th)?\b/gi, "$1 ஏப்ரல்")
      .replace(/\bMay\s+(\d{1,2})(?:st|nd|rd|th)?\b/gi, "$1 மே")
      .replace(/\bJun(?:e)?\s+(\d{1,2})(?:st|nd|rd|th)?\b/gi, "$1 ஜூன்")
      .replace(/\bJul(?:y)?\s+(\d{1,2})(?:st|nd|rd|th)?\b/gi, "$1 ஜூலை")
      .replace(/\bAug(?:ust)?\s+(\d{1,2})(?:st|nd|rd|th)?\b/gi, "$1 ஆகஸ்ட்")
      .replace(/\bSep(?:t(?:ember)?)?\s+(\d{1,2})(?:st|nd|rd|th)?\b/gi, "$1 செப்டம்பர்")
      .replace(/\bOct(?:ober)?\s+(\d{1,2})(?:st|nd|rd|th)?\b/gi, "$1 அக்டோபர்")
      .replace(/\bNov(?:ember)?\s+(\d{1,2})(?:st|nd|rd|th)?\b/gi, "$1 நவம்பர்")
      .replace(/\bDec(?:ember)?\s+(\d{1,2})(?:st|nd|rd|th)?\b/gi, "$1 டிசம்பர்")
      // Standalone full month names and abbreviations
      .replace(/\bJan(?:uary)?\.?\b/gi, "ஜனவரி")
      .replace(/\bFeb(?:ruary)?\.?\b/gi, "பிப்ரவரி")
      .replace(/\bMar(?:ch)?\.?\b/gi, "மார்ச்")
      .replace(/\bApr(?:il)?\.?\b/gi, "ஏப்ரல்")
      .replace(/\bMay\.?\b/gi, "மே")
      .replace(/\bJun(?:e)?\.?\b/gi, "ஜூன்")
      .replace(/\bJul(?:y)?\.?\b/gi, "ஜூலை")
      .replace(/\bAug(?:ust)?\.?\b/gi, "ஆகஸ்ட்")
      .replace(/\bSep(?:t(?:ember)?)?\.?\b/gi, "செப்டம்பர்")
      .replace(/\bOct(?:ober)?\.?\b/gi, "அக்டோபர்")
      .replace(/\bNov(?:ember)?\.?\b/gi, "நவம்பர்")
      .replace(/\bDec(?:ember)?\.?\b/gi, "டிசம்பர்")
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

    // High-Definition Neural Speech with Sentence-Level Pipelining
    const sentences = splitIntoSentences(cleanText);
    if (sentences.length === 0) return;

    if (btn) {
      btn.innerHTML = '<span class="mini-waveform"><span class="mbar"></span><span class="mbar"></span><span class="mbar"></span></span> ⏹️ Stop';
      btn.classList.add("playing");
      currentPlayingBtn = btn;
    }

    pipelineActive = true;
    let nextPreloadedAudio = null;

    function playSentenceIndex(index) {
      if (!pipelineActive || index >= sentences.length) {
        pipelineActive = false;
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
        return;
      }

      const sText = sentences[index];
      const sUrl = `${apiBase}/api/v1/voice/tts?text=${encodeURIComponent(sText)}&language=${targetLang}`;
      
      const audioObj = nextPreloadedAudio || new Audio(sUrl);
      nextPreloadedAudio = null;
      currentPipelineAudio = audioObj;
      currentAudio = audioObj;

      // Pipeline pre-fetch: start buffering the NEXT sentence in the background while current is speaking!
      if (index + 1 < sentences.length) {
        const nextUrl = `${apiBase}/api/v1/voice/tts?text=${encodeURIComponent(sentences[index + 1])}&language=${targetLang}`;
        nextPreloadedAudio = new Audio(nextUrl);
        nextPreloadedAudio.preload = "auto";
      }

      let watchdogTimer = setTimeout(() => {
        if (!isSpeaking) {
          console.warn("HD Cloud voice buffering, switching to instant voice to avoid delay");
          playBrowserSpeech(cleanText, targetLang, btn, onEndedCallback);
        }
      }, 380);

      audioObj.onplay = () => {
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

      audioObj.onended = () => {
        clearTimeout(watchdogTimer);
        playSentenceIndex(index + 1);
      };

      audioObj.onerror = (err) => {
        clearTimeout(watchdogTimer);
        console.warn("Sentence pipeline error, falling back to instant speech:", err);
        playBrowserSpeech(cleanText, targetLang, btn, onEndedCallback);
      };

      audioObj.play().catch(playErr => {
        clearTimeout(watchdogTimer);
        console.warn("Audio play blocked, using browser fallback:", playErr);
        playBrowserSpeech(cleanText, targetLang, btn, onEndedCallback);
      });
    }

    playSentenceIndex(0);
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
    try { if (window.speechSynthesis.paused) window.speechSynthesis.resume(); } catch (_) {}
    const cleanText = sanitizeTamilTextForSpeech(text);
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = lang === "ta" ? "ta-IN" : "en-IN";
    utterance.rate = 1.15;

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
    userInput.value = "";
    sendMessageWithText(text, isVoice);
  }

  function sendMessageWithText(text, isVoice = false, existingPairId = null, existingUserGroup = null) {
    unlockAudioPlayback();
    isProcessingMessage = true;
    if (isCallModeActive) {
      if (callBanner) {
        callBanner.classList.remove("speaking", "listening");
        callBanner.classList.add("thinking");
      }
      if (callBannerText) callBannerText.textContent = "⏳ சிந்திக்கிறது... (Thinking...)";
    }

    const pairId = existingPairId || ("pair_" + Date.now() + "_" + Math.random().toString(36).substring(2, 7));

    let userGroup = existingUserGroup;
    if (!userGroup) {
      const userRes = appendMessage("user", text, [], null, null, pairId);
      userGroup = userRes ? userRes.group : null;
    } else {
      userGroup.dataset.pairId = pairId;
    }

    const loadingGroup = document.createElement("div");
    loadingGroup.className = "msg-group bot";
    loadingGroup.dataset.pairId = pairId;
    const loadingDiv = document.createElement("div");
    loadingDiv.className = "msg bot";
    loadingDiv.textContent = activeLang === "ta" ? "சிந்திக்கிறது..." : "Thinking...";
    loadingGroup.appendChild(loadingDiv);
    msgList.appendChild(loadingGroup);
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
        loadingGroup.remove();
        activeConvId = data.conversation_id;
        try { localStorage.setItem("chat_active_conv_id", activeConvId); } catch (_) {}


        // Attach message_id to user message group for future delete/edit
        if (userGroup && data.message_id) {
          userGroup.dataset.messageId = data.message_id;
        }

        const msgRes = appendMessage("bot", data.reply, data.citations, data.action, data.message_id, pairId);

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
        loadingGroup.remove();
        appendMessage("bot", activeLang === "ta" ? "சேவையகப் பிழை ஏற்பட்டது. மீண்டும் முயற்சிக்கவும்." : "Server error. Please try again.");
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
  function startListening() {
    if (!recognition) return;
    if (micBtn.classList.contains("recording")) return;
    stopCurrentAudio();

    // Pre-warm Edge-TTS connection and backend caches on mic open for zero latency
    try {
      fetch(`${apiBase}/api/v1/voice/warmup`, { method: "POST" }).catch(() => {});
    } catch (_) {}

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
  }

  // Tawk.to human agent handoff button
  humanAgentBtn.onclick = () => {
    loadAndOpenTawkTo(widgetConfig.tawk_to_property_id, widgetConfig.tawk_to_widget_id);
    userInput.value = activeLang === "ta" ? "வாடிக்கையாளர் சேவை முகவரிடம் பேச வேண்டும்" : "I want to talk to human support";
    sendMessage();
  };

  // Load existing conversation or render initial welcome message (after all UI & audio handlers are ready)
  if (activeConvId) {
    loadConversation(activeConvId);
  } else {
    appendMessage("bot", widgetConfig.welcome_message_ta || "வணக்கம்! சொல்லுங்க, உங்களுக்கு நான் எப்படி உதவலாம்?");
  }

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
