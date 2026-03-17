let isAdmin = false;
let candidateData = null;
let pledgeData = [];
let electionSections = [];
let pledgeById = new Map();
let isLoggedIn = false;

function normalizeCandidateId(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  const lowered = text.toLowerCase();
  if (["undefined", "null", "none", "nan"].includes(lowered)) return "";
  return text;
}

function resolveCandidateId() {
  const fromWindow = normalizeCandidateId(window.POLITICIAN_DETAIL_ID);
  if (fromWindow) return fromWindow;

  const path = String(window.location.pathname || "");
  const prefix = "/politicians/";
  if (!path.startsWith(prefix)) return "";
  const tail = path.slice(prefix.length).split("/")[0];
  if (!tail) return "";
  try {
    return normalizeCandidateId(decodeURIComponent(tail));
  } catch (_err) {
    return normalizeCandidateId(tail);
  }
}

const detailLoadingEl = document.getElementById("politicianDetailLoading");
const detailPanelEl = document.getElementById("politicianDetailPanel");
const progressEditorModalEl = document.getElementById("progressEditorModal");
const progressEditorForm = document.getElementById("progressEditorForm");
const progressEditorNodePathEl = document.getElementById("progressEditorNodePath");
const progressEditorNodeIdInput = document.getElementById("progressEditorNodeId");
const progressEditorSourceIdInput = document.getElementById("progressEditorSourceId");
const progressEditorRateInput = document.getElementById("progressEditorRate");
const progressEditorStatusInput = document.getElementById("progressEditorStatus");
const progressEditorEvaluatorInput = document.getElementById("progressEditorEvaluator");
const progressEditorDateInput = document.getElementById("progressEditorDate");
const progressEditorReasonInput = document.getElementById("progressEditorReason");
const progressEditorSourceTitleInput = document.getElementById("progressEditorSourceTitle");
const progressEditorSourceUrlInput = document.getElementById("progressEditorSourceUrl");
const progressEditorSourceTypeInput = document.getElementById("progressEditorSourceType");
const progressEditorSourceDateInput = document.getElementById("progressEditorSourceDate");
const progressEditorSourcePublisherInput = document.getElementById("progressEditorSourcePublisher");
const progressEditorSourceSummaryInput = document.getElementById("progressEditorSourceSummary");
const progressEditorSourceRoleInput = document.getElementById("progressEditorSourceRole");
const progressEditorPageNoInput = document.getElementById("progressEditorPageNo");
const progressEditorQuoteInput = document.getElementById("progressEditorQuote");
const progressEditorLinkNoteInput = document.getElementById("progressEditorLinkNote");
const progressEditorSaveBtn = document.getElementById("progressEditorSaveBtn");

function setMessage(text, type = "info") {
  const el = document.getElementById("browseMessage");
  if (!el) return;
  el.className = `browse-message ${type}`;
  el.textContent = text;
}

function setActionButtonBusy(button, busyText = "처리 중...") {
  if (!button) return () => {};
  const originalText = button.textContent || "";
  button.setAttribute("data-original-text", originalText);
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.textContent = busyText;

  return () => {
    const restoreText = button.getAttribute("data-original-text");
    if (restoreText !== null) {
      button.textContent = restoreText;
      button.removeAttribute("data-original-text");
    }
    button.disabled = false;
    button.removeAttribute("aria-busy");
  };
}

function setDetailLoadingState(isLoading, showContentWhenDone = true) {
  if (detailLoadingEl) detailLoadingEl.hidden = !isLoading;
  const shouldShowContent = !isLoading && showContentWhenDone;
  if (detailPanelEl) detailPanelEl.hidden = !shouldShowContent;
}

async function apiPost(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.error || "요청 실패");
  return payload;
}

async function uploadImage(file) {
  const formData = new FormData();
  formData.append("image", file);
  const resp = await fetch("/api/upload-image", { method: "POST", body: formData });
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.error || "이미지 업로드 실패");
  return payload.path;
}

async function apiGet(url) {
  const resp = await fetch(url);
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.error || "요청 실패");
  return payload;
}

function applyLoginState(loggedIn, userId = "", email = "") {
  isLoggedIn = Boolean(loggedIn);
  window.APP_CONTEXT = {
    ...(window.APP_CONTEXT || {}),
    userId: userId || null,
    email: email || null,
  };
}

function readLoginStateFromContext() {
  const userId = String(window.APP_CONTEXT?.userId || window.APP_CONTEXT?.user_id || "").trim();
  const email = String(window.APP_CONTEXT?.email || "").trim();
  return {
    loggedIn: Boolean(userId || email),
    userId,
    email,
  };
}

async function syncLoginState() {
  const local = readLoginStateFromContext();
  applyLoginState(local.loggedIn, local.userId, local.email);
  try {
    const payload = await apiGet("/auth/session");
    if (payload && typeof payload.logged_in === "boolean") {
      const userId = String(payload.user_id || "").trim();
      const email = String(payload.email || "").trim();
      applyLoginState(payload.logged_in, userId, email);
      if (typeof payload.is_admin === "boolean") {
        isAdmin = payload.is_admin;
      }
    }
  } catch (_err) {
    // Keep local context state when session endpoint is temporarily unavailable.
  }
  return isLoggedIn;
}

async function apiPatch(url, body) {
  const resp = await fetch(url, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.error || "요청 실패");
  return payload;
}

async function apiDelete(url) {
  const resp = await fetch(url, { method: "DELETE" });
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.error || "요청 실패");
  return payload;
}

async function detectAdmin() {
  isAdmin = false;
}

