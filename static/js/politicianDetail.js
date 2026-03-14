let isAdmin = false;
let candidateData = null;
let pledgeData = [];
let electionSections = [];
let pledgeById = new Map();
const isLoggedIn = Boolean(window.APP_CONTEXT?.userId);

const progressModalEl = document.getElementById("progressEditModal");
const progressNodePathEl = document.getElementById("progressEditNodePath");
const progressQuickForm = document.getElementById("progressQuickForm");
const progressEditNodeIdInput = document.getElementById("progressEditNodeId");
const progressEditRateInput = document.getElementById("progressEditRate");
const progressEditRateGuideEl = document.getElementById("progressEditRateGuide");
const progressEditStatusInput = document.getElementById("progressEditStatus");
const progressEditEvaluatorInput = document.getElementById("progressEditEvaluator");
const progressEditDateInput = document.getElementById("progressEditDate");
const progressEditReasonInput = document.getElementById("progressEditReason");
const progressEditSourceTitleInput = document.getElementById("progressEditSourceTitle");
const progressEditSourceUrlInput = document.getElementById("progressEditSourceUrl");
const progressEditSourceTypeInput = document.getElementById("progressEditSourceType");
const progressEditSourceDateInput = document.getElementById("progressEditSourceDate");
const progressEditSourcePublisherInput = document.getElementById("progressEditSourcePublisher");
const progressEditSourceSummaryInput = document.getElementById("progressEditSourceSummary");
const progressEditSourceRoleInput = document.getElementById("progressEditSourceRole");
const progressEditPageNoInput = document.getElementById("progressEditPageNo");
const progressEditQuoteInput = document.getElementById("progressEditQuote");
const progressEditNoteInput = document.getElementById("progressEditNote");
const progressQuickSaveBtn = document.getElementById("progressQuickSaveBtn");
const progressTargetHintEl = document.getElementById("progressTargetHint");
const openFirstProgressBtn = document.getElementById("openFirstProgressBtn");
const detailLoadingEl = document.getElementById("politicianDetailLoading");
const detailGuideCardEl = document.getElementById("detailGuideCard");
const detailPanelEl = document.getElementById("politicianDetailPanel");

const SCORE_CRITERIA = {
  "5": "공약이 이미 완료된 사업",
  "4.5": "재임기간을 조금 넘겨 완료가 확실시되는 사업",
  "4": "예산/일정이 확정되어 진행 중인 사업",
  "3.5": "일부만 완료되었거나 축소·변경된 사업",
  "3": "예산/일정은 있으나 계획이 축소·변경된 사업",
  "2.5": "예비타당성 조사 등 준비단계 사업",
  "2": "논의·협의 중심으로 진행된 사업",
  "1.5": "계획만 있고 추진이 거의 없는 사업",
  "1": "간접 참여 수준 또는 상징적 진행",
  "0": "착수되지 않았거나 평가 불가능한 사업",
};

function setMessage(text, type = "info") {
  const el = document.getElementById("browseMessage");
  if (!el) return;
  el.className = `browse-message ${type}`;
  el.textContent = text;
}

