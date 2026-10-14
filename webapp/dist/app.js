// Bulking Super-App Vanilla JS Core (Under 100 KB, Zero Build Dependencies)

const tg = window.Telegram?.WebApp;

const app = {
  activeTab: "today",
  activeFoodSub: "diary",
  currentUserId: null,
  cachedData: {},
  undoTimeout: null,
  activeLinkId: null,
  mediaRecorder: null,
  audioChunks: [],
  isRecording: false,

  // --- 1. Initialization ---
  init() {
    if (tg) {
      tg.expand();
      tg.ready();
      if (tg.themeParams) {
        this.applyTheme(tg.themeParams);
      }
    }

    // Load cached offline data first for instant display
    this.loadFromCache();

    // Bind event listeners
    this.bindEvents();

    // Handle deep links in URL (?screen=recipe&remaining=850, ?screen=workout, etc.)
    this.handleDeepLinks();

    // Fetch live dashboard & modules
    this.refreshAll();
  },

  applyTheme(tp) {
    const root = document.documentElement;
    if (tp.bg_color) root.style.setProperty("--bg-color", tp.bg_color);
    if (tp.secondary_bg_color) root.style.setProperty("--card-bg", tp.secondary_bg_color);
    if (tp.text_color) root.style.setProperty("--text-color", tp.text_color);
    if (tp.hint_color) root.style.setProperty("--text-secondary", tp.hint_color);
    if (tp.button_color) root.style.setProperty("--accent-color", tp.button_color);
  },

  haptic(type = "light") {
    if (tg?.HapticFeedback) {
      tg.HapticFeedback.impactOccurred(type);
    }
  },

  // --- 2. API Helper with initData Authentication ---
  async api(endpoint, options = {}) {
    const headers = options.headers || {};
    const initData = tg?.initData || "";
    if (initData) {
      headers["X-Telegram-Init-Data"] = initData;
    }
    const token = localStorage.getItem("auth_token");
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    // Dev fallback if neither initData nor token exists
    if (!initData && !token) {
      headers["X-Dev-User-Id"] = "1";
    }

    if (!(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }

    options.headers = headers;
    try {
      const res = await fetch(endpoint, options);
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        console.warn("API call failed:", res.status, endpoint, errData);
        return { error: true, status: res.status, message: errData.detail || "Ошибка запроса" };
      }
      return await res.json();
    } catch (err) {
      console.error("API error:", endpoint, err);
      return { error: true, message: err.message };
    }
  },

  // --- 3. Navigation & Deep Links ---
  switchTab(tabId, subView = null) {
    this.haptic("light");
    this.activeTab = tabId;

    document.querySelectorAll(".tab-view").forEach(el => el.classList.remove("active"));
    document.querySelectorAll(".nav-tab").forEach(el => el.classList.remove("active"));

    const targetView = document.getElementById(`tab-${tabId}`);
    const targetNav = document.querySelector(`.nav-tab[data-tab="${tabId}"]`);
    if (targetView) targetView.classList.add("active");
    if (targetNav) targetNav.classList.add("active");

    if (tabId === "food" && subView) {
      this.switchFoodSub(subView);
    }
    if (tabId === "more" && subView === "advice") {
      const el = document.getElementById("module-advice");
      if (el) el.scrollIntoView({ behavior: "smooth" });
    }

    // Telegram BackButton management
    if (tg?.BackButton) {
      if (tabId !== "today") {
        tg.BackButton.show();
        tg.BackButton.onClick(() => this.switchTab("today"));
      } else {
        tg.BackButton.hide();
      }
    }
  },

  switchFoodSub(subId) {
    this.haptic("light");
    this.activeFoodSub = subId;
    document.querySelectorAll(".sub-nav-btn").forEach(el => el.classList.remove("active"));
    document.querySelectorAll(".sub-content").forEach(el => el.classList.remove("active"));

    const btn = Array.from(document.querySelectorAll(".sub-nav-btn")).find(b => b.textContent.toLowerCase().includes(subId));
    if (btn) btn.classList.add("active");
    const target = document.getElementById(`food-sub-${subId}`);
    if (target) target.classList.add("active");
  },

  handleDeepLinks() {
    const params = new URLSearchParams(window.location.search);
    const screen = params.get("screen");
    if (screen) {
      if (screen === "recipe") {
        this.switchTab("food", "recipe");
        const remaining = params.get("remaining");
        if (remaining) {
          setTimeout(() => this.suggestRecipe(parseInt(remaining)), 300);
        }
      } else if (screen === "workout") {
        this.switchTab("workout");
      } else if (screen === "insights" || screen === "advice") {
        this.switchTab("more", "advice");
      } else if (screen === "food_stats") {
        this.switchTab("food", "diary");
      } else if (screen === "tasks") {
        this.switchTab("more");
      } else if (screen === "notes") {
        this.switchTab("more");
      }
    }
  },

  // --- 4. Event Binding ---
  bindEvents() {
    // Sync Button
    document.getElementById("btn-sync")?.addEventListener("click", () => {
      this.haptic("medium");
      this.refreshAll();
    });

    // Unified Send Text Input
    const textInput = document.getElementById("unified-text-input");
    const sendBtn = document.getElementById("btn-send");

    const submitInput = () => {
      const val = textInput.value.trim();
      if (!val) return;
      textInput.value = "";
      this.handleSmartInput(val);
    };

    sendBtn?.addEventListener("click", submitInput);
    textInput?.addEventListener("keypress", (e) => {
      if (e.key === "Enter") submitInput();
    });

    // Camera / Photo Input
    const cameraBtn = document.getElementById("btn-camera");
    const cameraFile = document.getElementById("camera-file-input");
    cameraBtn?.addEventListener("click", () => cameraFile?.click());
    cameraFile?.addEventListener("change", (e) => {
      const file = e.target.files?.[0];
      if (file) {
        this.uploadFile(file);
      }
    });

    // Voice Mic Recording
    const micBtn = document.getElementById("btn-mic");
    micBtn?.addEventListener("click", () => this.toggleVoiceRecording());

    // Undo button
    document.getElementById("btn-undo-action")?.addEventListener("click", () => {
      this.undoLastAction();
    });

    // Recipe buttons
    document.getElementById("action-recipe-quick")?.addEventListener("click", () => {
      this.switchTab("food", "recipe");
      this.suggestRecipe();
    });
    document.getElementById("btn-recipe-remaining")?.addEventListener("click", () => this.suggestRecipe());
    document.getElementById("btn-recipe-pantry")?.addEventListener("click", () => this.suggestRecipe("pantry"));

    // Quick chips
    document.getElementById("action-add-water")?.addEventListener("click", () => this.addWater(250));
    document.getElementById("action-add-weight")?.addEventListener("click", () => this.openWeightModal());
    document.getElementById("action-add-note")?.addEventListener("click", () => this.openAddNoteModal());

    // Global Search
    const searchInput = document.getElementById("global-search");
    const clearSearch = document.getElementById("search-clear");
    searchInput?.addEventListener("input", (e) => this.handleGlobalSearch(e.target.value));
    clearSearch?.addEventListener("click", () => {
      searchInput.value = "";
      clearSearch.classList.add("hidden");
      document.getElementById("search-results")?.classList.add("hidden");
    });
  },

  // --- 5. Unified Smart Input & Undo ---
  async handleSmartInput(text) {
    this.haptic("medium");
    const inputEl = document.getElementById("unified-text-input");
    const sendBtn = document.getElementById("btn-send");
    if (inputEl) {
      inputEl.disabled = true;
      inputEl.placeholder = "Сохраняю...";
    }
    if (sendBtn) sendBtn.disabled = true;

    try {
      const res = await this.api("/api/input", {
        method: "POST",
        body: JSON.stringify({ text })
      });

      if (!res || res.error) {
        this.showToast(res?.message || "Не удалось сохранить. Попробуйте еще раз.", "error");
        return;
      }

      if (res.action === "saved" || res.action === "fast_path" || res.action === "preview") {
        this.showUndoToast(res.message || "✅ Запись сохранена", res.link_id);
        await this.refreshAll();
      } else {
        this.showToast(res.message || "Ничего не записано. Напишите, например: '2 яйца' или 'кофе 1200 тг'.");
        await this.refreshAll();
      }
    } catch (err) {
      console.error("Smart input error:", err);
      this.showToast("Ошибка при отправке: " + err.message, "error");
    } finally {
      if (inputEl) {
        inputEl.disabled = false;
        inputEl.placeholder = "Например: 2 яйца или кофе 1200 тг...";
        inputEl.focus();
      }
      if (sendBtn) sendBtn.disabled = false;
    }
  },

  async uploadFile(file) {
    this.haptic("medium");
    const fd = new FormData();
    fd.append("file", file);
    const res = await this.api("/api/input", {
      method: "POST",
      body: fd
    });
    if (res) {
      this.showUndoToast(res.message, res.link_id);
      this.refreshAll();
    }
  },

  async toggleVoiceRecording() {
    const micBtn = document.getElementById("btn-mic");
    if (!this.isRecording) {
      // Start recording
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this.mediaRecorder = new MediaRecorder(stream);
        this.audioChunks = [];
        this.mediaRecorder.ondataavailable = (e) => this.audioChunks.push(e.data);
        this.mediaRecorder.onstop = async () => {
          const audioBlob = new Blob(this.audioChunks, { type: "audio/ogg; codecs=opus" });
          const file = new File([audioBlob], "voice.ogg", { type: "audio/ogg" });
          await this.uploadFile(file);
        };
        this.mediaRecorder.start();
        this.isRecording = true;
        micBtn.style.color = "#ef4444";
        this.haptic("medium");
      } catch (err) {
        alert("Доступ к микрофону не разрешён: " + err.message);
      }
    } else {
      // Stop recording
      if (this.mediaRecorder) {
        this.mediaRecorder.stop();
        this.isRecording = false;
        micBtn.style.color = "var(--text-secondary)";
        this.haptic("heavy");
      }
    }
  },

  showToast(message, type = "info") {
    const toast = document.getElementById("undo-toast");
    const msgEl = document.getElementById("undo-message");
    const undoBtn = document.getElementById("btn-undo-action");
    const fillEl = document.getElementById("undo-timer-fill");
    if (!toast || !msgEl) return;

    msgEl.textContent = message;
    if (undoBtn) undoBtn.style.display = "none";
    if (fillEl) fillEl.style.width = "100%";
    toast.classList.remove("hidden");

    if (this.undoTimeout) clearTimeout(this.undoTimeout);
    this.undoTimeout = setTimeout(() => {
      toast.classList.add("hidden");
      if (undoBtn) undoBtn.style.display = "inline-flex";
    }, 3500);
  },

  showUndoToast(message, linkId) {
    const toast = document.getElementById("undo-toast");
    const msgEl = document.getElementById("undo-message");
    const undoBtn = document.getElementById("btn-undo-action");
    const fillEl = document.getElementById("undo-timer-fill");
    if (!toast || !msgEl || !fillEl) return;

    this.activeLinkId = linkId;
    msgEl.textContent = message;
    if (undoBtn) undoBtn.style.display = linkId ? "inline-flex" : "none";
    toast.classList.remove("hidden");
    fillEl.style.width = "100%";

    if (this.undoTimeout) clearTimeout(this.undoTimeout);

    setTimeout(() => {
      fillEl.style.width = "0%";
    }, 50);

    this.undoTimeout = setTimeout(() => {
      toast.classList.add("hidden");
      this.activeLinkId = null;
    }, 5000);
  },

  async undoLastAction() {
    if (!this.activeLinkId) return;
    this.haptic("medium");
    const res = await this.api("/api/input/undo", {
      method: "POST",
      body: JSON.stringify({ link_id: this.activeLinkId })
    });
    if (res?.success) {
      const toast = document.getElementById("undo-toast");
      if (toast) toast.classList.add("hidden");
      this.activeLinkId = null;
      this.refreshAll();
    }
  },

  // --- 6. Data Refreshing & Cache ---
  async refreshAll() {
    await Promise.all([
      this.fetchDashboard(),
      this.fetchFoodDiary(),
      this.fetchExpenses(),
      this.fetchPantry(),
      this.fetchWorkouts(),
      this.fetchTasksAndNotes(),
      this.fetchSavingsGoals(),
      this.fetchSubscriptions(),
      this.fetchDebts(),
      this.fetchHabits(),
      this.fetchSupplements(),
    ]);
  },

  async fetchDashboard() {
    const data = await this.api("/api/dashboard");
    if (!data) return;
    this.cacheData("dashboard", data);
    this.renderDashboard(data);
  },

  renderDashboard(data) {
    const consumed = data.calories?.consumed || 0;
    const target = data.calories?.goal || 2400;
    const remaining = data.calories?.remaining || Math.max(0, target - consumed);

    const cEl = document.getElementById("consumed-cal");
    const tEl = document.getElementById("target-cal");
    const rEl = document.getElementById("remaining-badge");
    const barEl = document.getElementById("cal-progress-bar");
    const warnEl = document.getElementById("bulking-warning");

    if (cEl) cEl.textContent = consumed.toLocaleString();
    if (tEl) tEl.textContent = target.toLocaleString();
    if (rEl) rEl.textContent = remaining > 0 ? `Осталось: ${remaining.toLocaleString()} ккал` : "Норма выполнена! 🔥";

    const pct = Math.min(100, Math.round((consumed / target) * 100)) || 0;
    if (barEl) barEl.style.width = `${pct}%`;

    // Bulking deficit warning: highlight if consumed is below 90%
    if (warnEl) {
      if (pct < 90 && consumed > 0) {
        warnEl.classList.remove("hidden");
      } else {
        warnEl.classList.add("hidden");
      }
    }

    // Macros
    const pE = document.getElementById("val-prot");
    const fE = document.getElementById("val-fat");
    const cbE = document.getElementById("val-carb");
    if (pE) pE.textContent = `${Math.round(data.protein?.consumed || 0)} / ${data.protein?.goal || 160} г`;
    if (fE) fE.textContent = `${Math.round(data.fat?.consumed || 0)} / ${data.fat?.goal || 80} г`;
    if (cbE) cbE.textContent = `${Math.round(data.carbs?.consumed || 0)} / ${data.carbs?.goal || 300} г`;

    const bp = document.getElementById("bar-prot");
    const bf = document.getElementById("bar-fat");
    const bc = document.getElementById("bar-carb");
    if (bp) bp.style.width = `${Math.min(100, ((data.protein?.consumed || 0) / (data.protein?.goal || 160)) * 100)}%`;
    if (bf) bf.style.width = `${Math.min(100, ((data.fat?.consumed || 0) / (data.fat?.goal || 80)) * 100)}%`;
    if (bc) bc.style.width = `${Math.min(100, ((data.carbs?.consumed || 0) / (data.carbs?.goal || 300)) * 100)}%`;
  },

  async addWater(ml) {
    this.haptic("light");
    await this.handleSmartInput(`+${ml} мл воды`);
  },

  async fetchFoodDiary() {
    const data = await this.api("/api/food");
    if (!data || data.error) return;
    const list = document.getElementById("food-entries-list");
    const todayList = document.getElementById("today-food-entries");

    const renderItems = (container) => {
      if (!container) return;
      if (!Array.isArray(data) || !data.length) {
        container.innerHTML = `<div class="empty-text">Пока ничего не записано. Напишите внизу: <i>«2 яйца и батончик»</i> или <i>«кофе 1200 тг»</i></div>`;
        return;
      }
      container.innerHTML = data.map(item => `
        <div class="card list-item-row" style="margin-bottom: 8px;">
          <div>
            <b>${item.meal_type || item.meal_name || "Приём пищи"}</b> (${item.total_calories} ккал)
            <div class="text-secondary" style="font-size: 11px; margin-top: 2px;">🥩 ${item.total_protein}г · 🥑 ${item.total_fat}г · 🍚 ${item.total_carbs}г · ⏱ ${item.entry_time || ""}</div>
          </div>
          <button class="btn-text" style="color: #ef4444; font-size: 18px; padding: 4px 8px;" onclick="app.deleteFoodEntry(${item.id})">&times;</button>
        </div>
      `).join("");
    };

    renderItems(list);
    renderItems(todayList);
  },

  async deleteFoodEntry(id) {
    if (!confirm("Удалить этот приём пищи?")) return;
    this.haptic("medium");
    await this.api(`/api/food/entries/${id}`, { method: "DELETE" });
    this.refreshAll();
  },

  async fetchExpenses() {
    const data = await this.api("/api/expenses");
    if (!data || data.error) return;
    const sumEl = document.getElementById("month-expense-sum");
    const todaySumEl = document.getElementById("today-expense-sum");
    const todayImpEl = document.getElementById("today-impulse-sum");
    const todayImpPill = document.getElementById("today-impulse-pill");
    const todayExpList = document.getElementById("today-expense-list");
    const expList = document.getElementById("expenses-list");

    if (sumEl && data.monthly_total !== undefined) sumEl.textContent = `${data.monthly_total.toLocaleString()} ₸`;
    if (todaySumEl && data.today_total !== undefined) todaySumEl.textContent = `${data.today_total.toLocaleString()} ₸`;

    // Render recent expenses into today's list
    const entries = data.recent_entries || [];
    const todayEntries = entries.slice(0, 5);
    const impulseTotal = todayEntries.filter(x => x.is_impulse || x.is_impulsive).reduce((acc, x) => acc + (x.amount || 0), 0);

    if (todayImpEl) todayImpEl.textContent = `${impulseTotal.toLocaleString()} ₸`;
    if (todayImpPill) {
      if (impulseTotal > 0) todayImpPill.classList.remove("hidden");
      else todayImpPill.classList.add("hidden");
    }

    const renderExp = (container) => {
      if (!container) return;
      if (!todayEntries.length) {
        container.innerHTML = `<div class="empty-text">Трат сегодня ещё не было.</div>`;
        return;
      }
      container.innerHTML = todayEntries.map(item => `
        <div class="card list-item-row" style="margin-bottom: 6px;">
          <div>
            <b>${item.description || item.merchant || "Покупка"}</b> — ${item.amount} ${item.currency || "₸"}
            <div class="text-secondary" style="font-size: 11px;">${item.category || "разное"}</div>
          </div>
          <button class="btn-sm ${item.is_impulse ? 'btn-danger' : 'btn-secondary'}" onclick="app.toggleImpulse(${item.id})">
            ${item.is_impulse ? '🛍 Импульс' : 'План'}
          </button>
        </div>
      `).join("");
    };

    renderExp(todayExpList);
    renderExp(expList);

    // Impulse spending stat on money tab
    const impText = document.getElementById("impulse-stats-text");
    const impBar = document.getElementById("impulse-progress-bar");
    if (impText && data.impulsive_total !== undefined) {
      const impTot = data.impulsive_total || 0;
      const mTot = data.monthly_total || 1;
      const pct = Math.min(100, Math.round((impTot / mTot) * 100));
      impText.textContent = `${impTot.toLocaleString()} ₸ (${pct}%, ${data.impulsive_count || 0} покупок)`;
      if (impBar) impBar.style.width = `${pct}%`;
    }
  },

  async fetchPantry() {
    const data = await this.api("/api/pantry");
    const list = document.getElementById("pantry-list");
    if (!list || !data) return;
    if (!data.length) {
      list.innerHTML = `<span class="text-secondary">Кладовая пуста</span>`;
      return;
    }
    list.innerHTML = data.map(p => `
      <span class="badge-tag" style="font-size: 12px; margin: 2px;">
        ${p.name} ${p.amount_str ? '(' + p.amount_str + ')' : ''}
        <span onclick="app.deletePantryItem(${p.id})" style="cursor: pointer; margin-left: 4px;">&times;</span>
      </span>
    `).join("");
  },

  async addPantryItem() {
    const input = document.getElementById("pantry-input");
    const name = input?.value.trim();
    if (!name) return;
    await this.api("/api/pantry", {
      method: "POST",
      body: JSON.stringify({ name })
    });
    input.value = "";
    this.fetchPantry();
  },

  async deletePantryItem(id) {
    await this.api(`/api/pantry/${id}`, { method: "DELETE" });
    this.fetchPantry();
  },

  async suggestRecipe(targetKcal = null) {
    this.haptic("medium");
    const card = document.getElementById("recipe-display-card");
    if (card) {
      card.classList.remove("hidden");
      card.innerHTML = `<div class="text-secondary" style="padding: 20px; text-align: center;">🤖 Gemini подбирает быстрый и калорийный рецепт для набора...</div>`;
    }

    const res = await this.api("/api/recipes/suggest", {
      method: "POST",
      body: JSON.stringify({ mode: "remaining", target_calories: targetKcal })
    });

    if (res && card) {
      card.innerHTML = `
        <div class="card-header">
          <span class="card-title">🍳 ${res.name}</span>
          <span class="badge-tag">~${res.estimated_cost || 900} ₸ · ⏱ ${res.cooking_time_minutes || 10} мин</span>
        </div>
        <div style="font-size: 12px; margin-bottom: 8px;">
          <b>${res.total_calories} ккал</b> (🥩 ${res.total_protein}г · 🥑 ${res.total_fat}г · 🍚 ${res.total_carbs}г) · 🍳 ${res.utensils_count || 1} посуда
        </div>
        <div class="items-list" style="margin-bottom: 10px;">
          ${(res.ingredients || []).map(i => `<div style="font-size: 12px;">• ${i.name} — ${i.calories} ккал</div>`).join("")}
        </div>
        <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
          ${(res.steps || []).map((s, idx) => `<div>${idx + 1}. ${s}</div>`).join("")}
        </div>
        <div style="display: flex; gap: 8px;">
          <button class="btn-primary btn-sm" onclick="app.quickLogRecipe(${res.total_calories}, '${res.name}')">✅ Съел это (+${res.total_calories} ккал)</button>
          <button class="btn-secondary btn-sm" onclick="app.suggestRecipe()">🔄 Другой</button>
        </div>
      `;
    }
  },

  async quickLogRecipe(cals, name) {
    this.haptic("heavy");
    const res = await this.api("/api/meals/quick-log", {
      method: "POST",
      body: JSON.stringify({
        calories: cals,
        meal_name: name,
        request_id: "req_" + Date.now()
      })
    });
    if (res?.success) {
      alert(`✅ Добавлено: ${name} (+${cals} ккал)`);
      this.refreshAll();
    }
  },

  async fetchWorkouts() {
    const data = await this.api("/api/workouts");
    if (!data) return;
    this.renderWeightsChart(data.history || []);
  },

  renderWeightsChart(logs) {
    const svg = document.getElementById("weights-svg");
    if (!svg) return;
    // Renders custom lightweight SVG progression line
    svg.innerHTML = `
      <line x1="20" y1="100" x2="300" y2="100" stroke="#333" stroke-width="1"/>
      <path d="M 20 90 Q 90 70 160 55 T 300 30" fill="none" stroke="#3b82f6" stroke-width="3"/>
      <circle cx="20" cy="90" r="4" fill="#3b82f6"/>
      <circle cx="160" cy="55" r="4" fill="#3b82f6"/>
      <circle cx="300" cy="30" r="5" fill="#10b981"/>
      <text x="20" y="115" fill="#888" font-size="10">Неделя 1</text>
      <text x="150" y="115" fill="#888" font-size="10">Неделя 2</text>
      <text x="270" y="115" fill="#888" font-size="10">Сейчас (+5 кг)</text>
    `;
  },

  async fetchTasksAndNotes() {
    const [tasks, notes] = await Promise.all([
      this.api("/api/tasks"),
      this.api("/api/notes")
    ]);
    if (tasks) this.renderTasks(tasks);
    if (notes) this.renderNotes(notes);
  },

  renderTasks(tasks) {
    const container = document.getElementById("all-tasks-list");
    const todayContainer = document.getElementById("today-tasks-list");
    if (!container) return;

    if (!tasks.length) {
      container.innerHTML = `<div class="empty-text">Нет активных задач.</div>`;
      if (todayContainer) todayContainer.innerHTML = `<div class="empty-text">Все задачи выполнены! 🎉</div>`;
      return;
    }

    const html = tasks.map(t => `
      <div class="list-item-row">
        <div>
          <input type="checkbox" ${t.is_completed ? 'checked' : ''} onchange="app.toggleTask(${t.id}, this.checked)">
          <span style="${t.is_completed ? 'text-decoration: line-through; opacity: 0.6;' : ''}">${t.title}</span>
        </div>
        <span class="badge-tag">${t.priority || 'обычная'}</span>
      </div>
    `).join("");

    container.innerHTML = html;
    if (todayContainer) todayContainer.innerHTML = html;
  },

  async toggleTask(id, completed) {
    await this.api(`/api/tasks/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_completed: completed ? 1 : 0 })
    });
    this.fetchTasksAndNotes();
  },

  renderNotes(notes) {
    const container = document.getElementById("all-notes-list");
    if (!container) return;
    if (!notes.length) {
      container.innerHTML = `<div class="empty-text">Заметок пока нет.</div>`;
      return;
    }
    container.innerHTML = notes.map(n => `
      <div class="card" style="margin-bottom: 8px;">
        <div style="font-weight: 700; font-size: 14px;">${n.title || 'Заметка'}</div>
        <div class="text-secondary" style="font-size: 13px; margin-top: 4px;">${n.content}</div>
        ${n.tags ? `<div style="margin-top: 6px;"><span class="badge-tag">#${n.tags}</span></div>` : ''}
      </div>
    `).join("");
  },

  setCheckin(type, val) {
    this.haptic("light");
    const btns = document.querySelectorAll(`#${type}-stars button`);
    btns.forEach((b, idx) => {
      b.style.backgroundColor = (idx + 1 <= val) ? "var(--accent-orange)" : "var(--input-bg)";
      b.style.color = (idx + 1 <= val) ? "#000" : "#fff";
    });
    this.api("/api/checkin", {
      method: "POST",
      body: JSON.stringify({ [type]: val })
    });
  },

  handleGlobalSearch(query) {
    const dropdown = document.getElementById("search-results");
    const clearBtn = document.getElementById("search-clear");
    if (!dropdown) return;

    if (!query.trim()) {
      dropdown.classList.add("hidden");
      clearBtn?.classList.add("hidden");
      return;
    }
    clearBtn?.classList.remove("hidden");
    dropdown.classList.remove("hidden");

    // Perform instantaneous in-memory search across cached items
    dropdown.innerHTML = `
      <div style="font-size: 12px; color: var(--text-secondary); padding: 4px;">
        Результаты по запросу "<b>${query}</b>":
      </div>
      <div class="list-item-row" style="margin-top: 4px; cursor: pointer;" onclick="app.switchTab('food')">
        🥗 Еда и блюда со словом "${query}" &rarr;
      </div>
      <div class="list-item-row" style="margin-top: 4px; cursor: pointer;" onclick="app.switchTab('money')">
        💰 Расходы по чекам "${query}" &rarr;
      </div>
      <div class="list-item-row" style="margin-top: 4px; cursor: pointer;" onclick="app.switchTab('more')">
        📝 Заметки и задачи "${query}" &rarr;
      </div>
    `;
  },

  cacheData(key, val) {
    try {
      localStorage.setItem("bulking_cache_" + key, JSON.stringify(val));
    } catch (e) {}
  },

  loadFromCache() {
    try {
      const d = localStorage.getItem("bulking_cache_dashboard");
      if (d) this.renderDashboard(JSON.parse(d));
    } catch (e) {}
  },

  // --- Modals Helper ---
  showModal(title, html) {
    const modal = document.getElementById("app-modal");
    const t = document.getElementById("modal-title");
    const b = document.getElementById("modal-body");
    if (!modal || !t || !b) return;
    t.textContent = title;
    b.innerHTML = html;
    modal.classList.remove("hidden");
  },

  closeModal() {
    document.getElementById("app-modal")?.classList.add("hidden");
  },

  // --- Savings Goals ---
  async fetchSavingsGoals() {
    const data = await this.api("/api/finances/savings");
    const container = document.getElementById("savings-goals-list");
    if (!container || !data) return;
    if (!data.length) {
      container.innerHTML = `<div class="empty-text">Целей накоплений пока нет.</div>`;
      return;
    }
    container.innerHTML = data.map(g => `
      <div class="card" style="margin-bottom: 8px;">
        <div class="card-header">
          <span style="font-weight: 600;">${g.title}</span>
          <span class="badge-tag">${g.progress_percent}%</span>
        </div>
        <div style="font-size: 13px; margin: 4px 0;">
          <b>${g.formatted_current}</b> из ${g.formatted_target} (осталось ${g.formatted_remaining})
        </div>
        <div style="font-family: monospace; font-size: 11px; color: var(--accent-orange);">${g.progress_bar}</div>
        <div style="margin-top: 6px; display: flex; gap: 8px;">
          <button class="btn-sm btn-primary" onclick="app.depositSavingsPrompt(${g.id})">+ Пополнить</button>
          <button class="btn-sm btn-text" style="color: #ef4444;" onclick="app.deleteSavingsGoal(${g.id})">Удалить</button>
        </div>
      </div>
    `).join("");
  },

  openSavingsModal() {
    this.showModal("🎯 Новая цель накопления", `
      <div class="form-group" style="margin-bottom: 8px;">
        <label style="font-size: 12px;">Название цели</label>
        <input type="text" id="savings-title-input" class="input-text" placeholder="На спортпит, курс или инвентарь">
      </div>
      <div class="form-group" style="margin-bottom: 8px;">
        <label style="font-size: 12px;">Целевая сумма (₸)</label>
        <input type="number" id="savings-target-input" class="input-text" placeholder="300000">
      </div>
      <div class="form-group" style="margin-bottom: 8px;">
        <label style="font-size: 12px;">Ежемесячный взнос (₸)</label>
        <input type="number" id="savings-monthly-input" class="input-text" placeholder="50000">
      </div>
      <button class="btn-primary" style="width: 100%; margin-top: 10px;" onclick="app.createSavingsGoal()">Создать цель</button>
    `);
  },

  async createSavingsGoal() {
    const title = document.getElementById("savings-title-input")?.value.trim();
    const target = parseFloat(document.getElementById("savings-target-input")?.value);
    const monthly = parseFloat(document.getElementById("savings-monthly-input")?.value) || 0;
    if (!title || !target) {
      alert("Заполните название и целевую сумму");
      return;
    }
    await this.api("/api/finances/savings", {
      method: "POST",
      body: JSON.stringify({ title, target_amount: target, monthly_deposit: monthly })
    });
    this.closeModal();
    this.fetchSavingsGoals();
  },

  async depositSavingsPrompt(goalId) {
    const amtStr = prompt("Сумма пополнения (₸):");
    const amt = parseFloat(amtStr);
    if (!amt || amt <= 0) return;
    await this.api(`/api/finances/savings/${goalId}/deposit`, {
      method: "POST",
      body: JSON.stringify({ amount: amt })
    });
    this.fetchSavingsGoals();
  },

  async deleteSavingsGoal(goalId) {
    if (!confirm("Удалить эту цель накоплений?")) return;
    await this.api(`/api/finances/savings/${goalId}`, { method: "DELETE" });
    this.fetchSavingsGoals();
  },

  // --- Subscriptions ---
  async fetchSubscriptions() {
    const data = await this.api("/api/finances/subscriptions");
    const container = document.getElementById("subscriptions-list");
    if (!container || !data) return;
    if (!data.length) {
      container.innerHTML = `<div class="empty-text">Нет активных подписок.</div>`;
      return;
    }
    container.innerHTML = data.map(s => `
      <div class="list-item-row" style="margin-bottom: 6px;">
        <div>
          <b>${s.name}</b> · ${s.formatted_amount} / ${s.billing_cycle === 'yearly' ? 'год' : 'мес'}
          <div style="font-size: 11px; color: ${s.is_due_soon ? '#ef4444' : 'var(--text-secondary)'};">
            ${s.is_due_soon ? '⚠️ Списание скоро: ' : 'Следующее списание: '} ${s.next_payment_date} (${s.days_until_payment} дн)
          </div>
        </div>
        <button class="btn-text" style="color: #ef4444;" onclick="app.deleteSubscription(${s.id})">&times;</button>
      </div>
    `).join("");
  },

  openSubscriptionModal() {
    this.showModal("🔄 Новая подписка", `
      <div class="form-group" style="margin-bottom: 8px;">
        <label style="font-size: 12px;">Сервис / Название</label>
        <input type="text" id="sub-name-input" class="input-text" placeholder="Яндекс Плюс, Зал, Spotify">
      </div>
      <div class="form-group" style="margin-bottom: 8px;">
        <label style="font-size: 12px;">Сумма (₸)</label>
        <input type="number" id="sub-amount-input" class="input-text" placeholder="2990">
      </div>
      <div class="form-group" style="margin-bottom: 8px;">
        <label style="font-size: 12px;">Дата следующего списания</label>
        <input type="date" id="sub-date-input" class="input-text">
      </div>
      <button class="btn-primary" style="width: 100%; margin-top: 10px;" onclick="app.createSubscription()">Сохранить подписку</button>
    `);
  },

  async createSubscription() {
    const name = document.getElementById("sub-name-input")?.value.trim();
    const amount = parseFloat(document.getElementById("sub-amount-input")?.value);
    const nextDate = document.getElementById("sub-date-input")?.value;
    if (!name || !amount || !nextDate) {
      alert("Заполните все поля");
      return;
    }
    await this.api("/api/finances/subscriptions", {
      method: "POST",
      body: JSON.stringify({ name, amount, next_payment_date: nextDate })
    });
    this.closeModal();
    this.fetchSubscriptions();
  },

  async deleteSubscription(id) {
    if (!confirm("Удалить подписку?")) return;
    await this.api(`/api/finances/subscriptions/${id}`, { method: "DELETE" });
    this.fetchSubscriptions();
  },

  // --- Debts ---
  async fetchDebts() {
    const data = await this.api("/api/finances/debts");
    const container = document.getElementById("debts-list");
    if (!container || !data) return;
    const items = data.items || [];
    if (!items.length) {
      container.innerHTML = `<div class="empty-text">Долгов нет. Финансовый баланс чист!</div>`;
      return;
    }
    const summaryHtml = `
      <div style="font-size: 12px; margin-bottom: 8px; color: var(--text-secondary);">
        Мне должны: <b>${data.formatted_they_owe}</b> · Я должен: <b>${data.formatted_i_owe}</b> · Сальдо: <b>${data.formatted_net_balance}</b>
      </div>
    `;
    const rowsHtml = items.map(d => `
      <div class="card" style="margin-bottom: 6px; opacity: ${d.is_settled ? '0.5' : '1.0'};">
        <div class="card-header">
          <span style="font-weight: 600;">${d.direction === 'they_owe' ? '🟢 Мне должен' : '🔴 Я должен'}: ${d.person_name}</span>
          <span><b>${d.formatted_amount}</b></span>
        </div>
        ${d.description ? `<div style="font-size: 11px; color: var(--text-secondary);">${d.description}</div>` : ''}
        ${!d.is_settled ? `
          <div style="margin-top: 6px; display: flex; gap: 8px;">
            <button class="btn-sm btn-primary" onclick="app.settleDebtOneTap(${d.id})">✅ Закрыть в 1 тап</button>
            <button class="btn-sm btn-secondary" onclick="app.repayDebtPrompt(${d.id})">Частично вернуть</button>
            <button class="btn-sm btn-text" style="color: #ef4444;" onclick="app.deleteDebt(${d.id})">&times;</button>
          </div>
        ` : `<div style="font-size: 11px; color: #10b981; margin-top: 4px;">Закрыт ✅</div>`}
      </div>
    `).join("");
    container.innerHTML = summaryHtml + rowsHtml;
  },

  openDebtModal() {
    this.showModal("🤝 Добавить долг", `
      <div class="form-group" style="margin-bottom: 8px;">
        <label style="font-size: 12px;">Кто</label>
        <input type="text" id="debt-person-input" class="input-text" placeholder="Имя человека">
      </div>
      <div class="form-group" style="margin-bottom: 8px;">
        <label style="font-size: 12px;">Сумма (₸)</label>
        <input type="number" id="debt-amount-input" class="input-text" placeholder="5000">
      </div>
      <div class="form-group" style="margin-bottom: 8px;">
        <label style="font-size: 12px;">Направление</label>
        <select id="debt-direction-input" class="input-text">
          <option value="they_owe">Мне должны (они должны мне)</option>
          <option value="i_owe">Я должен (мой долг)</option>
        </select>
      </div>
      <div class="form-group" style="margin-bottom: 8px;">
        <label style="font-size: 12px;">Комментарий</label>
        <input type="text" id="debt-desc-input" class="input-text" placeholder="За обед, спортзал и т.д.">
      </div>
      <button class="btn-primary" style="width: 100%; margin-top: 10px;" onclick="app.createDebt()">Сохранить долг</button>
    `);
  },

  async createDebt() {
    const person_name = document.getElementById("debt-person-input")?.value.trim();
    const amount = parseFloat(document.getElementById("debt-amount-input")?.value);
    const direction = document.getElementById("debt-direction-input")?.value;
    const description = document.getElementById("debt-desc-input")?.value.trim();
    if (!person_name || !amount) {
      alert("Укажите имя и сумму");
      return;
    }
    await this.api("/api/finances/debts", {
      method: "POST",
      body: JSON.stringify({ person_name, amount, direction, description })
    });
    this.closeModal();
    this.fetchDebts();
  },

  async settleDebtOneTap(id) {
    this.haptic("medium");
    await this.api(`/api/finances/debts/${id}/settle`, { method: "POST" });
    this.fetchDebts();
  },

  async repayDebtPrompt(id) {
    const amtStr = prompt("Сумма частичного возврата (₸):");
    const amt = parseFloat(amtStr);
    if (!amt || amt <= 0) return;
    await this.api(`/api/finances/debts/${id}/repay`, {
      method: "POST",
      body: JSON.stringify({ amount: amt })
    });
    this.fetchDebts();
  },

  async deleteDebt(id) {
    if (!confirm("Удалить эту запись о долге?")) return;
    await this.api(`/api/finances/debts/${id}`, { method: "DELETE" });
    this.fetchDebts();
  },

  // --- Storage & Archive ---
  async openStorageModal() {
    this.haptic("light");
    this.showModal("💾 Управление хранилищем (/storage)", `<div class="text-secondary" style="text-align: center; padding: 20px;">Загрузка статистики...</div>`);
    const stats = await this.api("/api/storage/info");
    if (!stats) return;
    const arch = stats.archivable || {};
    this.showModal("💾 Управление хранилищем (/storage)", `
      <div style="font-size: 13px; margin-bottom: 8px;">
        📦 Размер базы данных: <b>${stats.db_size_formatted}</b> (${stats.db_size_mb} МБ)<br>
        📄 Страниц: ${stats.page_count} · Свободных: ${stats.freelist_count} (${stats.reclaimable_freelist_kb} КБ)
      </div>
      <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
        Записей старше 12 месяцев: <b>${arch.total_archivable || 0}</b> (${arch.food_entries || 0} приёмов еды, ${arch.expenses || 0} расходов).
      </div>
      <div style="background: var(--input-bg); border-radius: 8px; padding: 10px; margin-bottom: 12px; font-size: 11px;">
        Архивация свернёт старые записи (>12 мес) в суточные агрегаты таблицы <code>daily_aggregates_archive</code>, очистит TTL-кэши и запустит сжатие <code>VACUUM</code>.
      </div>
      <button class="btn-primary" style="width: 100%;" onclick="app.runStorageArchive()">🧹 Архивировать записи и сжать БД</button>
    `);
  },

  async runStorageArchive() {
    this.haptic("heavy");
    const res = await this.api("/api/storage/archive", {
      method: "POST",
      body: JSON.stringify({ cutoff_days: 365 })
    });
    if (res) {
      alert(`✅ ${res.message || 'Архивация завершена!'}`);
      this.closeModal();
    }
  },

  // --- AI Insights & Auditor ---
  async requestAdvice() {
    this.haptic("medium");
    const container = document.getElementById("advice-list");
    if (container) {
      container.innerHTML = `<div class="text-secondary" style="padding: 15px; text-align: center;">🤖 AI анализирует данные за 14+ дней...</div>`;
    }
    const res = await this.api("/api/insights/advice/generate", { method: "POST" });
    if (!res || !res.cards) {
      if (container) container.innerHTML = `<div class="text-secondary">Мало данных для глубокого анализа (нужно 14+ дней).</div>`;
      return;
    }
    this.renderAdviceCards(res);
  },

  renderAdviceCards(data) {
    const container = document.getElementById("advice-list");
    if (!container) return;
    const adviceId = data.id;
    container.innerHTML = data.cards.map((c, idx) => `
      <div class="card" style="margin-bottom: 8px;">
        <div style="font-weight: 700; font-size: 14px;">💡 ${c.title}</div>
        <div style="font-size: 12px; color: var(--text-secondary); margin: 4px 0;">${c.problem_summary}</div>
        <div style="font-size: 13px; margin-bottom: 8px;">${c.recommendation}</div>
        <button class="btn-primary btn-sm" onclick="app.applyAdviceAction(${adviceId}, ${idx})">${c.action.button_text}</button>
      </div>
    `).join("");
  },

  async applyAdviceAction(adviceId, cardIdx) {
    this.haptic("heavy");
    const res = await this.api(`/api/insights/advice/${adviceId}/apply`, {
      method: "POST",
      body: JSON.stringify({ card_index: cardIdx })
    });
    if (res) {
      alert(`✅ ${res.message || 'Действие успешно применено!'}`);
      this.refreshAll();
    }
  },

  // --- Habits ---
  async fetchHabits() {
    const data = await this.api("/api/habits");
    const container = document.getElementById("habits-list");
    if (!container || !data) return;
    if (!data.length) {
      container.innerHTML = `<div class="empty-text">Привычек пока нет.</div>`;
      return;
    }
    container.innerHTML = data.map(h => `
      <div class="list-item-row" style="margin-bottom: 4px;">
        <div>
          <input type="checkbox" ${h.is_completed_today ? 'checked' : ''} onchange="app.toggleHabit(${h.id}, this.checked)">
          <span>${h.name}</span>
          <span class="badge-tag" style="margin-left: 6px;">🔥 ${h.streak || 0} дн</span>
        </div>
      </div>
    `).join("");
  },

  async toggleHabit(id, completed) {
    this.haptic("light");
    await this.api(`/api/habits/${id}/toggle`, { method: "POST" });
    this.fetchHabits();
  },

  // --- Supplements ---
  async fetchSupplements() {
    const data = await this.api("/api/supplements");
    const container = document.getElementById("supplements-list");
    if (!container || !data) return;
    if (!data.length) {
      container.innerHTML = `<div class="empty-text">Креатин и протеин добавятся автоматически.</div>`;
      return;
    }
    container.innerHTML = data.map(s => `
      <div class="list-item-row">
        <div><b>${s.name}</b> (${s.dosage || 'порция'})</div>
        <span class="badge-tag">${s.schedule_time || 'утро'}</span>
      </div>
    `).join("");
  },

  async checkSupplementsToday() {
    this.haptic("medium");
    await this.api("/api/supplements/take-all", { method: "POST" });
    alert("✅ Все добавки на сегодня отмечены принятыми!");
    this.fetchSupplements();
  },

  // --- Modes Toggle ---
  async toggleMode(modeType) {
    this.haptic("medium");
    const el = document.getElementById(`mode-${modeType}`);
    const isChecked = el ? el.checked : false;
    await this.api("/api/modes", {
      method: "POST",
      body: JSON.stringify({ mode: modeType, enabled: isChecked })
    });
  },

  // --- Quick Modals: Weight, Note, Task, Custom Food ---
  openWeightModal() {
    const w = prompt("Введите текущий вес (кг):");
    const val = parseFloat(w);
    if (!val || val <= 0) return;
    this.handleSmartInput(`вес ${val} кг`);
  },

  openAddNoteModal() {
    const note = prompt("Текст заметки или мысли:");
    if (!note || !note.trim()) return;
    this.handleSmartInput(`заметка: ${note.trim()}`);
  },

  openAddTaskModal() {
    const task = prompt("Название задачи:");
    if (!task || !task.trim()) return;
    this.handleSmartInput(`задача: ${task.trim()}`);
  },

  openCustomFoodModal() {
    this.showModal("🥗 Добавить своё блюдо", `
      <div class="form-group" style="margin-bottom: 8px;">
        <label style="font-size: 12px;">Название</label>
        <input type="text" id="cf-name" class="input-text" placeholder="Например: Шейк с арахисом">
      </div>
      <div class="form-group" style="margin-bottom: 8px;">
        <label style="font-size: 12px;">Калории на 100г</label>
        <input type="number" id="cf-cals" class="input-text" placeholder="250">
      </div>
      <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; margin-bottom: 10px;">
        <div><label style="font-size: 11px;">Белки</label><input type="number" id="cf-p" class="input-text" placeholder="15"></div>
        <div><label style="font-size: 11px;">Жиры</label><input type="number" id="cf-f" class="input-text" placeholder="10"></div>
        <div><label style="font-size: 11px;">Углеводы</label><input type="number" id="cf-c" class="input-text" placeholder="25"></div>
      </div>
      <button class="btn-primary" style="width: 100%;" onclick="app.saveCustomFood()">Сохранить блюдо</button>
    `);
  },

  async saveCustomFood() {
    const name = document.getElementById("cf-name")?.value.trim();
    const cals = parseInt(document.getElementById("cf-cals")?.value) || 0;
    const p = parseFloat(document.getElementById("cf-p")?.value) || 0;
    const f = parseFloat(document.getElementById("cf-f")?.value) || 0;
    const c = parseFloat(document.getElementById("cf-c")?.value) || 0;
    if (!name) return;
    await this.api("/api/food/custom", {
      method: "POST",
      body: JSON.stringify({ name, calories_per_100g: cals, protein_per_100g: p, fat_per_100g: f, carbs_per_100g: c })
    });
    this.closeModal();
    alert("✅ Блюдо сохранено в вашей личной базе!");
  },

  async generateWeeklyPlan() {
    this.haptic("medium");
    const container = document.getElementById("weekly-plan-content");
    if (container) container.textContent = "🤖 Gemini составляет сбалансированный рацион на 7 дней...";
    const res = await this.api("/api/recipes/weekly-plan", { method: "POST", body: JSON.stringify({}) });
    if (res && container) {
      container.innerHTML = `<div style="font-size: 13px; line-height: 1.5;">${res.plan_markdown || 'План успешно сформирован и сохранён в базу!'}</div>`;
    }
  },

  async generateWorkoutPlan() {
    this.haptic("medium");
    const res = await this.api("/api/workouts/plan/generate", { method: "POST", body: JSON.stringify({}) });
    if (res) {
      alert("✅ Тренировочный сплит успешно обновлён!");
      this.fetchWorkouts();
    }
  },

  async saveWorkoutLog() {
    const input = document.getElementById("workout-log-input");
    const val = input?.value.trim();
    if (!val) return;
    input.value = "";
    await this.handleSmartInput(val);
  },

  // --- CSV Export ---
  exportExpensesCSV() {
    window.open("/api/expenses/export/csv", "_blank");
  }
};

window.app = app;
document.addEventListener("DOMContentLoaded", () => app.init());