function todayValue() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const local = new Date(now.getTime() - offset * 60 * 1000);
  return local.toISOString().slice(0, 10);
}

function toDateInputValue(value) {
  const text = String(value || "").trim();
  const match = text.match(/^(\d{4}-\d{2}-\d{2})/);
  return match ? match[1] : "";
}

function normalizeHttpUrlInput(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const parsed = new URL(raw);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    return parsed.href;
  } catch (_err) {
    return null;
  }
}

function ensureSelectOption(selectEl, value, label = null) {
  if (!selectEl) return;
  const key = String(value || "").trim();
  if (!key) return;
  const exists = Array.from(selectEl.options || []).some((option) => String(option.value) === key);
  if (exists) return;
  const option = document.createElement("option");
  option.value = key;
  option.textContent = label || key;
  selectEl.appendChild(option);
}

function adminControlsForCandidate() {
  if (!isAdmin) return "";
  const nameValue = escapeHtml(candidateData?.name || "");
  const birthDateValue = escapeHtml(toDateInputValue(candidateData?.birth_date || ""));
  const currentImageValue = escapeHtml(candidateData?.image || "");
  const hasImage = Boolean(String(candidateData?.image || "").trim());
  return `
    <div class="admin-actions">
      <button type="button" class="admin-btn" data-action="toggle-candidate-edit">정치인 수정</button>
      <button type="button" class="admin-btn danger" data-action="delete-candidate">정치인 삭제</button>
    </div>
    <form class="inline-edit-form" data-form="candidate-edit" hidden>
      <h4>정치인 수정</h4>
      <div class="inline-edit-grid">
        <label>
          이름
          <input name="name" type="text" required value="${nameValue}">
        </label>
        <label>
          생년월일
          <input name="birth_date" type="date" value="${birthDateValue}">
        </label>
      </div>
      <input name="current_image" type="hidden" value="${currentImageValue}">
      <input name="image_mode" type="hidden" value="${hasImage ? "show" : "hide"}">
      <div class="inline-image-toggle" role="group" aria-label="이미지 표시 설정">
        <span class="inline-image-toggle-label">이미지 설정</span>
        <div class="inline-image-toggle-buttons">
          <button type="button" class="admin-btn${hasImage ? " is-selected" : ""}" data-action="candidate-image-show">보이기</button>
          <button type="button" class="admin-btn${hasImage ? "" : " is-selected"}" data-action="candidate-image-hide">숨기기</button>
        </div>
      </div>
      <label class="inline-file-upload${hasImage ? "" : " is-hidden"}">
        이미지 업로드
        <input name="image_file" type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.jfif">
      </label>
      <p class="inline-form-help">보이기 상태에서 파일을 올리면 새 이미지로 교체됩니다.</p>
      <div class="inline-edit-actions">
        <button type="button" class="admin-btn" data-action="cancel-candidate-edit">취소</button>
        <button type="submit" class="admin-btn">저장</button>
      </div>
    </form>
  `;
}

function setCandidateImageMode(formEl, mode) {
  if (!formEl) return;
  const normalized = mode === "hide" ? "hide" : "show";
  const modeInput = formEl.querySelector("input[name='image_mode']");
  if (modeInput) modeInput.value = normalized;

  const showBtn = formEl.querySelector("button[data-action='candidate-image-show']");
  const hideBtn = formEl.querySelector("button[data-action='candidate-image-hide']");
  showBtn?.classList.toggle("is-selected", normalized === "show");
  hideBtn?.classList.toggle("is-selected", normalized === "hide");

  const fileLabel = formEl.querySelector(".inline-file-upload");
  if (fileLabel) {
    fileLabel.classList.toggle("is-hidden", normalized === "hide");
  }
}

function reportControlForCandidate() {
  if (isAdmin) return "";
  return `
    <div class="admin-actions">
      <button type="button" class="report-btn" id="reportCandidateBtn">정치인 신고</button>
    </div>
  `;
}

function renderPledgeStatusOptions(status) {
  const current = String(status || "active").trim() || "active";
  const base = ["active", "hidden", "archived", "draft", "deleted"];
  const options = base
    .map((key) => `<option value="${escapeHtml(key)}"${key === current ? " selected" : ""}>${escapeHtml(key)}</option>`)
    .join("");
  if (base.includes(current)) return options;
  return `<option value="${escapeHtml(current)}" selected>${escapeHtml(current)}</option>${options}`;
}

function adminControlsForPledge(pledge) {
  if (!isAdmin) return "";
  const safeId = escapeHtml(pledge?.id);
  const safeTitle = escapeHtml(pledge?.title || "");
  const safeCategory = escapeHtml(pledge?.category || "");
  const safeRawText = escapeHtml(pledge?.raw_text || "");
  const sortOrderValue = Number.isFinite(Number(pledge?.sort_order)) ? String(Math.floor(Number(pledge.sort_order))) : "";
  const safeSortOrder = escapeHtml(sortOrderValue);
  const safeCandidateElectionId = escapeHtml(pledge?.candidate_election_id || "");
  const statusOptions = renderPledgeStatusOptions(pledge?.status);
  return `
    <div class="admin-actions pledge-admin-actions">
      <button type="button" class="admin-btn" data-action="toggle-pledge-edit" data-id="${safeId}">수정</button>
      <button type="button" class="admin-btn danger" data-action="delete-pledge" data-id="${safeId}">삭제</button>
    </div>
    <form class="inline-edit-form" data-form="pledge-edit" data-id="${safeId}" hidden>
      <h4>공약 수정</h4>
      <input name="pledge_id" type="hidden" value="${safeId}">
      <input name="candidate_election_id" type="hidden" value="${safeCandidateElectionId}">
      <div class="inline-edit-grid triple">
        <label>
          제목
          <input name="title" type="text" required value="${safeTitle}">
        </label>
        <label>
          카테고리
          <input name="category" type="text" required value="${safeCategory}">
        </label>
        <label>
          순서(sort_order)
          <input name="sort_order" type="number" min="1" step="1" required value="${safeSortOrder}">
        </label>
      </div>
      <label>
        상태
        <select name="status">${statusOptions}</select>
      </label>
      <label>
        공약 원문
        <textarea name="raw_text" rows="8" required>${safeRawText}</textarea>
      </label>
      <div class="inline-edit-actions">
        <button type="button" class="admin-btn" data-action="cancel-pledge-edit" data-id="${safeId}">취소</button>
        <button type="submit" class="admin-btn">저장</button>
      </div>
    </form>
  `;
}

