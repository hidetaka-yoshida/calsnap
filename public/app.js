(() => {
  const state = {
    period: "day",
    date: toLocalDateStr(new Date()),
    portion: "normal",
    inputTab: "photo",
    imageDataUrl: "",
    imageFilename: "",
    colorProfile: null,
    lastSource: "dictionary",
    settings: {
      bmr: 1500,
      target_calories: 1800,
      has_gemini_key: false,
      gemini_api_key_masked: "",
      use_ai: false,
    },
  };

  function toLocalDateStr(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function toLocalDatetimeStr(d) {
    const base = toLocalDateStr(d);
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${base}T${hh}:${mm}`;
  }

  function showToast(msg) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => el.classList.add("hidden"), 2600);
  }

  async function api(url, options = {}) {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (res.status === 401) {
      document.getElementById("authOverlay").classList.remove("hidden");
      throw new Error("AUTH_REQUIRED");
    }
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    return res.json();
  }

  // --- Initialization ---
  document.addEventListener("DOMContentLoaded", async () => {
    document.getElementById("mealDatetime").value = toLocalDatetimeStr(new Date());
    document.getElementById("datePicker").value = state.date;

    bindEvents();
    const authStatus = await api("/api/auth/status").catch(() => ({
      auth_mode: "none",
      auth_required: false,
      authenticated: true,
    }));
    if (authStatus.auth_required && !authStatus.authenticated) {
      showAuthOverlay(authStatus);
      return;
    }
    applyAuthenticatedUser(authStatus);
    await loadSettings();
    await refreshSummary();
  });

  function applyAuthenticatedUser(authStatus) {
    const logoutBtn = document.getElementById("logoutBtn");
    const userBadge = document.getElementById("userBadge");
    if (authStatus.auth_required) {
      logoutBtn.classList.remove("hidden");
    }
    if (authStatus.user && authStatus.user.name) {
      userBadge.textContent = `👤 ${authStatus.user.name}`;
      userBadge.classList.remove("hidden");
    }
  }

  function showAuthOverlay(authStatus) {
    const overlay = document.getElementById("authOverlay");
    const desc = document.getElementById("authDesc");
    const googleWrap = document.getElementById("googleSignInWrap");
    const passForm = document.getElementById("authForm");
    overlay.classList.remove("hidden");

    if (authStatus.auth_mode === "google" && authStatus.google_client_id) {
      desc.textContent = "Googleアカウントでログインして個人の記録を利用します";
      googleWrap.classList.remove("hidden");
      passForm.classList.add("hidden");
      initGoogleSignIn(authStatus.google_client_id);
    } else {
      desc.textContent = "パスコードを入力してロックを解除してください";
      passForm.classList.remove("hidden");
      googleWrap.classList.add("hidden");
    }
  }

  function initGoogleSignIn(clientId) {
    const renderBtn = () => {
      if (!window.google || !window.google.accounts || !window.google.accounts.id) return;
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: async (response) => {
          const errEl = document.getElementById("authError");
          errEl.classList.add("hidden");
          try {
            const res = await fetch("/api/auth/google", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ id_token: response.credential }),
            });
            const data = await res.json();
            if (!res.ok) {
              errEl.textContent = data.error || "ログインに失敗しました";
              errEl.classList.remove("hidden");
              return;
            }
            document.getElementById("authOverlay").classList.add("hidden");
            applyAuthenticatedUser({ auth_required: true, user: data.user });
            await loadSettings();
            await refreshSummary();
          } catch (err) {
            errEl.textContent = "通信エラーが発生しました";
            errEl.classList.remove("hidden");
          }
        },
      });
      const container = document.getElementById("googleBtnContainer");
      container.innerHTML = "";
      window.google.accounts.id.renderButton(container, {
        theme: "outline",
        size: "large",
        width: 260,
        locale: "ja",
      });
    };

    if (window.google && window.google.accounts) {
      renderBtn();
      return;
    }
    if (!document.getElementById("gisScript")) {
      const s = document.createElement("script");
      s.id = "gisScript";
      s.src = "https://accounts.google.com/gsi/client";
      s.async = true;
      s.defer = true;
      s.onload = renderBtn;
      document.head.appendChild(s);
    }
  }

  function bindEvents() {
    // Input mode tabs
    document.querySelectorAll("[data-input-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.inputTab = btn.dataset.inputTab;
        document.querySelectorAll("[data-input-tab]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById("textPanel").classList.toggle("hidden", state.inputTab !== "text");
        document.getElementById("photoPanel").classList.toggle("hidden", state.inputTab !== "photo");
      });
    });

    // Quick chips
    document.querySelectorAll("[data-quick]").forEach((chip) => {
      chip.addEventListener("click", () => {
        document.getElementById("mealQuery").value = chip.dataset.quick;
        runEstimate("text");
      });
    });

    // Portion buttons
    document.querySelectorAll("[data-portion]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.portion = btn.dataset.portion;
        document.querySelectorAll("[data-portion]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        if (state.inputTab === "text" && document.getElementById("mealQuery").value.trim()) {
          runEstimate("text");
        } else if (state.inputTab === "photo" && state.imageDataUrl) {
          runEstimate("photo");
        }
      });
    });

    document.getElementById("estimateTextBtn").addEventListener("click", () => runEstimate("text"));
    document.getElementById("mealQuery").addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        runEstimate("text");
      }
    });

    document.getElementById("estimatePhotoBtn").addEventListener("click", () => runEstimate("photo"));

    // Photo drop, direct camera & album input
    const dropZone = document.getElementById("dropZone");
    const photoInput = document.getElementById("photoInput");
    const cameraInput = document.getElementById("cameraInput");

    document.getElementById("cameraBtn").addEventListener("click", () => cameraInput.click());
    document.getElementById("albumBtn").addEventListener("click", () => photoInput.click());

    cameraInput.addEventListener("change", () => {
      const file = cameraInput.files && cameraInput.files[0];
      if (file) handlePhotoFile(file);
    });

    dropZone.addEventListener("click", (e) => {
      if (e.target.id !== "clearPhotoBtn") {
        photoInput.click();
      }
    });

    document.getElementById("logoutBtn").addEventListener("click", async () => {
      await fetch("/api/auth/logout", { method: "POST" });
      window.location.reload();
    });

    document.getElementById("authForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const passcode = document.getElementById("passcodeInput").value;
      const errEl = document.getElementById("authError");
      errEl.classList.add("hidden");
      try {
        const res = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ passcode }),
        });
        if (!res.ok) {
          errEl.textContent = "パスコードが違います";
          errEl.classList.remove("hidden");
          return;
        }
        document.getElementById("authOverlay").classList.add("hidden");
        document.getElementById("passcodeInput").value = "";
        await loadSettings();
        await refreshSummary();
      } catch (err) {
        errEl.textContent = "通信エラーが発生しました";
        errEl.classList.remove("hidden");
      }
    });

    dropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    });

    dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));

    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
      const file = e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) handlePhotoFile(file);
    });

    photoInput.addEventListener("change", () => {
      const file = photoInput.files && photoInput.files[0];
      if (file) handlePhotoFile(file);
    });

    document.getElementById("clearPhotoBtn").addEventListener("click", (e) => {
      e.stopPropagation();
      clearPhoto();
    });

    // Meal form submit
    document.getElementById("mealForm").addEventListener("submit", saveMeal);

    // Period tabs & date nav
    document.querySelectorAll("[data-period]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.period = btn.dataset.period;
        document.querySelectorAll("[data-period]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        refreshSummary();
      });
    });

    document.getElementById("prevPeriodBtn").addEventListener("click", () => shiftDate(-1));
    document.getElementById("nextPeriodBtn").addEventListener("click", () => shiftDate(1));
    document.getElementById("todayBtn").addEventListener("click", () => {
      state.date = toLocalDateStr(new Date());
      document.getElementById("datePicker").value = state.date;
      refreshSummary();
    });
    document.getElementById("datePicker").addEventListener("change", (e) => {
      if (e.target.value) {
        state.date = e.target.value;
        refreshSummary();
      }
    });

    // Settings modal
    document.getElementById("openSettingsBtn").addEventListener("click", openSettings);
    document.getElementById("closeSettingsBtn").addEventListener("click", closeSettings);
    document.getElementById("cancelSettingsBtn").addEventListener("click", closeSettings);
    document.querySelector("#settingsModal .modal-backdrop").addEventListener("click", closeSettings);
    document.getElementById("settingsForm").addEventListener("submit", saveSettings);

    document.getElementById("calcBmrBtn").addEventListener("click", () => {
      const sex = document.getElementById("calcSex").value;
      const age = Number(document.getElementById("calcAge").value) || 30;
      const h = Number(document.getElementById("calcHeight").value) || 170;
      const w = Number(document.getElementById("calcWeight").value) || 65;
      // Mifflin-St Jeor equation
      const bmr = Math.round(10 * w + 6.25 * h - 5 * age + (sex === "male" ? 5 : -161));
      document.getElementById("settingBmr").value = bmr;
      document.getElementById("settingTarget").value = Math.round(bmr * 1.25);
      showToast(`基礎代謝量を ${bmr} kcal として計算しました`);
    });

    document.querySelectorAll("[data-goal]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const bmr = Number(document.getElementById("settingBmr").value) || 1500;
        const mult = { diet: 1.15, maintain: 1.35, bulk: 1.55 }[btn.dataset.goal] || 1.25;
        document.getElementById("settingTarget").value = Math.round(bmr * mult);
      });
    });
  }

  function shiftDate(dir) {
    const d = new Date(`${state.date}T12:00:00`);
    if (state.period === "day") {
      d.setDate(d.getDate() + dir);
    } else if (state.period === "week") {
      d.setDate(d.getDate() + dir * 7);
    } else {
      d.setMonth(d.getMonth() + dir);
    }
    state.date = toLocalDateStr(d);
    document.getElementById("datePicker").value = state.date;
    refreshSummary();
  }

  // --- Photo processing (resize + color profile in browser = 0 cost) ---
  function handlePhotoFile(file) {
    state.imageFilename = file.name || "";
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        const maxSide = 512;
        let w = img.width;
        let h = img.height;
        if (w > maxSide || h > maxSide) {
          if (w > h) {
            h = Math.round((h * maxSide) / w);
            w = maxSide;
          } else {
            w = Math.round((w * maxSide) / h);
            h = maxSide;
          }
        }
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, w, h);

        // Extract simple color profile for zero-cost heuristic
        const pixels = ctx.getImageData(0, 0, w, h).data;
        let greenCount = 0;
        let warmCount = 0;
        let brightSum = 0;
        const totalPx = pixels.length / 4;
        for (let i = 0; i < pixels.length; i += 4) {
          const r = pixels[i];
          const g = pixels[i + 1];
          const b = pixels[i + 2];
          brightSum += (r + g + b) / (3 * 255);
          if (g > r + 12 && g > b + 12) greenCount++;
          if (r > b + 25 && r >= g) warmCount++;
        }
        state.colorProfile = {
          green_ratio: Number((greenCount / totalPx).toFixed(3)),
          warm_ratio: Number((warmCount / totalPx).toFixed(3)),
          brightness: Number((brightSum / totalPx).toFixed(3)),
        };

        state.imageDataUrl = canvas.toDataURL("image/jpeg", 0.72);
        document.getElementById("photoPreview").src = state.imageDataUrl;
        document.getElementById("dropPlaceholder").classList.add("hidden");
        document.getElementById("photoPreviewWrap").classList.remove("hidden");
        runEstimate("photo");
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  }

  function clearPhoto() {
    state.imageDataUrl = "";
    state.imageFilename = "";
    state.colorProfile = null;
    document.getElementById("photoInput").value = "";
    document.getElementById("cameraInput").value = "";
    document.getElementById("photoPreview").src = "";
    document.getElementById("photoPreviewWrap").classList.add("hidden");
    document.getElementById("dropPlaceholder").classList.remove("hidden");
  }

  async function runEstimate(mode) {
    const query =
      mode === "photo"
        ? document.getElementById("photoHint").value.trim()
        : document.getElementById("mealQuery").value.trim();

    try {
      const res = await api("/api/estimate", {
        method: "POST",
        body: JSON.stringify({
          query,
          portion: state.portion,
          image_data_url: mode === "photo" ? state.imageDataUrl : "",
          filename: mode === "photo" ? state.imageFilename : "",
          color_profile: mode === "photo" ? state.colorProfile : null,
        }),
      });

      state.lastSource = res.method || "dictionary";
      document.getElementById("mealName").value = res.matched_name || query || "食事";
      document.getElementById("mealCalories").value = res.calories;
      document.getElementById("mealProtein").value = res.protein;
      document.getElementById("mealFat").value = res.fat;
      document.getElementById("mealCarbs").value = res.carbs;

      const box = document.getElementById("estimateBox");
      box.classList.remove("hidden");
      document.getElementById("estimateNote").textContent = res.note || "概算値を反映しました。";

      const candList = document.getElementById("candidateList");
      candList.innerHTML = "";
      if (Array.isArray(res.candidates) && res.candidates.length > 0) {
        res.candidates.forEach((c) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "candidate-chip";
          btn.textContent = `${c.name} (${c.calories} kcal)`;
          btn.addEventListener("click", () => {
            document.getElementById("mealName").value = c.name;
            document.getElementById("mealCalories").value = c.calories;
            document.getElementById("mealProtein").value = c.protein;
            document.getElementById("mealFat").value = c.fat;
            document.getElementById("mealCarbs").value = c.carbs;
          });
          candList.appendChild(btn);
        });
      }
    } catch (err) {
      showToast("概算に失敗しました");
    }
  }

  async function saveMeal(e) {
    e.preventDefault();
    const payload = {
      name: document.getElementById("mealName").value.trim() || "食事",
      calories: Number(document.getElementById("mealCalories").value) || 0,
      protein: Number(document.getElementById("mealProtein").value) || 0,
      fat: Number(document.getElementById("mealFat").value) || 0,
      carbs: Number(document.getElementById("mealCarbs").value) || 0,
      meal_type: document.getElementById("mealType").value,
      eaten_at: document.getElementById("mealDatetime").value,
      source: state.lastSource,
      image_data_url: state.inputTab === "photo" ? state.imageDataUrl : "",
    };

    try {
      await api("/api/meals", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showToast("食事を記録しました");
      // Switch view date to the recorded date so user sees it right away
      if (payload.eaten_at) {
        state.date = payload.eaten_at.slice(0, 10);
        document.getElementById("datePicker").value = state.date;
      }
      document.getElementById("mealQuery").value = "";
      document.getElementById("photoHint").value = "";
      document.getElementById("estimateBox").classList.add("hidden");
      clearPhoto();
      await refreshSummary();
    } catch (err) {
      showToast("記録の保存に失敗しました");
    }
  }

  async function deleteMeal(id) {
    try {
      await api(`/api/meals/${id}`, { method: "DELETE" });
      showToast("記録を削除しました");
      await refreshSummary();
    } catch (err) {
      showToast("削除に失敗しました");
    }
  }

  // --- Summary & Visualization ---
  async function refreshSummary() {
    try {
      const data = await api(
        `/api/summary?period=${encodeURIComponent(state.period)}&date=${encodeURIComponent(state.date)}`
      );
      renderStatusCards(data);
      renderPeriodStats(data);
      renderChart(data);
      renderMealList(data.meals || []);
    } catch (err) {
      showToast("集計データの取得に失敗しました");
    }
  }

  function renderStatusCards(data) {
    const bmr = data.bmr;
    const target = Math.max(data.target_calories, bmr);
    const val = data.period === "day" ? data.total_calories : data.average_calories;
    const j = data.judgment;

    document.getElementById("statusDateLabel").textContent =
      data.period === "day"
        ? `${data.date} の摂取状況`
        : `${data.start_date} 〜 ${data.end_date} の1日平均`;

    const badge = document.getElementById("judgmentBadge");
    badge.textContent = j.label;
    badge.className = `status-pill ${j.color}`;

    document.getElementById("heroCalories").textContent = val.toLocaleString();
    document.getElementById("heroTarget").textContent = target.toLocaleString();
    document.getElementById("judgmentDetail").textContent = j.detail;

    document.getElementById("bmrMarkerLabel").textContent = `基礎代謝: ${bmr}`;
    document.getElementById("targetMarkerLabel").textContent = `目標: ${target}`;

    const scaleMax = Math.max(target * 1.35, val * 1.1, 2200);
    const pct = (v) => Math.min(100, Math.max(0, (v / scaleMax) * 100));

    document.getElementById("bmrZone").style.width = `${pct(bmr)}%`;
    document.getElementById("bmrLine").style.left = `${pct(bmr)}%`;
    document.getElementById("targetLine").style.left = `${pct(target)}%`;

    const bar = document.getElementById("calorieBar");
    bar.style.width = `${pct(val)}%`;
    const colorMap = {
      green: "var(--green)",
      amber: "var(--amber)",
      blue: "var(--blue)",
      orange: "var(--orange)",
      red: "var(--red)",
      gray: "var(--gray)",
    };
    bar.style.backgroundColor = colorMap[j.color] || "var(--green)";

    // PFC
    const p = data.protein || 0;
    const f = data.fat || 0;
    const c = data.carbs || 0;
    const totalPfcCal = Math.max(1, p * 4 + f * 9 + c * 4);
    document.getElementById("pVal").textContent = `${p.toFixed(1)} g (${Math.round((p * 400) / totalPfcCal)}%)`;
    document.getElementById("fVal").textContent = `${f.toFixed(1)} g (${Math.round((f * 900) / totalPfcCal)}%)`;
    document.getElementById("cVal").textContent = `${c.toFixed(1)} g (${Math.round((c * 400) / totalPfcCal)}%)`;

    document.getElementById("pBar").style.width = `${Math.min(100, (p * 400) / totalPfcCal)}%`;
    document.getElementById("fBar").style.width = `${Math.min(100, (f * 900) / totalPfcCal)}%`;
    document.getElementById("cBar").style.width = `${Math.min(100, (c * 400) / totalPfcCal)}%`;
    document.getElementById("mealCountLabel").textContent = `${(data.meals || []).length}件の記録`;
  }

  function renderPeriodStats(data) {
    const titleEl = document.getElementById("periodTitle");
    if (data.period === "day") {
      titleEl.textContent = data.date;
    } else if (data.period === "week") {
      titleEl.textContent = `${data.start_date} 〜 ${data.end_date}`;
    } else {
      titleEl.textContent = data.date.slice(0, 7);
    }

    document.getElementById("statTotal").textContent = `${data.total_calories.toLocaleString()} kcal`;
    document.getElementById("statAvg").textContent = `${data.average_calories.toLocaleString()} kcal`;
    document.getElementById("statGood").textContent = `${data.good_days} / ${data.recorded_days || data.total_days} 日`;
  }

  function renderChart(data) {
    const container = document.getElementById("chartContainer");
    const bmr = data.bmr;
    const target = Math.max(data.target_calories, bmr);

    // For 'day', show meal-by-meal bars if meals exist, otherwise the single day bar
    let items = [];
    if (data.period === "day") {
      if (data.meals && data.meals.length > 0) {
        items = data.meals.map((m) => ({
          label: `${m.meal_type} (${m.eaten_at.slice(11, 16)})`,
          calories: m.calories,
          color: "#3b82f6",
          tooltip: `${m.name}: ${m.calories} kcal`,
        }));
      } else {
        items = [{ label: data.date.slice(5), calories: 0, color: "#cbd5e1", tooltip: "記録なし" }];
      }
    } else {
      const colorMap = {
        green: "#10b981",
        amber: "#f59e0b",
        blue: "#3b82f6",
        orange: "#f97316",
        red: "#ef4444",
        gray: "#cbd5e1",
      };
      items = (data.days || []).map((d) => ({
        label: data.period === "month" ? d.date.slice(8) : d.label,
        calories: d.calories,
        color: colorMap[d.judgment.color] || "#10b981",
        tooltip: `${d.date}: ${d.calories} kcal (${d.judgment.label})`,
      }));
    }

    const isMonth = data.period === "month";
    const width = isMonth ? Math.max(560, items.length * 20) : Math.max(300, items.length * 46);
    const height = 200;
    const padL = 40;
    const padR = 12;
    const padT = 16;
    const padB = 28;
    const plotW = width - padL - padR;
    const plotH = height - padT - padB;

    const maxItemCal = Math.max(...items.map((i) => i.calories), 0);
    const yMax = Math.max(target * 1.25, maxItemCal * 1.12, 1000);

    const yPos = (val) => padT + plotH - (val / yMax) * plotH;
    const step = plotW / items.length;
    const barW = Math.max(8, Math.min(34, step * 0.62));

    const svgStyle = isMonth
      ? `style="display:block; min-width:${width}px;"`
      : `style="display:block; width:100%; max-width:100%;"`;
    let svg = `<svg viewBox="0 0 ${width} ${height}" ${svgStyle} height="${height}" xmlns="http://www.w3.org/2000/svg">`;

    // Horizontal grid lines
    [0, 0.5, 1].forEach((ratio) => {
      const v = Math.round(yMax * ratio);
      const y = yPos(v);
      svg += `<line x1="${padL}" y1="${y}" x2="${width - padR}" y2="${y}" stroke="#e2e8f0" stroke-width="1" />`;
      svg += `<text x="${padL - 6}" y="${y + 4}" text-anchor="end" font-size="10" fill="#64748b">${v}</text>`;
    });

    // Bars
    items.forEach((it, idx) => {
      const x = padL + idx * step + (step - barW) / 2;
      const y = yPos(it.calories);
      const h = Math.max(0, padT + plotH - y);
      svg += `<g><title>${escapeXml(it.tooltip)}</title>`;
      svg += `<rect x="${x}" y="${y}" width="${barW}" height="${h}" rx="4" fill="${it.color}" />`;
      if (data.period !== "month" || idx % 2 === 0) {
        svg += `<text x="${x + barW / 2}" y="${height - 8}" text-anchor="middle" font-size="10" fill="#64748b">${escapeXml(it.label)}</text>`;
      }
      svg += `</g>`;
    });

    // BMR & Target reference lines (for week/month daily comparison)
    if (data.period !== "day") {
      const yBmr = yPos(bmr);
      const yTarget = yPos(target);
      svg += `<line x1="${padL}" y1="${yBmr}" x2="${width - padR}" y2="${yBmr}" stroke="#d97706" stroke-width="1.5" />`;
      svg += `<line x1="${padL}" y1="${yTarget}" x2="${width - padR}" y2="${yTarget}" stroke="#1e293b" stroke-width="1.5" stroke-dasharray="4 3" />`;
    }

    svg += `</svg>`;
    container.innerHTML = svg;
  }

  function escapeXml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderMealList(meals) {
    const list = document.getElementById("mealList");
    list.innerHTML = "";
    if (!meals.length) {
      list.innerHTML = `<p class="muted-text">この期間の食事記録はまだありません。</p>`;
      return;
    }

    meals.slice().reverse().forEach((m) => {
      const item = document.createElement("div");
      item.className = "meal-item";

      const left = document.createElement("div");
      left.className = "meal-left";

      if (m.image_path) {
        const img = document.createElement("img");
        img.src = m.image_path;
        img.className = "meal-thumb";
        img.alt = m.name;
        left.appendChild(img);
      }

      const info = document.createElement("div");
      const title = document.createElement("div");
      title.className = "meal-title";
      title.textContent = m.name;

      const meta = document.createElement("div");
      meta.className = "meal-meta";
      meta.textContent = `${m.eaten_at.replace("T", " ").slice(0, 16)} ・ ${m.meal_type} ・ P:${m.protein}g F:${m.fat}g C:${m.carbs}g`;

      info.appendChild(title);
      info.appendChild(meta);
      left.appendChild(info);

      const right = document.createElement("div");
      right.className = "meal-right";

      const kcal = document.createElement("span");
      kcal.className = "meal-kcal";
      kcal.textContent = `${m.calories} kcal`;

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "btn btn-sm btn-outline";
      delBtn.textContent = "削除";
      delBtn.addEventListener("click", () => deleteMeal(m.id));

      right.appendChild(kcal);
      right.appendChild(delBtn);

      item.appendChild(left);
      item.appendChild(right);
      list.appendChild(item);
    });
  }

  // --- Settings ---
  async function loadSettings() {
    try {
      state.settings = await api("/api/settings");
      updateModeBadge();
    } catch (err) {
      // ignore
    }
  }

  function updateModeBadge() {
    const badge = document.getElementById("modeBadge");
    if (state.settings.use_ai && state.settings.has_gemini_key) {
      badge.textContent = "運用コスト: 低コストAI併用 (Gemini Flash-Lite)";
      badge.classList.add("ai-on");
    } else {
      badge.textContent = "運用コスト: 0円（ローカル推定）";
      badge.classList.remove("ai-on");
    }
  }

  function openSettings() {
    document.getElementById("settingBmr").value = state.settings.bmr;
    document.getElementById("settingTarget").value = state.settings.target_calories;
    document.getElementById("settingUseAi").checked = Boolean(state.settings.use_ai);
    document.getElementById("settingApiKey").value = "";
    document.getElementById("apiKeyStatus").textContent = state.settings.has_gemini_key
      ? `現在のキー: ${state.settings.gemini_api_key_masked}（変更する場合のみ入力）`
      : "未設定（完全無料モードで動作中）";
    document.getElementById("settingsModal").classList.remove("hidden");
  }

  function closeSettings() {
    document.getElementById("settingsModal").classList.add("hidden");
  }

  async function saveSettings(e) {
    e.preventDefault();
    const payload = {
      bmr: Number(document.getElementById("settingBmr").value) || 1500,
      target_calories: Number(document.getElementById("settingTarget").value) || 1800,
      use_ai: document.getElementById("settingUseAi").checked,
    };
    const keyInput = document.getElementById("settingApiKey").value.trim();
    if (keyInput) {
      payload.gemini_api_key = keyInput;
    }

    try {
      state.settings = await api("/api/settings", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      updateModeBadge();
      closeSettings();
      showToast("設定を保存しました");
      await refreshSummary();
    } catch (err) {
      showToast("設定の保存に失敗しました");
    }
  }
})();
