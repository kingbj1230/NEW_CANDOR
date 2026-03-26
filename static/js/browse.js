let cachedPoliticians = [];
let cachedPromiseCards = [];
let candidateMap = new Map();
const PROMISE_CACHE_KEY = "promise_cards_cache_v20260325";
const PROMISE_CACHE_TTL_MS = 90 * 1000;

function debounce(fn, wait = 120) {
  let timer = null;
  return (...args) => {
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), wait);
  };
}

function readPromiseCardsCache() {
  try {
    const raw = sessionStorage.getItem(PROMISE_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const savedAt = Number(parsed?.savedAt || 0);
    const age = Date.now() - savedAt;
    if (!savedAt || age < 0 || age > PROMISE_CACHE_TTL_MS) return null;
    const candidates = Array.isArray(parsed?.candidates) ? parsed.candidates : [];
    const promises = Array.isArray(parsed?.promises) ? parsed.promises : [];
    return { candidates, promises };
  } catch (_err) {
    return null;
  }
}

function writePromiseCardsCache(payload) {
  try {
    const candidates = Array.isArray(payload?.candidates) ? payload.candidates : [];
    const promises = Array.isArray(payload?.promises) ? payload.promises : [];
    const row = JSON.stringify({
      savedAt: Date.now(),
      candidates,
      promises,
    });
    sessionStorage.setItem(PROMISE_CACHE_KEY, row);
  } catch (_err) {
    // Ignore cache write failures (quota/private mode).
  }
}

function toDateLabel(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString("ko-KR");
}

function formatPresidentialElectionTitle(value) {
  const text = String(value ?? "").trim();
  if (!/^\d+$/.test(text)) return text || "선거 정보 없음";
  const round = Number(text);
  if (!Number.isFinite(round) || round < 1) return text || "선거 정보 없음";
  return `제${round}대 대통령 선거`;
}

function toDateKey(value) {
  const text = String(value || "").trim();
  const plain = text.match(/^(\d{4}-\d{2}-\d{2})/);
  if (plain) return plain[1];
  if (!text) return "";
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return "";
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function todayDateKey() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getPublicPositionLabel(row) {
  const rawPosition = String(row?.position || "").trim();
  if (!rawPosition.includes("대통령")) return "";

  const today = todayDateKey();
  const termStart = toDateKey(row?.term_start);
  const termEnd = toDateKey(row?.term_end);

  if (termEnd && today > termEnd) return "전 대통령";
  if (termStart && today < termStart) return "대통령";
  return "대통령";
}

function splitCategory(category) {
  const parts = String(category || "")
    .split(/[>,/|]/g)
    .map((v) => v.trim())
    .filter(Boolean);
  return {
    primary: parts[0] || "미분류",
    secondary: parts[1] || "",
  };
}

function toProgressValue(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0 || n > 5) return null;
  return Math.round(n * 100) / 100;
}

function progressText(value) {
  const n = toProgressValue(value);
  if (n === null) return "미평가";
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, "");
}

function progressPercent(value) {
  const n = toProgressValue(value);
  if (n === null) return 0;
  return Math.max(0, Math.min(100, (n / 5) * 100));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function sanitizeUrl(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const parsed = new URL(raw, window.location.origin);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") return parsed.href;
  } catch (_err) {
    return "";
  }
  return "";
}

function normalizeCandidateId(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  const lowered = text.toLowerCase();
  if (["undefined", "null", "none", "nan"].includes(lowered)) return "";
  return text;
}

function setBrowseMessage(text, type = "info") {
  const el = document.getElementById("browseMessage");
  if (!el) return;
  el.className = `browse-message ${type}`;
  el.textContent = text;
}

async function apiPost(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.error || "요청에 실패했습니다.");
  return payload;
}

async function apiGet(url) {
  const resp = await fetch(url);
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.error || "요청에 실패했습니다.");
  return payload;
}