function reportControlForPledge(pledgeId) {
  if (isAdmin) return "";
  const safeId = escapeHtml(pledgeId);
  return `
    <div class="admin-actions pledge-admin-actions">
      <button type="button" class="report-btn" data-action="report-pledge" data-id="${safeId}">신고</button>
    </div>
  `;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
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

function toDateLabel(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString("ko-KR");
}

function toSortOrderValue(value, fallback = Number.MAX_SAFE_INTEGER) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

function isExecutionMethodGoal(goalText) {
  const normalized = String(goalText || "").replace(/\s+/g, "");
  return normalized.includes("이행방법");
}

function formatScoreText(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, "");
}

function getScoreTierClass(value) {
  if (value <= 1.5) return "tier-low";
  if (value <= 3) return "tier-mid-low";
  if (value <= 4.5) return "tier-mid-high";
  return "tier-high";
}

function progressStatusLabel(status) {
  const key = String(status || "").trim().toLowerCase();
  const labels = {
    not_started: "미착수",
    in_progress: "진행 중",
    partially_completed: "부분 완료",
    completed: "완료",
    failed: "실패",
    unknown: "미확인",
  };
  return labels[key] || (status ? String(status) : "미확인");
}

function scoreBarMarkup(node) {
  const numeric = Number(node?.progress_rate);
  const status = progressStatusLabel(node?.progress_status);
  const evaluator = String(node?.progress_evaluator || "").trim();
  const evaluationDate = toDateLabel(node?.progress_evaluation_date);
  const tooltipParts = [];
  if (status && status !== "미확인") tooltipParts.push(`상태 ${status}`);
  if (evaluator) tooltipParts.push(`평가 ${evaluator}`);
  if (evaluationDate && evaluationDate !== "-") tooltipParts.push(`기준일 ${evaluationDate}`);

  if (!Number.isFinite(numeric)) {
    const tooltip = tooltipParts.length ? `이행률 평가 기록 없음 · ${tooltipParts.join(" · ")}` : "이행률 평가 기록 없음";
    return {
      html: `
        <span class="score-bar" title="${escapeHtml(tooltip)}" aria-label="${escapeHtml(tooltip)}">
          <span class="score-bar-fill pending" style="width:100%;"></span>
        </span>
      `,
      numeric: null,
      tooltip,
    };
  }

  const clamped = Math.max(0, Math.min(5, numeric));
  const percent = (clamped / 5) * 100;
  const text = formatScoreText(clamped);
  tooltipParts.unshift(`이행률 ${text}`);
  const tooltip = tooltipParts.join(" · ");
  const tierClass = getScoreTierClass(clamped);

  return {
    html: `
      <span class="score-bar" title="${escapeHtml(tooltip)}" aria-label="${escapeHtml(tooltip)}">
        <span class="score-bar-fill ${tierClass}" style="width:${percent}%;"></span>
      </span>
    `,
    numeric: clamped,
    tooltip,
  };
}

function renderScoreBadge(node, meta = {}) {
  const bar = scoreBarMarkup(node);
  if (!node?.id) return `<span class="score-readonly">${bar.html}<span class="score-input-label">평가 없음</span></span>`;
  const actionLabel = Number.isFinite(bar.numeric) ? "평가 수정" : "평가 입력";
  const nodePath = String(meta?.nodePath || node?.text || "").trim();
  const latestHistory = Array.isArray(node?.progress_history) && node.progress_history.length ? (node.progress_history[0] || {}) : {};
  const latestSourceLink = Array.isArray(node?.progress_sources) && node.progress_sources.length ? (node.progress_sources[0] || {}) : {};
  const latestSource = latestSourceLink?.source || {};
  const currentRate = Number.isFinite(bar.numeric) ? formatScoreText(bar.numeric) : "";

  return `
    <button
      type="button"
      class="score-input-trigger"
      data-action="open-progress-editor"
      data-node-id="${escapeHtml(node.id)}"
      data-node-path="${escapeHtml(nodePath)}"
      data-progress-id="${escapeHtml(latestHistory?.id || "")}"
      data-current-rate="${escapeHtml(currentRate)}"
      data-current-status="${escapeHtml(node?.progress_status || "unknown")}"
      data-current-evaluator="${escapeHtml(node?.progress_evaluator || "")}"
      data-current-date="${escapeHtml(node?.progress_evaluation_date || "")}"
      data-current-reason="${escapeHtml(node?.progress_reason || "")}"
      data-current-source-id="${escapeHtml(latestSourceLink?.source_id || "")}"
      data-current-source-title="${escapeHtml(latestSource?.title || "")}"
      data-current-source-url="${escapeHtml(latestSource?.url || "")}"
      data-current-source-type="${escapeHtml(latestSource?.source_type || "")}"
      data-current-source-publisher="${escapeHtml(latestSource?.publisher || "")}"
      data-current-source-date="${escapeHtml(latestSource?.published_at || "")}"
      data-current-source-summary="${escapeHtml(latestSource?.summary || "")}"
      data-current-source-role="${escapeHtml(latestSourceLink?.source_role || "primary")}"
      data-current-page-no="${escapeHtml(latestSourceLink?.page_no || "")}"
      data-current-quoted-text="${escapeHtml(latestSourceLink?.quoted_text || "")}"
      data-current-link-note="${escapeHtml(latestSourceLink?.note || "")}"
      title="클릭해서 ${escapeHtml(actionLabel)}"
    >
      ${bar.html}
      <span class="score-input-label">${escapeHtml(actionLabel)}</span>
    </button>
  `;
}

