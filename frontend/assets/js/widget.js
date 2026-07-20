/**
 * N+ONE AI Copilot — Chat Widget
 * -------------------------------
 * Zero-dependency vanilla JS widget, embeddable on the N+ONE website with a
 * single <script src="widget.js" data-api-base="https://api.nplusone.africa"></script>.
 *
 * Design decision: vanilla JS (no React/build step) so the marketing site
 * (WordPress) can embed it by simply dropping two <script>/<link> tags,
 * without a frontend build pipeline.
 */
(function () {
  "use strict";

  const scriptTag = document.currentScript;
  const API_BASE = scriptTag?.dataset?.apiBase || "http://localhost:8000";
  const STORAGE_KEY = "npo_session_id";
  const THEME_KEY = "npo_theme";

  const I18N = {
    en: {
      title: "N+ONE Assistant",
      subtitle: "Ask about our services, datacenters & more",
      placeholder: "Type your question...",
      greeting:
        "Hi! I'm the N+ONE DATACENTERS assistant. Ask me about our colocation, hyperscale, business continuity, certifications, locations, or careers.",
      clear: "Clear conversation",
      footer: "Answers are based on official N+ONE content and may be incomplete.",
      helpful: "Helpful",
      notHelpful: "Not helpful",
    },
    fr: {
      title: "Assistant N+ONE",
      subtitle: "Posez vos questions sur nos services et datacenters",
      placeholder: "Écrivez votre question...",
      greeting:
        "Bonjour ! Je suis l'assistant N+ONE DATACENTERS. Posez-moi vos questions sur la colocation, l'hyperscale, la continuité d'activité, les certifications, les sites ou les carrières.",
      clear: "Effacer la conversation",
      footer: "Les réponses se basent sur le contenu officiel N+ONE et peuvent être incomplètes.",
      helpful: "Utile",
      notHelpful: "Pas utile",
    },
    ar: {
      title: "مساعد N+ONE",
      subtitle: "اسألنا عن خدماتنا ومراكز البيانات",
      placeholder: "اكتب سؤالك...",
      greeting:
        "مرحباً! أنا مساعد N+ONE DATACENTERS. اسألني عن خدمات الاستضافة المشتركة، الهايبرسكيل، استمرارية الأعمال، الشهادات، المواقع، أو التوظيف.",
      clear: "مسح المحادثة",
      footer: "الإجابات مبنية على المحتوى الرسمي لـ N+ONE وقد تكون غير مكتملة.",
      helpful: "مفيد",
      notHelpful: "غير مفيد",
    },
  };

  function getSessionId() {
    let id = localStorage.getItem(STORAGE_KEY);
    if (!id) {
      id = "sess_" + crypto.randomUUID();
      localStorage.setItem(STORAGE_KEY, id);
    }
    return id;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  /** Minimal Markdown -> HTML (bold, italics, code, lists, links). Avoids a full MD dependency. */
  function renderMarkdown(text) {
    let html = escapeHtml(text);
    html = html.replace(/```([\s\S]*?)```/g, (_, code) =>
      `<pre><button class="npo-copy-btn" onclick="navigator.clipboard.writeText(this.nextSibling.textContent)">Copy</button><code>${code.trim()}</code></pre>`
    );
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
    html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
    html = html.replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>");
    html = html.replace(/\n{2,}/g, "</p><p>");
    html = html.replace(/\n/g, "<br/>");
    return `<p>${html}</p>`;
  }

  class NpOneWidget {
    constructor() {
      this.sessionId = getSessionId();
      this.language = document.documentElement.lang?.slice(0, 2) || "en";
      if (!I18N[this.language]) this.language = "en";
      this.theme = localStorage.getItem(THEME_KEY) || "dark";
      this.isOpen = false;
      this.isSending = false;

      this._buildDom();
      this._bindEvents();
      this._renderGreeting();
    }

    t(key) {
      return I18N[this.language][key];
    }

    _buildDom() {
      this.root = document.createElement("div");
      this.root.className = "npo-widget-root";
      this.root.setAttribute("data-theme", this.theme);

      this.root.innerHTML = `
        <button class="npo-fab" aria-label="Open chat">
          <span class="npo-fab-badge"></span>
          <svg viewBox="0 0 24 24"><path d="M12 3C6.48 3 2 6.94 2 12c0 2.3.94 4.4 2.5 6L2 22l4.3-1.36C8 21.5 9.94 22 12 22c5.52 0 10-3.94 10-9s-4.48-10-10-10z"/></svg>
        </button>
        <div class="npo-panel" role="dialog" aria-label="N+ONE Assistant">
          <div class="npo-header">
            <span class="npo-logo-dot"></span>
            <div>
              <h3>${this.t("title")}</h3>
              <p>${this.t("subtitle")}</p>
            </div>
            <div class="npo-header-actions">
              <select class="npo-lang-select" title="Language">
                <option value="en">EN</option>
                <option value="fr">FR</option>
                <option value="ar">AR</option>
              </select>
              <button class="npo-icon-btn npo-theme-toggle" title="Toggle theme">
                <svg viewBox="0 0 24 24"><path d="M12 3a9 9 0 100 18 9 9 0 000-18zm0 16a7 7 0 010-14v14z"/></svg>
              </button>
              <button class="npo-icon-btn npo-clear-btn" title="${this.t("clear")}">
                <svg viewBox="0 0 24 24"><path d="M6 7h12v2H6zm2 3h8l-1 9H9zM9 4h6l1 2H8z"/></svg>
              </button>
              <button class="npo-icon-btn npo-close-btn" title="Close">
                <svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" fill="none"/></svg>
              </button>
            </div>
          </div>
          <div class="npo-messages"></div>
          <div class="npo-input-area">
            <textarea rows="1" placeholder="${this.t("placeholder")}"></textarea>
            <button class="npo-send-btn" aria-label="Send">
              <svg viewBox="0 0 24 24"><path d="M2 21l21-9L2 3v7l15 2-15 2z"/></svg>
            </button>
          </div>
          <div class="npo-footer-note">${this.t("footer")}</div>
        </div>
      `;
      document.body.appendChild(this.root);

      this.fab = this.root.querySelector(".npo-fab");
      this.panel = this.root.querySelector(".npo-panel");
      this.messagesEl = this.root.querySelector(".npo-messages");
      this.textarea = this.root.querySelector("textarea");
      this.sendBtn = this.root.querySelector(".npo-send-btn");
      this.langSelect = this.root.querySelector(".npo-lang-select");
      this.langSelect.value = this.language;
    }

    _bindEvents() {
      this.fab.addEventListener("click", () => this.toggle());
      this.root.querySelector(".npo-close-btn").addEventListener("click", () => this.toggle(false));
      this.root.querySelector(".npo-theme-toggle").addEventListener("click", () => this.toggleTheme());
      this.root.querySelector(".npo-clear-btn").addEventListener("click", () => this.clearConversation());
      this.sendBtn.addEventListener("click", () => this.send());
      this.textarea.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          this.send();
        }
      });
      this.textarea.addEventListener("input", () => {
        this.textarea.style.height = "auto";
        this.textarea.style.height = Math.min(this.textarea.scrollHeight, 90) + "px";
      });
      this.langSelect.addEventListener("change", (e) => {
        this.language = e.target.value;
        this._rebuildStaticTexts();
      });
    }

    _rebuildStaticTexts() {
      this.root.querySelector(".npo-header h3").textContent = this.t("title");
      this.root.querySelector(".npo-header p").textContent = this.t("subtitle");
      this.textarea.placeholder = this.t("placeholder");
      this.root.querySelector(".npo-footer-note").textContent = this.t("footer");
    }

    toggleTheme() {
      this.theme = this.theme === "dark" ? "light" : "dark";
      this.root.setAttribute("data-theme", this.theme);
      localStorage.setItem(THEME_KEY, this.theme);
    }

    toggle(force) {
      this.isOpen = force ?? !this.isOpen;
      this.panel.classList.toggle("npo-open", this.isOpen);
      if (this.isOpen) this.textarea.focus();
    }

    _renderGreeting() {
      this._appendMessage("assistant", this.t("greeting"), []);
    }

    _appendMessage(role, text, sources = [], messageId = null) {
      const wrapper = document.createElement("div");
      wrapper.className = `npo-msg npo-${role === "user" ? "user" : "assistant"}`;

      const avatar = document.createElement("div");
      avatar.className = "npo-avatar";
      avatar.textContent = role === "user" ? "U" : "N1";

      const bubble = document.createElement("div");
      bubble.className = "npo-bubble";
      bubble.innerHTML = renderMarkdown(text);

      if (sources.length) {
        const srcWrap = document.createElement("div");
        srcWrap.className = "npo-sources";
        sources.forEach((s) => {
          const a = document.createElement("a");
          a.className = "npo-source-chip";
          a.href = s.url || "#";
          a.target = "_blank";
          a.rel = "noopener";
          a.textContent = `📄 ${s.title}`;
          srcWrap.appendChild(a);
        });
        bubble.appendChild(srcWrap);
      }

      if (role === "assistant" && messageId) {
        const fb = document.createElement("div");
        fb.className = "npo-feedback";
        fb.innerHTML = `
          <button data-v="up">👍 ${this.t("helpful")}</button>
          <button data-v="down">👎 ${this.t("notHelpful")}</button>
        `;
        fb.querySelectorAll("button").forEach((btn) => {
          btn.addEventListener("click", () => {
            fb.querySelectorAll("button").forEach((b) => b.classList.remove("npo-active"));
            btn.classList.add("npo-active");
            this._sendFeedback(messageId, btn.dataset.v === "up");
          });
        });
        bubble.appendChild(fb);
      }

      wrapper.appendChild(avatar);
      wrapper.appendChild(bubble);
      this.messagesEl.appendChild(wrapper);
      this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
      return wrapper;
    }

    _showTyping() {
      const el = document.createElement("div");
      el.className = "npo-msg npo-assistant npo-typing-wrapper";
      el.innerHTML = `<div class="npo-avatar">N1</div><div class="npo-bubble npo-typing"><span></span><span></span><span></span></div>`;
      this.messagesEl.appendChild(el);
      this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
      return el;
    }

    async send() {
      const text = this.textarea.value.trim();
      if (!text || this.isSending) return;

      this.isSending = true;
      this.sendBtn.disabled = true;
      this._appendMessage("user", text);
      this.textarea.value = "";
      this.textarea.style.height = "auto";

      const typingEl = this._showTyping();

      try {
        const res = await fetch(`${API_BASE}/api/v1/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: text,
            session_id: this.sessionId,
            language: this.language,
          }),
        });
        const data = await res.json();
        typingEl.remove();

        if (!res.ok) {
          this._appendMessage("assistant", data.detail || "Something went wrong. Please try again.");
        } else {
          this._appendMessage("assistant", data.answer, data.sources, data.message_id);
        }
      } catch (err) {
        typingEl.remove();
        this._appendMessage(
          "assistant",
          "I couldn't reach the server. Please check your connection and try again."
        );
      } finally {
        this.isSending = false;
        this.sendBtn.disabled = false;
      }
    }

    async _sendFeedback(messageId, isHelpful) {
      try {
        await fetch(`${API_BASE}/api/v1/chat/feedback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message_id: messageId, is_helpful: isHelpful }),
        });
      } catch (_) {
        /* non-critical, fail silently */
      }
    }

    async clearConversation() {
      try {
        await fetch(`${API_BASE}/api/v1/chat/clear`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: this.sessionId }),
        });
      } catch (_) {
        /* non-critical */
      }
      localStorage.removeItem(STORAGE_KEY);
      this.sessionId = getSessionId();
      this.messagesEl.innerHTML = "";
      this._renderGreeting();
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    window.npoWidget = new NpOneWidget();
  });
})();
