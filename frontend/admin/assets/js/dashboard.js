/**
 * N+ONE AI Copilot — Admin Dashboard logic
 * Vanilla JS, no build step (consistent with the chat widget). Token kept in
 * sessionStorage only (cleared when the tab closes) — an admin console
 * shouldn't persist credentials across browser restarts on a shared machine.
 */
(function () {
  "use strict";

  const state = {
    apiBase: "http://localhost:8000",
    token: sessionStorage.getItem("npo_admin_token") || null,
    username: sessionStorage.getItem("npo_admin_user") || "admin",
  };

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  // ---------------- Auth ----------------
  async function login(username, password, apiBase) {
    const res = await fetch(`${apiBase}/api/v1/admin/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) throw new Error("invalid credentials");
    const data = await res.json();
    return data.access_token;
  }

  async function apiGet(path) {
    const res = await fetch(`${state.apiBase}${path}`, {
      headers: { Authorization: `Bearer ${state.token}` },
    });
    if (res.status === 401) {
      logout();
      throw new Error("session expired");
    }
    if (!res.ok) throw new Error(`request failed: ${path}`);
    return res.json();
  }

  async function apiPost(path) {
    const res = await fetch(`${state.apiBase}${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${state.token}` },
    });
    if (!res.ok) throw new Error(`request failed: ${path}`);
    return res.json();
  }

  function logout() {
    sessionStorage.removeItem("npo_admin_token");
    sessionStorage.removeItem("npo_admin_user");
    state.token = null;
    $("#app").classList.remove("npo-show");
    $("#loginScreen").style.display = "flex";
  }

  // ---------------- Rendering ----------------
  function renderStats(stats) {
    const cards = [
      { label: "Conversations totales", value: stats.total_conversations, sub: "depuis le lancement" },
      { label: "Messages échangés", value: stats.total_messages, sub: "utilisateur + assistant" },
      { label: "Temps de réponse moyen", value: `${Math.round(stats.avg_response_time_ms)} ms`, sub: "génération incluse" },
      { label: "Documents indexés", value: stats.knowledge_documents, sub: `${stats.vectorstore_chunks} chunks vectorisés` },
    ];
    $("#statsGrid").innerHTML = cards
      .map(
        (c) => `
        <div class="npo-stat-card">
          <div class="npo-stat-label">${c.label}</div>
          <div class="npo-stat-value">${c.value}</div>
          <div class="npo-stat-sub">${c.sub}</div>
        </div>`
      )
      .join("");

    $("#providerLabel").textContent = stats.active_llm_provider.toUpperCase();

    // Top questions bar list
    const maxCount = Math.max(1, ...stats.top_questions.map((q) => q.count));
    $("#topQuestions").innerHTML = stats.top_questions.length
      ? stats.top_questions
          .map(
            (q) => `
          <div class="npo-bar-row">
            <div class="npo-bar-label" title="${escapeHtml(q.question)}">${escapeHtml(q.question)}</div>
            <div class="npo-bar-track"><div class="npo-bar-fill" style="width:${(q.count / maxCount) * 100}%"></div></div>
            <div class="npo-bar-count">${q.count}</div>
          </div>`
          )
          .join("")
      : `<div class="npo-empty">Aucune question enregistrée pour le moment.</div>`;

    renderDonut(stats.feedback_positive, stats.feedback_negative);
    $("#fbPositive").textContent = stats.feedback_positive;
    $("#fbNegative").textContent = stats.feedback_negative;
  }

  function renderDonut(positive, negative) {
    const total = positive + negative;
    const svg = $("#donutSvg");
    const r = 50, cx = 60, cy = 60, circumference = 2 * Math.PI * r;
    if (total === 0) {
      svg.innerHTML = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="14"/>`;
      return;
    }
    const posFrac = positive / total;
    const posLen = circumference * posFrac;
    svg.innerHTML = `
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#f43f5e" stroke-width="14"
        stroke-dasharray="${circumference}" stroke-dashoffset="0" transform="rotate(-90 ${cx} ${cy})"/>
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#22c55e" stroke-width="14"
        stroke-dasharray="${posLen} ${circumference}" stroke-dashoffset="0" transform="rotate(-90 ${cx} ${cy})"/>
      <text x="${cx}" y="${cy + 5}" text-anchor="middle" fill="#e8edf7" font-size="18" font-family="Fira Code, monospace">
        ${Math.round(posFrac * 100)}%
      </text>`;
  }

  function renderLogs(logs) {
    const tbody = $("#logsTable tbody");
    if (!logs.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="npo-empty">Aucun log disponible.</td></tr>`;
      return;
    }
    tbody.innerHTML = logs
      .map((l) => {
        const ok = l.status_code < 400;
        return `
        <tr>
          <td>${escapeHtml(l.endpoint)}</td>
          <td><span class="npo-badge ${ok ? "npo-badge-ok" : "npo-badge-err"}">${l.status_code}</span></td>
          <td>${l.duration_ms} ms</td>
          <td>${l.error ? escapeHtml(l.error.slice(0, 60)) : "—"}</td>
          <td>${new Date(l.created_at).toLocaleString()}</td>
        </tr>`;
      })
      .join("");
  }

  function renderKb(status) {
    $("#kbStatus").innerHTML = `
      <div class="npo-kb-item">
        <span>Index vectoriel FAISS</span>
        <span class="npo-badge ${status.vectorstore_exists ? "npo-badge-ok" : "npo-badge-err"}">
          ${status.vectorstore_exists ? "Actif" : "Absent"}
        </span>
      </div>`;
    $("#kbDocs").innerHTML = status.documents.length
      ? status.documents
          .map(
            (d) => `
        <div class="npo-kb-item">
          <div>
            <div>${escapeHtml(d.source.split("/").pop())}</div>
            <div class="npo-kb-meta">${d.type.toUpperCase()} · ${d.chunks} chunks · indexé le ${new Date(d.indexed_at).toLocaleDateString()}</div>
          </div>
        </div>`
          )
          .join("")
      : `<div class="npo-empty">Aucun document indexé. Lancez ingestion/ingest.py.</div>`;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ---------------- Data loading ----------------
  async function loadAll() {
    try {
      const [stats, kb] = await Promise.all([
        apiGet("/api/v1/admin/stats"),
        apiGet("/api/v1/admin/knowledge-base/status"),
      ]);
      renderStats(stats);
      renderKb(kb);
      const logs = await apiGet("/api/v1/admin/logs?limit=100");
      renderLogs(logs);
    } catch (err) {
      console.error(err);
    }
  }

  // ---------------- Navigation ----------------
  const VIEW_META = {
    overview: ["Vue d'ensemble", "Statistiques et santé du copilote IA"],
    logs: ["Logs", "Journal des requêtes traitées par l'API"],
    kb: ["Base de connaissances", "État de l'index vectoriel et des documents sources"],
  };

  function switchView(view) {
    $$(".npo-nav button").forEach((b) => b.classList.toggle("npo-active", b.dataset.view === view));
    $$(".npo-view").forEach((v) => v.classList.toggle("npo-active", v.id === `view-${view}`));
    $("#viewTitle").textContent = VIEW_META[view][0];
    $("#viewSubtitle").textContent = VIEW_META[view][1];
  }

  // ---------------- Init ----------------
  document.addEventListener("DOMContentLoaded", () => {
    if (state.token) {
      state.apiBase = sessionStorage.getItem("npo_admin_api_base") || state.apiBase;
      showApp();
    }

    $("#loginForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const username = $("#username").value.trim();
      const password = $("#password").value;
      const apiBase = $("#apiBase").value.trim().replace(/\/$/, "");
      const btn = $("#loginBtn");
      btn.disabled = true;
      btn.textContent = "Connexion...";
      $("#loginError").classList.remove("npo-show");

      try {
        const token = await login(username, password, apiBase);
        state.token = token;
        state.apiBase = apiBase;
        state.username = username;
        sessionStorage.setItem("npo_admin_token", token);
        sessionStorage.setItem("npo_admin_user", username);
        sessionStorage.setItem("npo_admin_api_base", apiBase);
        showApp();
      } catch (err) {
        $("#loginError").classList.add("npo-show");
      } finally {
        btn.disabled = false;
        btn.textContent = "Se connecter";
      }
    });

    $("#logoutBtn").addEventListener("click", logout);

    $$(".npo-nav button").forEach((btn) => {
      btn.addEventListener("click", () => switchView(btn.dataset.view));
    });

    $("#reloadKbBtn").addEventListener("click", async () => {
      const btn = $("#reloadKbBtn");
      btn.disabled = true;
      btn.textContent = "Rechargement...";
      try {
        await apiPost("/api/v1/admin/knowledge-base/reload");
        await loadAll();
        btn.textContent = "✅ Rechargé";
      } catch (_) {
        btn.textContent = "❌ Échec";
      } finally {
        setTimeout(() => {
          btn.disabled = false;
          btn.textContent = "🔄 Recharger l'index";
        }, 1500);
      }
    });
  });

  function showApp() {
    $("#loginScreen").style.display = "none";
    $("#app").classList.add("npo-show");
    $("#currentUser").textContent = state.username;
    loadAll();
    // Light polling so the console stays "live" without a manual refresh.
    setInterval(loadAll, 30000);
  }
})();