function renderPledgeTree(pledge) {
  const goals = Array.isArray(pledge?.goals) ? pledge.goals : [];

  if (!goals.length) {
    const fallback = (pledge?.raw_text || "").trim();
    return fallback
      ? `<p class="promise-summary">${escapeHtml(fallback)}</p>`
      : '<p class="empty">세부 공약이 등록되지 않았습니다.</p>';
  }

  return `
    <div class="pledge-tree">
      ${goals
        .map((goal) => {
          const goalText = String(goal?.text || "").trim();
          const promises = Array.isArray(goal?.promises) ? goal.promises : [];
          const showExecutionScore = isExecutionMethodGoal(goalText);
          return `
            <section class="goal-block">
              <h4 class="goal-title">${escapeHtml(goalText)}</h4>
              ${promises.length
                ? promises
                    .map((promise) => {
                      const promiseText = String(promise?.text || "").trim();
                      const items = Array.isArray(promise?.items) ? promise.items : [];
                      const promisePath = [goalText, promiseText].filter(Boolean).join(" > ");
                      const promiseScoreBadge = showExecutionScore && !items.length
                        ? renderScoreBadge(promise, { nodePath: promisePath })
                        : "";
                      return `
                        <div class="promise-block">
                          <p class="promise-line">
                            <span>${escapeHtml(promiseText)}</span>
                            ${promiseScoreBadge}
                          </p>
                          ${items.length
                            ? `<ul class="item-list">${items
                                .map((item) => {
                                  const itemText = String(item?.text || "").trim();
                                  const itemPath = [goalText, promiseText, itemText].filter(Boolean).join(" > ");
                                  const itemScoreBadge = showExecutionScore
                                    ? renderScoreBadge(item, { nodePath: itemPath })
                                    : "";
                                  return `<li><span>${escapeHtml(itemText)}</span>${itemScoreBadge}</li>`;
                                })
                                .join("")}</ul>`
                            : ""}
                        </div>
                      `;
                    })
                    .join("")
                : '<p class="empty">세부 약속이 없습니다.</p>'}
            </section>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderPledgeCard(pledge) {
  const createdAt = toDateLabel(pledge?.created_at);
  const sortOrder = toSortOrderValue(pledge?.sort_order, 0);
  const sortLabel = sortOrder > 0 ? `#${sortOrder}` : "#-";
  return `
    <details class="pledge-section">
      <summary class="pledge-summary">
        <span class="pledge-summary-title">${escapeHtml(sortLabel)} ${escapeHtml(pledge?.title || "제목 없음")}</span>
        <span class="pledge-summary-info">${escapeHtml(pledge?.category || "미분류")}</span>
      </summary>
      <div class="pledge-section-body">
        <article class="promise-card no-avatar">
          <div class="promise-content">
            <h3 class="promise-name">${escapeHtml(sortLabel)} ${escapeHtml(pledge?.title || "제목 없음")}</h3>
            <div class="promise-meta">
              <span class="category">${escapeHtml(pledge?.category || "미분류")}</span>
              <span class="status">${escapeHtml(pledge?.status || "active")}</span>
              <small>${createdAt} 생성</small>
            </div>
            ${renderPledgeTree(pledge)}
            ${adminControlsForPledge(pledge)}
            ${reportControlForPledge(pledge?.id)}
          </div>
        </article>
      </div>
    </details>
  `;
}

function renderElectionSection(section, index) {
  const election = section?.election || {};
  const electionTitle = election?.title || "선거 정보 없음";
  const electionDate = toDateLabel(election?.election_date);
  const electionType = election?.election_type || "선거";
  const party = section?.party || "-";
  const result = section?.result || "-";
  const candidateNumber = section?.candidate_number ?? "-";
  const pledges = (Array.isArray(section?.pledges) ? section.pledges : []).slice().sort((a, b) => {
    const bySort = toSortOrderValue(a?.sort_order) - toSortOrderValue(b?.sort_order);
    if (bySort !== 0) return bySort;
    return String(a?.created_at || "").localeCompare(String(b?.created_at || ""));
  });
  const isOpen = index === 0 ? " open" : "";

  return `
    <details class="election-section"${isOpen}>
      <summary class="election-summary">
        <div class="election-summary-main">
          <h4>${escapeHtml(electionTitle)}</h4>
          <p>${escapeHtml(electionType)} · ${escapeHtml(electionDate)}</p>
        </div>
        <div class="election-summary-meta">
          <span>${escapeHtml(party)}</span>
          <span>${escapeHtml(result)}</span>
          <span>기호 ${escapeHtml(candidateNumber)}</span>
          <strong>${pledges.length}개 공약</strong>
        </div>
      </summary>
      <div class="election-section-body">
        ${pledges.length ? pledges.map((pledge) => renderPledgeCard(pledge)).join("") : '<p class="empty">이 선거에 등록된 공약이 없습니다.</p>'}
      </div>
    </details>
  `;
}

function renderDetail() {
  const profileEl = document.getElementById("politicianProfile");
  const listEl = document.getElementById("politicianPledgeList");
  const countEl = document.getElementById("politicianPledgeCount");
  const adminBadge = document.getElementById("adminBadge");
  if (!profileEl || !listEl || !countEl) return;

  if (adminBadge) adminBadge.hidden = !isAdmin;
  const safeProfileImage = sanitizeUrl(candidateData?.image);
  const birthDateLabel = toDateLabel(candidateData?.birth_date);

  profileEl.innerHTML = `
    <div class="politician-profile-head">
      ${safeProfileImage ? `<img src="${safeProfileImage}" alt="${escapeHtml(candidateData?.name || "정치인")}">` : '<div class="profile-empty-image">이미지 없음</div>'}
      <div>
        <h3>${escapeHtml(candidateData?.name || "-")}</h3>
        <p>${escapeHtml(candidateData?.position || "-")} · ${escapeHtml(candidateData?.party || "-")}</p>
      </div>
    </div>
    <div class="politician-profile-meta">
      <span><strong>${escapeHtml(birthDateLabel)}</strong> 생년월일</span>
      <span><strong>${escapeHtml(candidateData?.election_year || "-")}</strong> 최근 선거연도</span>
      <span><strong>${escapeHtml(candidateData?.party || "-")}</strong> 최근 정당</span>
      <span><strong>${escapeHtml(candidateData?.position || "-")}</strong> 최근 직책</span>
    </div>
    ${adminControlsForCandidate()}
    ${reportControlForCandidate()}
  `;

  countEl.textContent = `${pledgeData.length}건`;
  if (!electionSections.length) {
    listEl.innerHTML = '<p class="empty">출마 선거 정보가 없습니다.</p>';
    return;
  }

  listEl.innerHTML = `<div class="election-sections">${electionSections
    .map((section, index) => renderElectionSection(section, index))
    .join("")}</div>`;
}

async function reloadData() {
  const candidateId = resolveCandidateId();
  if (!candidateId) {
    throw new Error("정치인 ID가 올바르지 않습니다. 목록에서 다시 선택해 주세요.");
  }
  const payload = await apiGet(`/api/politicians/${encodeURIComponent(candidateId)}`);
  candidateData = payload.candidate || null;
  pledgeData = payload.pledges || [];
  electionSections = payload.election_sections || [];
  pledgeById = new Map(pledgeData.map((row) => [String(row.id), row]));

  if (!electionSections.length && pledgeData.length) {
    electionSections = [
      {
        candidate_election_id: "unknown",
        election: {
          title: "미분류 선거",
          election_type: "기타",
          election_date: null,
        },
        party: null,
        result: null,
        candidate_number: null,
        pledges: pledgeData,
      },
    ];
  }

  if (typeof payload.is_admin === "boolean") {
    isAdmin = payload.is_admin;
  }

  if (!candidateData) {
    throw new Error("해당 정치인을 찾을 수 없습니다.");
  }
}

function setProgressEditorOpen(open) {
  if (!progressEditorModalEl) return;
  progressEditorModalEl.hidden = !open;
  document.body.style.overflow = open ? "hidden" : "";
}

function resetProgressEditorForm() {
  progressEditorForm?.reset();
  if (progressEditorNodeIdInput) progressEditorNodeIdInput.value = "";
  if (progressEditorSourceIdInput) progressEditorSourceIdInput.value = "";
  if (progressEditorRateInput) progressEditorRateInput.value = "0";
  if (progressEditorStatusInput) progressEditorStatusInput.value = "unknown";
  if (progressEditorDateInput) progressEditorDateInput.value = todayValue();
  if (progressEditorSourceRoleInput) progressEditorSourceRoleInput.value = "primary";
  if (progressEditorNodePathEl) progressEditorNodePathEl.textContent = "평가 대상을 선택해 주세요.";
}

function closeProgressEditor() {
  setProgressEditorOpen(false);
}

async function openProgressEditorFromButton(button) {
  if (!progressEditorModalEl || !progressEditorForm) {
    setMessage("이행률 입력 폼을 초기화하지 못했습니다.", "error");
    return;
  }
  if (!isLoggedIn) {
    await syncLoginState();
  }
  if (!isLoggedIn) {
    setMessage("로그인 후 이행률 평가를 입력할 수 있습니다.", "error");
    return;
  }

  const nodeId = String(button.getAttribute("data-node-id") || "").trim();
  if (!nodeId) {
    setMessage("평가 대상 정보를 찾지 못했습니다.", "error");
    return;
  }

  resetProgressEditorForm();

  const nodePath = String(button.getAttribute("data-node-path") || "").trim();
  const currentRate = String(button.getAttribute("data-current-rate") || "").trim();
  const currentStatus = String(button.getAttribute("data-current-status") || "").trim();
  const currentEvaluator = String(button.getAttribute("data-current-evaluator") || "").trim();
  const currentDate = String(button.getAttribute("data-current-date") || "").trim();
  const currentReason = String(button.getAttribute("data-current-reason") || "").trim();
  const currentSourceId = String(button.getAttribute("data-current-source-id") || "").trim();
  const currentSourceTitle = String(button.getAttribute("data-current-source-title") || "").trim();
  const currentSourceUrl = String(button.getAttribute("data-current-source-url") || "").trim();
  const currentSourceType = String(button.getAttribute("data-current-source-type") || "").trim();
  const currentSourcePublisher = String(button.getAttribute("data-current-source-publisher") || "").trim();
  const currentSourceDate = String(button.getAttribute("data-current-source-date") || "").trim();
  const currentSourceSummary = String(button.getAttribute("data-current-source-summary") || "").trim();
  const currentSourceRole = String(button.getAttribute("data-current-source-role") || "").trim();
  const currentPageNo = String(button.getAttribute("data-current-page-no") || "").trim();
  const currentQuotedText = String(button.getAttribute("data-current-quoted-text") || "").trim();
  const currentLinkNote = String(button.getAttribute("data-current-link-note") || "").trim();

  if (progressEditorNodeIdInput) progressEditorNodeIdInput.value = nodeId;
  if (progressEditorNodePathEl) progressEditorNodePathEl.textContent = nodePath || "선택된 항목";
  if (progressEditorRateInput && currentRate) {
    ensureSelectOption(progressEditorRateInput, currentRate, `${currentRate} (기존값)`);
    progressEditorRateInput.value = currentRate;
  }
  if (progressEditorStatusInput && currentStatus) {
    ensureSelectOption(progressEditorStatusInput, currentStatus, currentStatus);
    progressEditorStatusInput.value = currentStatus;
  }
  if (progressEditorEvaluatorInput) progressEditorEvaluatorInput.value = currentEvaluator;
  if (progressEditorDateInput) progressEditorDateInput.value = toDateInputValue(currentDate) || todayValue();
  if (progressEditorReasonInput) progressEditorReasonInput.value = currentReason;
  if (progressEditorSourceIdInput) progressEditorSourceIdInput.value = currentSourceId;
  if (progressEditorSourceTitleInput) progressEditorSourceTitleInput.value = currentSourceTitle;
  if (progressEditorSourceUrlInput) progressEditorSourceUrlInput.value = currentSourceUrl;
  if (progressEditorSourceTypeInput && currentSourceType) {
    ensureSelectOption(progressEditorSourceTypeInput, currentSourceType, currentSourceType);
    progressEditorSourceTypeInput.value = currentSourceType;
  }
  if (progressEditorSourcePublisherInput) progressEditorSourcePublisherInput.value = currentSourcePublisher;
  if (progressEditorSourceDateInput) progressEditorSourceDateInput.value = toDateInputValue(currentSourceDate);
  if (progressEditorSourceSummaryInput) progressEditorSourceSummaryInput.value = currentSourceSummary;
  if (progressEditorSourceRoleInput && currentSourceRole) {
    ensureSelectOption(progressEditorSourceRoleInput, currentSourceRole, currentSourceRole);
    progressEditorSourceRoleInput.value = currentSourceRole;
  }
  if (progressEditorPageNoInput) progressEditorPageNoInput.value = currentPageNo;
  if (progressEditorQuoteInput) progressEditorQuoteInput.value = currentQuotedText;
  if (progressEditorLinkNoteInput) progressEditorLinkNoteInput.value = currentLinkNote;

  setProgressEditorOpen(true);
}

async function submitProgressEditorForm(event) {
  event.preventDefault();
  if (!isLoggedIn) {
    await syncLoginState();
  }
  if (!isLoggedIn) throw new Error("로그인 후 이행률 평가를 입력할 수 있습니다.");

  const pledgeNodeId = String(progressEditorNodeIdInput?.value || "").trim();
  if (!pledgeNodeId) throw new Error("평가 대상이 없습니다.");

  const progressRateRaw = String(progressEditorRateInput?.value || "").trim();
  const progressRate = Number(progressRateRaw);
  if (!Number.isFinite(progressRate) || progressRate < 0 || progressRate > 5) {
    throw new Error("이행 점수는 0~5 범위여야 합니다.");
  }
  const scaled = progressRate * 2;
  if (Math.abs(Math.round(scaled) - scaled) > 1e-9) {
    throw new Error("이행 점수는 0.5 단위여야 합니다.");
  }

  const status = String(progressEditorStatusInput?.value || "").trim();
  if (!status) throw new Error("상태를 선택해 주세요.");

  const evaluationDate = String(progressEditorDateInput?.value || "").trim();
  if (!evaluationDate) throw new Error("평가 기준일을 입력해 주세요.");

  const sourceUrlRaw = String(progressEditorSourceUrlInput?.value || "").trim();
  const sourceUrl = normalizeHttpUrlInput(sourceUrlRaw);
  if (sourceUrlRaw && !sourceUrl) {
    throw new Error("출처 URL 형식을 확인해 주세요. http(s) 주소만 저장할 수 있습니다.");
  }

  const restoreButton = setActionButtonBusy(progressEditorSaveBtn, "저장 중...");
  setMessage("이행률 평가를 저장 중입니다...", "info");
  try {
    const result = await apiPost("/api/progress-admin/record", {
      pledge_node_id: pledgeNodeId,
      progress_rate: progressRate,
      status,
      evaluator: String(progressEditorEvaluatorInput?.value || "").trim(),
      evaluation_date: evaluationDate,
      reason: String(progressEditorReasonInput?.value || "").trim(),
      source_id: String(progressEditorSourceIdInput?.value || "").trim(),
      source_title: String(progressEditorSourceTitleInput?.value || "").trim(),
      source_url: sourceUrl || "",
      source_type: String(progressEditorSourceTypeInput?.value || "").trim(),
      source_publisher: String(progressEditorSourcePublisherInput?.value || "").trim(),
      source_published_at: String(progressEditorSourceDateInput?.value || "").trim(),
      source_summary: String(progressEditorSourceSummaryInput?.value || "").trim(),
      source_role: String(progressEditorSourceRoleInput?.value || "").trim() || "primary",
      quoted_text: String(progressEditorQuoteInput?.value || "").trim(),
      page_no: String(progressEditorPageNoInput?.value || "").trim(),
      note: String(progressEditorLinkNoteInput?.value || "").trim(),
    });

    closeProgressEditor();
    await reloadData();
    renderDetail();
    if (result?.warning) {
      setMessage("이행률은 저장되었습니다. (출처 연결 중 일부 항목은 건너뛰었습니다.)", "success");
    } else {
      setMessage("이행률 평가를 저장했습니다.", "success");
    }
  } finally {
    restoreButton();
  }
}

function bindProgressEditorEvents() {
  progressEditorForm?.addEventListener("submit", async (event) => {
    try {
      await submitProgressEditorForm(event);
    } catch (error) {
      setMessage(error.message || "이행률 저장 중 오류가 발생했습니다.", "error");
    }
  });

  progressEditorModalEl?.addEventListener("click", (event) => {
    const closeBtn = event.target.closest("[data-action='close-progress-editor']");
    if (!closeBtn) return;
    closeProgressEditor();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!progressEditorModalEl || progressEditorModalEl.hidden) return;
    closeProgressEditor();
  });
}

