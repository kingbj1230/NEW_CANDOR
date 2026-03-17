const messageEl = document.getElementById("progressOverviewMessage");
const loadingEl = document.getElementById("progressOverviewLoading");
const loadingTextEl = document.getElementById("progressOverviewLoadingText");

const electionTypeSelect = document.getElementById("overviewElectionType");
const keywordInput = document.getElementById("overviewKeyword");
const refreshBtn = document.getElementById("overviewRefreshBtn");

const listEl = document.getElementById("overviewList");
const countLabelEl = document.getElementById("overviewCountLabel");

let loadingCount = 0;
let overviewRows = [];

function setMessage(text, type = "info") {
  if (!messageEl) return;
  messageEl.className = `progress-overview-message ${type}`;
  messageEl.textContent = text;
}

function setLoading(isLoading, text = "처리 중입니다...") {
  if (!loadingEl) return;
  if (isLoading) {
    loadingCount += 1;
    if (loadingTextEl) loadingTextEl.textContent = text;
    loadingEl.hidden = false;
    return;
  }
  loadingCount = Math.max(0, loadingCount - 1);
  if (loadingCount === 0) loadingEl.hidden = true;
}

async function apiGet(url) {
  const resp = await fetch(url);
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.error || "요청 실패");
  return payload;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function normalizeCandidateId(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  const lowered = text.toLowerCase();
  if (["undefined", "null", "none", "nan"].includes(lowered)) return "";
  return text;
}

function toDateLabel(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString("ko-KR");
}

function formatRate(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "미평가";
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, "");
}

function toPercent(rate) {
  const n = Number(rate);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, (n / 5) * 100));
}

function renderElectionTypeOptions() {
  if (!electionTypeSelect) return;
  const current = electionTypeSelect.value;
  const typeSet = new Set();
  overviewRows.forEach((row) => {
    const electionType = String(row?.election_type || "").trim();
    if (electionType) typeSet.add(electionType);
  });
  const types = Array.from(typeSet).sort((a, b) => a.localeCompare(b, "ko"));
  const options = ['<option value="">전체</option>'];
  types.forEach((electionType) => {
    options.push(`<option value="${escapeHtml(electionType)}">${escapeHtml(electionType)}</option>`);
  });
  electionTypeSelect.innerHTML = options.join("");
  if (current && types.includes(current)) {
    electionTypeSelect.value = current;
  }
}

function renderList(filteredRows) {
  if (!listEl || !countLabelEl) return;
  countLabelEl.textContent = `${filteredRows.length}건`;

  if (!filteredRows.length) {
    listEl.innerHTML = '<article class="overview-item empty">조건에 맞는 결과가 없습니다.</article>';
    return;
  }

  listEl.innerHTML = filteredRows
    .map((row) => {
      const avg = Number(row?.avg_progress);
      const percent = toPercent(avg);
      const hasAvg = Number.isFinite(avg);
      const imageMarkup = row?.candidate_image
        ? `<img src="${escapeHtml(row.candidate_image)}" alt="${escapeHtml(row?.candidate_name || "정치인")}">`
        : '<div class="overview-avatar-empty">이미지</div>';
      const candidateId = normalizeCandidateId(row?.candidate_id);
      const detailHref = candidateId ? `/politicians/${encodeURIComponent(candidateId)}` : "#";
      const detailLabel = candidateId ? "상세에서 평가 입력" : "상세 링크 없음";

      return `
        <article class="overview-item">
          ${imageMarkup}
          <div class="overview-main">
            <h4>${escapeHtml(row?.candidate_name || "이름 없음")}</h4>
            <p>${escapeHtml(row?.election_type || "기타")} · ${escapeHtml(row?.election_title || "선거 정보 없음")} · ${escapeHtml(toDateLabel(row?.election_date))}</p>
            <p>${escapeHtml(row?.party || "-")} · ${escapeHtml(row?.result || "-")} · 평가 ${escapeHtml(String(row?.evaluated_count || 0))}/${escapeHtml(String(row?.target_count || 0))}</p>
          </div>
          <div class="overview-side">
            <div class="overview-bar" title="평균 이행률 ${escapeHtml(formatRate(avg))}">
              <span style="width:${percent}%;"></span>
            </div>
            <div class="score">${hasAvg ? `${escapeHtml(formatRate(avg))}` : "미평가"}</div>
            <a class="overview-link" href="${detailHref}" ${candidateId ? "" : 'aria-disabled="true" tabindex="-1"'}>${detailLabel}</a>
          </div>
        </article>
      `;
    })
    .join("");
}

function applyFilters() {
  const electionType = String(electionTypeSelect?.value || "").trim();
  const keyword = String(keywordInput?.value || "").trim().toLowerCase();

  let filtered = overviewRows.slice();
  if (electionType) {
    filtered = filtered.filter((row) => String(row?.election_type || "") === electionType);
  }
  if (keyword) {
    filtered = filtered.filter((row) => {
      const haystack = [
        row?.candidate_name,
        row?.party,
        row?.election_type,
        row?.election_title,
        row?.result,
      ]
        .map((v) => String(v || ""))
        .join(" ")
        .toLowerCase();
      return haystack.includes(keyword);
    });
  }

  renderList(filtered);
}

async function loadOverview() {
  setLoading(true, "이행현황을 불러오는 중입니다...");
  try {
    const payload = await apiGet("/api/progress-overview");
    overviewRows = payload.rows || [];
    renderElectionTypeOptions();
    applyFilters();
    setMessage("이행현황을 불러왔습니다.", "success");
  } catch (error) {
    setMessage(error.message || "이행현황 조회 실패", "error");
  } finally {
    setLoading(false);
  }
}

function bindEvents() {
  electionTypeSelect?.addEventListener("change", applyFilters);
  keywordInput?.addEventListener("input", applyFilters);
  refreshBtn?.addEventListener("click", loadOverview);
}

document.addEventListener("DOMContentLoaded", () => {
  if (window.location.pathname !== "/progress") return;
  bindEvents();
  setMessage("이행현황을 준비하는 중입니다...", "info");
  loadOverview();
});