async function reportTarget({ candidateId = null, pledgeId = null }) {
  const reason = prompt("신고 사유를 입력해 주세요.", "부적합한 내용");
  if (reason === null) return;
  if (!reason.trim()) throw new Error("신고 사유를 입력해 주세요.");
  await apiPost("/api/report", {
    candidate_id: candidateId,
    pledge_id: pledgeId,
    reason: reason.trim(),
    report_type: "신고",
    reason_category: "콘텐츠 신고",
    target_url: window.location.href,
  });
}

function renderPoliticians(items) {
  const listEl = document.getElementById("politicianList");
  if (!listEl) return;
  if (!items.length) {
    listEl.innerHTML = '<p class="empty">검색 결과가 없습니다.</p>';
    return;
  }

  listEl.innerHTML = items
    .map(
      (c) => {
        const rawCandidateId = normalizeCandidateId(c.id);
        const candidateId = escapeHtml(rawCandidateId);
        const candidateName = escapeHtml(c.name || "-");
        const publicPosition = getPublicPositionLabel(c);
        const position = escapeHtml(publicPosition || "-");
        const party = escapeHtml(c.party || "-");
        const bioLine = [publicPosition, c.party].map((v) => String(v || "").trim()).filter(Boolean).join(" · ") || "-";
        const electionTitle = escapeHtml(formatPresidentialElectionTitle(c.election_title));
        const imageUrl = sanitizeUrl(c.image);
        return `
    <article class="politician-card" data-candidate-id="${candidateId}">
      <div class="politician-card-head ${imageUrl ? "" : "no-photo"}">
        ${imageUrl ? `<img src="${imageUrl}" alt="${candidateName || "정치인"}">` : ""}
        <div class="politician-actions" aria-hidden="true">
          <span class="action-chip">상세</span>
          <span class="action-chip action-primary">공약</span>
        </div>
      </div>
      <div class="meta">
        <h3>${candidateName}</h3>
        <p class="bio">${escapeHtml(bioLine)}</p>
        <div class="politician-stats">
          <span><strong>${electionTitle}</strong> 최근 선거</span>
          <span><strong>${party}</strong> 정당</span>
          ${publicPosition ? `<span><strong>${position}</strong> 직책</span>` : ""}
        </div>
        <div class="card-actions-row">
          <button type="button" class="report-btn" data-action="report-candidate" data-id="${candidateId}">신고</button>
        </div>
      </div>
    </article>
  `;
      }
    )
    .join("");
}

function renderPromises(items) {
  const listEl = document.getElementById("promiseList");
  if (!listEl) return;

  if (!items.length) {
    listEl.innerHTML = '<p class="empty">조건에 맞는 공약이 없습니다.</p>';
    return;
  }

  listEl.innerHTML = items
    .map((row) => {
      const candidateName = candidateMap.get(String(row.candidate_id))?.name || "후보자 정보 없음";
      const electionLine = `${row.election_type || "선거"} · ${formatPresidentialElectionTitle(row.election_title)} · ${toDateLabel(row.election_date)}`;
      const partyLine = `${row.party || "-"} · ${row.result || "-"} · 기호 ${row.candidate_number ?? "-"}`;
      const categoryInfo = splitCategory(row.category);
      const progressValue = progressText(row.progress_rate);
      const progressWidth = progressPercent(row.progress_rate);
      const content = String(row.content || "").trim() || "세부 실행 항목 없음";
      const candidateId = escapeHtml(normalizeCandidateId(row.candidate_id));
      const candidateElectionId = escapeHtml(row.candidate_election_id || "");
      const pledgeId = escapeHtml(row.pledge_id || "");
      const ariaName = escapeHtml(`${candidateName} 공약 상세 보기`);

      return `
      <article
        class="promise-card clickable no-avatar"
        data-candidate-id="${candidateId}"
        data-candidate-election-id="${candidateElectionId}"
        data-pledge-id="${pledgeId}"
        role="button"
        tabindex="0"
        aria-label="${ariaName}"
      >
        <div class="promise-content">
          <p class="bio">${escapeHtml(candidateName)}</p>
          <h3 class="promise-name">${escapeHtml(row.promise_title || "제목 없음")}</h3>
          <p class="bio">${escapeHtml(electionLine)}</p>
          <p class="bio">${escapeHtml(partyLine)}</p>
          <p class="promise-summary">${escapeHtml(content)}</p>

          <div class="promise-progress-row" title="이행률 ${escapeHtml(progressValue)}">
            <div class="promise-progress-track"><span style="width:${progressWidth}%;"></span></div>
            <span class="promise-progress-value">${escapeHtml(progressValue)}</span>
          </div>

          <div class="promise-meta">
            <span class="category">${escapeHtml(categoryInfo.primary)}</span>
            ${categoryInfo.secondary ? `<span class="category-sub">${escapeHtml(categoryInfo.secondary)}</span>` : ""}
          </div>

          <div class="card-actions-row">
            <button type="button" class="report-btn" data-action="report-pledge" data-id="${pledgeId}">신고</button>
          </div>
        </div>
      </article>
    `;
    })
    .join("");
}