async function reportCandidate() {
  const reason = prompt("신고 사유를 입력해 주세요.", "부적합한 내용");
  if (reason === null) return;
  if (!reason.trim()) throw new Error("신고 사유를 입력해 주세요.");
  await apiPost("/api/report", {
    candidate_id: candidateData.id,
    reason: reason.trim(),
    report_type: "신고",
    reason_category: "콘텐츠 신고",
    target_url: window.location.href,
  });
  window.location.href = "/politicians";
}

async function reportPledge(pledgeId) {
  const reason = prompt("신고 사유를 입력해 주세요.", "부적합한 내용");
  if (reason === null) return;
  if (!reason.trim()) throw new Error("신고 사유를 입력해 주세요.");
  await apiPost("/api/report", {
    pledge_id: pledgeId,
    reason: reason.trim(),
    report_type: "신고",
    reason_category: "콘텐츠 신고",
    target_url: window.location.href,
  });
  await reloadData();
  renderDetail();
}

async function submitCandidateEditForm(formEl, submitButton = null) {
  const name = String(formEl?.elements?.name?.value || "").trim();
  if (!name) throw new Error("이름을 입력해 주세요.");

  const birthDateRaw = String(formEl?.elements?.birth_date?.value || "").trim();
  const birthDate = toDateInputValue(birthDateRaw);
  if (birthDateRaw && !birthDate) {
    throw new Error("생년월일 형식을 확인해 주세요. (YYYY-MM-DD)");
  }

  const imageMode = String(formEl?.elements?.image_mode?.value || "show").trim() === "hide" ? "hide" : "show";
  const currentImage = String(formEl?.elements?.current_image?.value || "").trim();
  const imageFileInput = formEl?.elements?.image_file;
  const restoreButton = setActionButtonBusy(submitButton, "저장 중...");
  try {
    let image = currentImage || null;
    if (imageMode === "hide") {
      image = null;
    } else if (imageFileInput && imageFileInput.files && imageFileInput.files.length > 0) {
      image = await uploadImage(imageFileInput.files[0]);
    }

    await apiPatch(`/api/admin/candidates/${encodeURIComponent(candidateData.id)}`, {
      name,
      image,
      birth_date: birthDate || null,
    });
  } finally {
    restoreButton();
  }
}