function setDetailLoadingState(isLoading, showContentWhenDone = true) {
  if (detailLoadingEl) detailLoadingEl.hidden = !isLoading;
  const shouldShowContent = !isLoading && showContentWhenDone;
  if (detailGuideCardEl) detailGuideCardEl.hidden = !shouldShowContent;
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

async function apiGet(url) {
  const resp = await fetch(url);
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.error || "요청 실패");
  return payload;
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

function adminControlsForCandidate() {
  if (!isAdmin) return "";
  return `
    <div class="admin-actions">
      <button type="button" class="admin-btn" id="editCandidateBtn">정치인 수정</button>
      <button type="button" class="admin-btn danger" id="deleteCandidateBtn">정치인 삭제</button>
    </div>
  `;
}

function reportControlForCandidate() {
  if (isAdmin) return "";
  return `
    <div class="admin-actions">
      <button type="button" class="report-btn" id="reportCandidateBtn">정치인 신고</button>
    </div>
  `;
}

function adminControlsForPledge(pledgeId) {
  if (!isAdmin) return "";
  return `
    <div class="admin-actions pledge-admin-actions">
      <button type="button" class="admin-btn" data-action="edit-pledge" data-id="${pledgeId}">수정</button>
      <button type="button" class="admin-btn danger" data-action="delete-pledge" data-id="${pledgeId}">삭제</button>
    </div>
  `;
}

function reportControlForPledge(pledgeId) {
  if (isAdmin) return "";
  return `
    <div class="admin-actions pledge-admin-actions">
      <button type="button" class="report-btn" data-action="report-pledge" data-id="${pledgeId}">신고</button>
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

function scoreCriteriaText(value) {
  const key = formatScoreText(value);
  return SCORE_CRITERIA[key] || "평가기준 설명 없음";
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
  if (!node?.id) return bar.html;
  const actionLabel = Number.isFinite(bar.numeric) ? "이행률 수정" : "이행률 입력";

  const nodePath = String(meta?.nodePath || node?.text || "").trim();
  const currentRate = Number.isFinite(bar.numeric) ? String(bar.numeric) : "";
  const currentStatus = String(node?.progress_status || "unknown");
  const currentEvaluator = String(node?.progress_evaluator || "");
  const currentDate = String(node?.progress_evaluation_date || "");
  const currentReason = String(node?.progress_reason || "");

  return `
    <button
      type="button"
      class="score-input-trigger"
      data-action="open-progress-modal"
      data-node-id="${escapeHtml(node.id)}"
      data-node-path="${escapeHtml(nodePath)}"
      data-current-rate="${escapeHtml(currentRate)}"
      data-current-status="${escapeHtml(currentStatus)}"
      data-current-evaluator="${escapeHtml(currentEvaluator)}"
      data-current-date="${escapeHtml(currentDate)}"
      data-current-reason="${escapeHtml(currentReason)}"
      aria-label="${escapeHtml(actionLabel)}"
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
            ${adminControlsForPledge(pledge?.id)}
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

  profileEl.innerHTML = `
    <div class="politician-profile-head">
      ${candidateData?.image ? `<img src="${candidateData.image}" alt="${escapeHtml(candidateData.name || "정치인")}">` : '<div class="profile-empty-image">이미지 없음</div>'}
      <div>
        <h3>${escapeHtml(candidateData?.name || "-")}</h3>
        <p>${escapeHtml(candidateData?.position || "-")} · ${escapeHtml(candidateData?.party || "-")}</p>
      </div>
    </div>
    <div class="politician-profile-meta">
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
    updateProgressGuideState(0);
    return;
  }

  listEl.innerHTML = `<div class="election-sections">${electionSections
    .map((section, index) => renderElectionSection(section, index))
    .join("")}</div>`;

  const progressButtonCount = listEl.querySelectorAll("button[data-action='open-progress-modal']").length;
  updateProgressGuideState(progressButtonCount);
}

function updateProgressGuideState(progressButtonCount) {
  const count = Number(progressButtonCount) || 0;
  if (progressTargetHintEl) {
    const loginHint = isLoggedIn
      ? "버튼을 누르면 바로 저장 가능한 평가 입력창이 열립니다."
      : "버튼을 누르면 평가 입력창을 볼 수 있고 저장은 로그인 후 가능합니다.";
    progressTargetHintEl.textContent = count > 0
      ? `현재 평가 가능한 항목 ${count}개 · ${loginHint}`
      : "현재 평가 가능한 항목이 없습니다. 공약 구조(실행 방법)를 확인해 주세요.";
  }
  if (openFirstProgressBtn) {
    openFirstProgressBtn.disabled = count < 1;
    openFirstProgressBtn.textContent = count > 0 ? "첫 평가 입력하기" : "평가 대상 없음";
  }
}

function openFirstProgressModal() {
  const firstBtn = document.querySelector("#politicianPledgeList button[data-action='open-progress-modal']");
  if (!firstBtn) {
    setMessage("현재 평가 가능한 항목이 없습니다.", "info");
    return;
  }
  firstBtn.scrollIntoView({ behavior: "smooth", block: "center" });
  openProgressModalFromButton(firstBtn);
}

async function reloadData() {
  const candidateId = window.POLITICIAN_DETAIL_ID;
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

function ensureProgressRateOption(value) {
  if (!progressEditRateInput) return;
  const key = formatScoreText(value);
  if (!key) return;

  const exists = Array.from(progressEditRateInput.options || []).some((option) => String(option.value) === key);
  if (exists) return;

  const option = document.createElement("option");
  option.value = key;
  option.textContent = `${key}점 · 기존 저장값`;
  progressEditRateInput.appendChild(option);
}

function syncProgressRateLabel() {
  if (!progressEditRateInput || !progressEditRateGuideEl) return;
  const valueText = formatScoreText(progressEditRateInput.value) || "0";
  progressEditRateGuideEl.textContent = `${valueText}점 기준: ${scoreCriteriaText(progressEditRateInput.value)}`;
}

function setProgressModalOpen(open) {
  if (!progressModalEl) return;
  progressModalEl.hidden = !open;
  document.body.style.overflow = open ? "hidden" : "";
}

function resetProgressQuickForm() {
  progressQuickForm?.reset();
  if (progressEditRateInput) progressEditRateInput.value = "0";
  if (progressEditStatusInput) progressEditStatusInput.value = "not_started";
  if (progressEditDateInput) progressEditDateInput.value = todayValue();
  if (progressEditSourceRoleInput) progressEditSourceRoleInput.value = "주요근거";
  syncProgressRateLabel();
}

function openProgressModalFromButton(button) {
  if (!progressModalEl || !progressQuickForm) return;

  resetProgressQuickForm();

  const nodeId = String(button.getAttribute("data-node-id") || "").trim();
  const nodePath = String(button.getAttribute("data-node-path") || "").trim();
  const currentRate = String(button.getAttribute("data-current-rate") || "").trim();
  const currentStatus = String(button.getAttribute("data-current-status") || "").trim();
  const currentEvaluator = String(button.getAttribute("data-current-evaluator") || "").trim();
  const currentDate = String(button.getAttribute("data-current-date") || "").trim();
  const currentReason = String(button.getAttribute("data-current-reason") || "").trim();

  if (!nodeId) {
    setMessage("평가 대상 정보를 찾지 못했습니다.", "error");
    return;
  }

  if (progressEditNodeIdInput) progressEditNodeIdInput.value = nodeId;
  if (progressNodePathEl) progressNodePathEl.textContent = nodePath || "선택된 항목";
  if (progressEditRateInput && currentRate) {
    ensureProgressRateOption(currentRate);
    progressEditRateInput.value = formatScoreText(currentRate);
  }
  if (progressEditStatusInput && currentStatus) progressEditStatusInput.value = currentStatus;
  if (progressEditEvaluatorInput) progressEditEvaluatorInput.value = currentEvaluator;
  if (progressEditDateInput) progressEditDateInput.value = toDateInputValue(currentDate) || todayValue();
  if (progressEditReasonInput) progressEditReasonInput.value = currentReason;
  syncProgressRateLabel();
  if (progressQuickSaveBtn) progressQuickSaveBtn.disabled = !isLoggedIn;
  if (!isLoggedIn) {
    setMessage("입력창은 확인할 수 있지만 저장은 로그인 후 가능합니다.", "info");
  }

  setProgressModalOpen(true);
}

function closeProgressModal() {
  setProgressModalOpen(false);
}

async function submitProgressQuickForm(event) {
  event.preventDefault();
  if (!isLoggedIn) throw new Error("로그인 후 입력할 수 있습니다.");
  if (!progressEditNodeIdInput?.value) throw new Error("평가 대상이 없습니다.");
  if (!progressEditSourceTitleInput?.value?.trim()) throw new Error("출처 제목을 입력해 주세요.");

  if (progressQuickSaveBtn) progressQuickSaveBtn.disabled = true;
  try {
    await apiPost("/api/progress-admin/quick-record", {
      pledge_node_id: progressEditNodeIdInput.value,
      progress_rate: progressEditRateInput?.value,
      status: progressEditStatusInput?.value,
      evaluator: progressEditEvaluatorInput?.value || "",
      evaluation_date: progressEditDateInput?.value || "",
      reason: progressEditReasonInput?.value || "",
      source_title: progressEditSourceTitleInput?.value || "",
      source_url: progressEditSourceUrlInput?.value || "",
      source_type: progressEditSourceTypeInput?.value || "",
      source_publisher: progressEditSourcePublisherInput?.value || "",
      source_published_at: progressEditSourceDateInput?.value || "",
      source_summary: progressEditSourceSummaryInput?.value || "",
      source_role: progressEditSourceRoleInput?.value || "주요근거",
      quoted_text: progressEditQuoteInput?.value || "",
      page_no: progressEditPageNoInput?.value || "",
      note: progressEditNoteInput?.value || "",
    });

    closeProgressModal();
    await reloadData();
    renderDetail();
    setMessage("이행률과 근거 출처를 저장했습니다.", "success");
  } finally {
    if (progressQuickSaveBtn) progressQuickSaveBtn.disabled = false;
  }
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

async function editCandidate() {
  const name = prompt("이름", candidateData?.name || "");
  if (name === null) return;
  if (!name.trim()) throw new Error("이름을 입력해 주세요.");

  await apiPatch(`/api/admin/candidates/${encodeURIComponent(candidateData.id)}`, {
    name: name.trim(),
  });
}

async function deleteCandidate() {
  if (!confirm("정말 이 정치인을 삭제할까요?")) return;
  await apiDelete(`/api/admin/candidates/${encodeURIComponent(candidateData.id)}`);
  window.location.href = "/politicians";
}

async function editPledge(pledgeId) {
  const pledge = pledgeById.get(String(pledgeId));
  if (!pledge) return;

  const title = prompt("공약 제목", pledge.title || "");
  if (title === null) return;
  const sortOrderRaw = prompt("공약 순서 (sort_order)", String(pledge.sort_order || ""));
  if (sortOrderRaw === null) return;
  const rawText = prompt("공약 원문", pledge.raw_text || "");
  if (rawText === null) return;
  const category = prompt("카테고리", pledge.category || "");
  if (category === null) return;
  const status = prompt("상태", pledge.status || "active");
  if (status === null) return;
  if (!title.trim() || !rawText.trim() || !category.trim()) throw new Error("입력값을 확인해 주세요.");

  const parsedSortOrder = Number(sortOrderRaw || "");
  if (!Number.isFinite(parsedSortOrder) || parsedSortOrder < 1) {
    throw new Error("공약 순서는 1 이상의 숫자여야 합니다.");
  }

  await apiPatch(`/api/admin/pledges/${encodeURIComponent(pledgeId)}`, {
    candidate_election_id: pledge.candidate_election_id,
    sort_order: Math.floor(parsedSortOrder),
    title: title.trim(),
    raw_text: rawText.trim(),
    category: category.trim(),
    status: status.trim() || "active",
  });
}

async function deletePledge(pledgeId) {
  if (!confirm("정말 이 공약을 삭제할까요?")) return;
  await apiDelete(`/api/admin/pledges/${encodeURIComponent(pledgeId)}`);
}

function bindProgressModalEvents() {
  progressEditRateInput?.addEventListener("change", syncProgressRateLabel);
  progressQuickForm?.addEventListener("submit", async (event) => {
    try {
      await submitProgressQuickForm(event);
    } catch (error) {
      setMessage(error.message || "이행률 저장 실패", "error");
    }
  });

  progressModalEl?.addEventListener("click", (event) => {
    const closeBtn = event.target.closest("[data-action='close-progress-modal']");
    if (!closeBtn) return;
    closeProgressModal();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!progressModalEl || progressModalEl.hidden) return;
    closeProgressModal();
  });
}

function bindActions() {
  const profileEl = document.getElementById("politicianProfile");
  const listEl = document.getElementById("politicianPledgeList");

  openFirstProgressBtn?.addEventListener("click", () => {
    openFirstProgressModal();
  });

  profileEl?.addEventListener("click", async (event) => {
    try {
      if (event.target.closest("#reportCandidateBtn")) {
        await reportCandidate();
        return;
      }
      if (!isAdmin) return;
      if (event.target.closest("#editCandidateBtn")) {
        await editCandidate();
        await reloadData();
        renderDetail();
        setMessage("정치인 정보를 수정했습니다.", "success");
      } else if (event.target.closest("#deleteCandidateBtn")) {
        await deleteCandidate();
      }
    } catch (error) {
      setMessage(error.message || "작업 실패", "error");
    }
  });

  listEl?.addEventListener("click", async (event) => {
    const btn = event.target.closest("button[data-action]");
    if (!btn) return;
    const action = btn.getAttribute("data-action");

    try {
      if (action === "open-progress-modal") {
        openProgressModalFromButton(btn);
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
      if (action === "edit-pledge") {
        await editPledge(id);
        await reloadData();
        renderDetail();
        setMessage("공약을 수정했습니다.", "success");
      } else if (action === "delete-pledge") {
        await deletePledge(id);
        await reloadData();
        renderDetail();
        setMessage("공약을 삭제했습니다.", "success");
      }
    } catch (error) {
      setMessage(error.message || "작업 실패", "error");
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  if (!window.location.pathname.startsWith("/politicians/")) return;
  bindActions();
  bindProgressModalEvents();
  resetProgressQuickForm();
  setDetailLoadingState(true);
  setMessage("정치인 정보를 불러오는 중입니다...", "info");
  detectAdmin()
    .then(reloadData)
    .then(() => {
      renderDetail();
      setDetailLoadingState(false);
      const suffix = isLoggedIn
        ? " 각 항목 오른쪽 '이행률 입력' 버튼으로 바로 평가를 등록할 수 있습니다."
        : " 각 항목 오른쪽 '이행률 입력' 버튼으로 입력창을 확인할 수 있으며 저장은 로그인 후 가능합니다.";
      setMessage((isAdmin ? "정치인 상세페이지를 불러왔습니다. (관리자 모드)" : "정치인 상세페이지를 불러왔습니다.") + suffix, "success");
    })
    .catch((error) => {
      setDetailLoadingState(false, false);
      setMessage(error.message || "정치인 상세페이지 로딩 실패", "error");
    });
});