function filterPoliticians(keyword) {
  const q = String(keyword || "").trim().toLowerCase();
  if (!q) return cachedPoliticians;
  return cachedPoliticians.filter((c) =>
    [c.name, c.party, getPublicPositionLabel(c)].some((v) => String(v || "").toLowerCase().includes(q))
  );
}

function getPromiseFilterValues() {
  return {
    keyword: document.getElementById("promiseSearchInput")?.value.trim().toLowerCase() || "",
    candidateId: document.getElementById("promiseCandidateFilter")?.value || "",
    electionId: document.getElementById("promiseElectionFilter")?.value || "",
    category: document.getElementById("promiseCategoryFilter")?.value || "",
  };
}

function hasActivePromiseFilters() {
  const v = getPromiseFilterValues();
  return Boolean(v.keyword || v.candidateId || v.electionId || v.category);
}

function pickRandomPromiseCards(limit = 10) {
  const rows = cachedPromiseCards.slice();
  for (let i = rows.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [rows[i], rows[j]] = [rows[j], rows[i]];
  }
  return rows.slice(0, limit);
}

function filterPromiseCards() {
  const { keyword, candidateId, electionId, category } = getPromiseFilterValues();
  const filtered = cachedPromiseCards.filter((row) => {
    const candidateName = candidateMap.get(String(row.candidate_id))?.name || "";
    const categoryInfo = splitCategory(row.category);
    const keywordMatched = !keyword || [row.promise_title, candidateName].some((v) => String(v || "").toLowerCase().includes(keyword));
    const candidateMatched = !candidateId || String(row.candidate_id || "") === String(candidateId);
    const electionMatched = !electionId || String(row.election_id || "") === String(electionId);
    const categoryMatched = !category || String(categoryInfo.primary || "") === category;
    return keywordMatched && candidateMatched && electionMatched && categoryMatched;
  });

  return filtered.sort((a, b) => {
    const byDate = String(b.election_date || "").localeCompare(String(a.election_date || ""));
    if (byDate !== 0) return byDate;
    const byCandidate = String(candidateMap.get(String(a.candidate_id))?.name || "").localeCompare(
      String(candidateMap.get(String(b.candidate_id))?.name || ""),
      "ko"
    );
    if (byCandidate !== 0) return byCandidate;
    const byPledge = Number(a.pledge_sort_order || 999999) - Number(b.pledge_sort_order || 999999);
    if (!Number.isNaN(byPledge) && byPledge !== 0) return byPledge;
    const byPromise = Number(a.promise_sort_order || 999999) - Number(b.promise_sort_order || 999999);
    if (!Number.isNaN(byPromise) && byPromise !== 0) return byPromise;
    return String(a.promise_title || "").localeCompare(String(b.promise_title || ""), "ko");
  });
}