async function deleteCandidate(actionButton = null) {
  if (!confirm("정말 이 정치인을 삭제할까요?")) return;
  const restoreButton = setActionButtonBusy(actionButton, "삭제 진행중...");
  setMessage("정치인 삭제를 진행 중입니다...", "info");
  try {
    await apiDelete(`/api/admin/candidates/${encodeURIComponent(candidateData.id)}`);
    window.location.href = "/politicians";
  } finally {
    restoreButton();
  }
}

async function submitPledgeEditForm(formEl, submitButton = null) {
  const pledgeId = String(formEl?.elements?.pledge_id?.value || "").trim();
  if (!pledgeId) throw new Error("공약 식별자를 찾지 못했습니다.");
  const candidateElectionId = String(formEl?.elements?.candidate_election_id?.value || "").trim();
  if (!candidateElectionId) throw new Error("후보자-선거 매칭 정보가 없습니다.");

  const title = String(formEl?.elements?.title?.value || "").trim();
  const rawText = String(formEl?.elements?.raw_text?.value || "").trim();
  const category = String(formEl?.elements?.category?.value || "").trim();
  const status = String(formEl?.elements?.status?.value || "").trim() || "active";
  const sortOrderRaw = String(formEl?.elements?.sort_order?.value || "").trim();
  const parsedSortOrder = Number(sortOrderRaw);

  if (!title || !rawText || !category) throw new Error("입력값을 확인해 주세요.");
  if (!Number.isFinite(parsedSortOrder) || parsedSortOrder < 1) {
    throw new Error("공약 순서는 1 이상의 숫자여야 합니다.");
  }

  const restoreButton = setActionButtonBusy(submitButton, "저장 중...");
  try {
    await apiPatch(`/api/admin/pledges/${encodeURIComponent(pledgeId)}`, {
      candidate_election_id: candidateElectionId,
      sort_order: Math.floor(parsedSortOrder),
      title,
      raw_text: rawText,
      category,
      status,
    });
  } finally {
    restoreButton();
  }
}

async function deletePledge(pledgeId, actionButton = null) {
  if (!confirm("정말 이 공약을 삭제할까요?")) return;
  const restoreButton = setActionButtonBusy(actionButton, "삭제 진행중...");
  setMessage("공약 삭제를 진행 중입니다...", "info");
  try {
    await apiDelete(`/api/admin/pledges/${encodeURIComponent(pledgeId)}`);
  } finally {
    restoreButton();
  }
}

function bindActions() {
  const profileEl = document.getElementById("politicianProfile");
  const listEl = document.getElementById("politicianPledgeList");

  profileEl?.addEventListener("click", async (event) => {
    try {
      if (event.target.closest("#reportCandidateBtn")) {
        await reportCandidate();
        return;
      }
      if (!isAdmin) return;
      const actionBtn = event.target.closest("button[data-action]");
      if (!actionBtn) return;
      const action = String(actionBtn.getAttribute("data-action") || "").trim();
      const formEl = profileEl.querySelector("form[data-form='candidate-edit']");

      if (action === "toggle-candidate-edit") {
        if (!formEl) return;
        formEl.hidden = !formEl.hidden;
        if (!formEl.hidden) {
          const defaultMode = String(formEl?.elements?.image_mode?.value || "show").trim();
          setCandidateImageMode(formEl, defaultMode === "hide" ? "hide" : "show");
          const nameInput = formEl.querySelector("input[name='name']");
          nameInput?.focus();
        }
        return;
      }
      if (action === "candidate-image-show") {
        setCandidateImageMode(formEl, "show");
        return;
      }
      if (action === "candidate-image-hide") {
        setCandidateImageMode(formEl, "hide");
        return;
      }
      if (action === "cancel-candidate-edit") {
        if (formEl) formEl.hidden = true;
        return;
      }
      if (action === "delete-candidate") {
        await deleteCandidate(actionBtn);
      }
    } catch (error) {
      setMessage(error.message || "작업 실패", "error");
    }
  });

  profileEl?.addEventListener("submit", async (event) => {
    const formEl = event.target.closest("form[data-form='candidate-edit']");
    if (!formEl) return;
    event.preventDefault();
    try {
      const submitBtn = formEl.querySelector("button[type='submit']");
      await submitCandidateEditForm(formEl, submitBtn);
      await reloadData();
      renderDetail();
      setMessage("정치인 정보를 수정했습니다.", "success");
    } catch (error) {
      setMessage(error.message || "정치인 수정 실패", "error");
    }
  });

  listEl?.addEventListener("click", async (event) => {
    const btn = event.target.closest("button[data-action]");
    if (!btn) return;
    const action = btn.getAttribute("data-action");

    try {
      if (action === "open-progress-editor") {
        await openProgressEditorFromButton(btn);
        return;
      }

      const id = btn.getAttribute("data-id");
      if (!id) return;

      if (action === "report-pledge") {
        await reportPledge(id);
        setMessage("신고가 접수되었고 숨김 처리되었습니다.", "success");
        return;
      }
      if (!isAdmin) return;
      if (action === "toggle-pledge-edit") {
        const card = btn.closest(".promise-content");
        if (!card) return;
        const formEl = card.querySelector(`form[data-form='pledge-edit'][data-id="${String(id)}"]`) || card.querySelector("form[data-form='pledge-edit']");
        if (!formEl) return;
        formEl.hidden = !formEl.hidden;
        if (!formEl.hidden) {
          const titleInput = formEl.querySelector("input[name='title']");
          titleInput?.focus();
        }
      } else if (action === "cancel-pledge-edit") {
        const card = btn.closest(".promise-content");
        if (!card) return;
        const formEl = card.querySelector(`form[data-form='pledge-edit'][data-id="${String(id)}"]`) || card.querySelector("form[data-form='pledge-edit']");
        if (formEl) formEl.hidden = true;
      } else if (action === "delete-pledge") {
        await deletePledge(id, btn);
        await reloadData();
        renderDetail();
        setMessage("공약을 삭제했습니다.", "success");
      }
    } catch (error) {
      setMessage(error.message || "작업 실패", "error");
    }
  });

  listEl?.addEventListener("submit", async (event) => {
    const formEl = event.target.closest("form[data-form='pledge-edit']");
    if (!formEl) return;
    event.preventDefault();
    try {
      const submitBtn = formEl.querySelector("button[type='submit']");
      await submitPledgeEditForm(formEl, submitBtn);
      await reloadData();
      renderDetail();
      setMessage("공약을 수정했습니다.", "success");
    } catch (error) {
      setMessage(error.message || "공약 수정 실패", "error");
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  if (!window.location.pathname.startsWith("/politicians/")) return;
  bindActions();
  bindProgressEditorEvents();
  resetProgressEditorForm();
  setDetailLoadingState(true);
  setMessage("정치인 정보를 불러오는 중입니다...", "info");
  syncLoginState()
    .then(detectAdmin)
    .then(reloadData)
    .then(() => {
      renderDetail();
      setDetailLoadingState(false);
      const suffix = isLoggedIn
        ? " 각 항목 오른쪽 버튼으로 이행률을 새 구조로 입력할 수 있습니다."
        : " 이행률 입력은 로그인 후 가능합니다.";
      setMessage((isAdmin ? "정치인 상세페이지를 불러왔습니다. (관리자 모드)" : "정치인 상세페이지를 불러왔습니다.") + suffix, "success");
    })
    .catch((error) => {
      setDetailLoadingState(false, false);
      setMessage(error.message || "정치인 상세페이지 로딩 실패", "error");
    });
});