function populateCandidateFilter() {
  const select = document.getElementById("promiseCandidateFilter");
  if (!select) return;
  const current = select.value;

  const rows = Array.from(
    new Map(
      cachedPromiseCards
        .map((row) => {
          const id = String(row.candidate_id || "");
          const name = candidateMap.get(id)?.name;
          if (!id || !name) return null;
          return [id, { id, name }];
        })
        .filter(Boolean)
    ).values()
  ).sort((a, b) => String(a.name).localeCompare(String(b.name), "ko"));

  select.innerHTML = '<option value="">전체 후보</option>' + rows.map((row) => `<option value="${escapeHtml(row.id)}">${escapeHtml(row.name)}</option>`).join("");
  if (current && rows.some((row) => String(row.id) === String(current))) select.value = current;
}

function populateElectionFilter() {
  const select = document.getElementById("promiseElectionFilter");
  if (!select) return;
  const current = select.value;

  const rows = Array.from(
    new Map(
      cachedPromiseCards
        .map((row) => {
          const id = String(row.election_id || "");
          if (!id) return null;
          const label = `${row.election_type || "선거"} · ${formatPresidentialElectionTitle(row.election_title)} · ${toDateLabel(row.election_date)}`;
          return [id, { id, label, date: row.election_date || "" }];
        })
        .filter(Boolean)
    ).values()
  ).sort((a, b) => String(b.date).localeCompare(String(a.date)));

  select.innerHTML = '<option value="">전체 선거</option>' + rows.map((row) => `<option value="${escapeHtml(row.id)}">${escapeHtml(row.label)}</option>`).join("");
  if (current && rows.some((row) => String(row.id) === String(current))) select.value = current;
}

function populateCategoryFilter() {
  const select = document.getElementById("promiseCategoryFilter");
  if (!select) return;
  const current = select.value;

  const categories = Array.from(
    new Set(
      cachedPromiseCards
        .map((row) => splitCategory(row.category).primary)
        .map((v) => String(v || "").trim())
        .filter(Boolean)
    )
  ).sort((a, b) => a.localeCompare(b, "ko"));

  select.innerHTML = '<option value="">전체 카테고리</option>' + categories.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
  if (current && categories.includes(current)) select.value = current;
}

async function fetchPoliticians() {
  const payload = await apiGet("/api/politicians");
  cachedPoliticians = payload.politicians || [];
  candidateMap = new Map(cachedPoliticians.map((row) => [String(row.id), row]));
}

async function fetchPromiseCards(forceRefresh = false) {
  if (!forceRefresh) {
    const cached = readPromiseCardsCache();
    if (cached) {
      cachedPromiseCards = cached.promises;
      candidateMap = new Map((cached.candidates || []).map((row) => [String(row.id), row]));
      return;
    }
  }

  const payload = await apiGet("/api/promises");
  cachedPromiseCards = payload.promises || [];
  const candidates = payload.candidates || [];
  candidateMap = new Map(candidates.map((row) => [String(row.id), row]));
  writePromiseCardsCache({ candidates, promises: cachedPromiseCards });
}

function bindPoliticianPage() {
  const input = document.getElementById("politicianSearchInput");
  const refreshBtn = document.getElementById("refreshPoliticiansBtn");
  const listEl = document.getElementById("politicianList");

  input?.addEventListener("input", () => renderPoliticians(filterPoliticians(input.value)));

  listEl?.addEventListener("click", async (event) => {
    const reportButton = event.target.closest("button[data-action='report-candidate']");
    if (reportButton) {
      event.stopPropagation();
      try {
        await reportTarget({ candidateId: reportButton.getAttribute("data-id") });
        await fetchPoliticians();
        renderPoliticians(filterPoliticians(input?.value || ""));
        setBrowseMessage("신고가 접수되었습니다.", "success");
      } catch (error) {
        setBrowseMessage(error.message || "신고 처리 실패", "error");
      }
      return;
    }

    const card = event.target.closest(".politician-card");
    if (!card) return;
    const candidateId = normalizeCandidateId(card.getAttribute("data-candidate-id"));
    if (!candidateId) {
      setBrowseMessage("정치인 ID를 확인할 수 없습니다. 목록을 새로고침해 주세요.", "error");
      return;
    }
    window.location.href = `/politicians/${encodeURIComponent(candidateId)}`;
  });

  const refresh = async () => {
    try {
      await fetchPoliticians();
      renderPoliticians(cachedPoliticians);
      setBrowseMessage("정치인 목록을 불러왔습니다.", "success");
    } catch (error) {
      setBrowseMessage(error.message || "정치인 조회 실패", "error");
    }
  };

  refreshBtn?.addEventListener("click", refresh);
  refresh();
}

function bindPromisePage() {
  const input = document.getElementById("promiseSearchInput");
  const candidate = document.getElementById("promiseCandidateFilter");
  const election = document.getElementById("promiseElectionFilter");
  const category = document.getElementById("promiseCategoryFilter");
  const listEl = document.getElementById("promiseList");

  const renderFiltered = () => {
    if (!hasActivePromiseFilters()) {
      renderPromises(pickRandomPromiseCards(10));
      return;
    }
    const rows = filterPromiseCards().slice(0, 10);
    renderPromises(rows);
  };

  input?.addEventListener("input", debounce(renderFiltered, 120));
  candidate?.addEventListener("change", renderFiltered);
  election?.addEventListener("change", renderFiltered);
  category?.addEventListener("change", renderFiltered);

  listEl?.addEventListener("click", async (event) => {
    const reportButton = event.target.closest("button[data-action='report-pledge']");
    if (reportButton) {
      event.stopPropagation();
      try {
        await reportTarget({ pledgeId: reportButton.getAttribute("data-id") });
        await fetchPromiseCards(true);
        populateCandidateFilter();
        populateElectionFilter();
        populateCategoryFilter();
        renderFiltered();
        setBrowseMessage("신고가 접수되었고 숨김 처리되었습니다.", "success");
      } catch (error) {
        setBrowseMessage(error.message || "신고 처리 실패", "error");
      }
      return;
    }

    const card = event.target.closest(".promise-card.clickable");
    if (!card) return;
    const candidateId = normalizeCandidateId(card.getAttribute("data-candidate-id"));
    if (!candidateId) {
      setBrowseMessage("정치인 연결 정보가 누락되었습니다. 다른 공약을 선택해 주세요.", "error");
      return;
    }

    const candidateElectionId = card.getAttribute("data-candidate-election-id") || "";
    const pledgeId = card.getAttribute("data-pledge-id") || "";
    const query = new URLSearchParams();
    if (candidateElectionId) query.set("ce", candidateElectionId);
    if (pledgeId) query.set("pledge", pledgeId);
    const suffix = query.toString() ? `?${query.toString()}` : "";

    window.location.href = `/politicians/${encodeURIComponent(candidateId)}${suffix}`;
  });

  listEl?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    if (event.target.closest("button, a, input, select, textarea")) return;
    const card = event.target.closest(".promise-card.clickable");
    if (!card) return;
    event.preventDefault();
    card.click();
  });

  const refresh = async () => {
    try {
      await fetchPromiseCards();
      populateCandidateFilter();
      populateElectionFilter();
      populateCategoryFilter();
      renderFiltered();
      setBrowseMessage("검색 조건이 없으면 무작위 10개 항목이 표시됩니다.", "info");
    } catch (error) {
      setBrowseMessage(error.message || "공약 조회 실패", "error");
    }
  };

  refresh();
}

document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname;
  if (path === "/politicians") bindPoliticianPage();
  else if (path === "/promises") bindPromisePage();
});

