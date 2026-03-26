const candidateShell = document.querySelector(".candidate-shell");
const isAdminUser = String(candidateShell?.dataset?.isAdmin || "").toLowerCase() === "true";

const messageEl = document.getElementById("candidateMessage");
const electionForm = document.getElementById("electionForm");
const electionList = document.getElementById("electionList");
const refreshElectionsBtn = document.getElementById("refreshElectionsBtn");
const saveElectionBtn = document.getElementById("saveElectionBtn");
const cancelElectionEditBtn = document.getElementById("cancelElectionEditBtn");
const electionIdInput = document.getElementById("electionId");
const electionTypeInput = document.getElementById("electionType");
const electionTitleInput = document.getElementById("electionTitle");
const electionDateInput = document.getElementById("electionDate");

const candidateElectionForm = document.getElementById("candidateElectionForm");
const candidateElectionList = document.getElementById("candidateElectionList");
const refreshCandidateElectionsBtn = document.getElementById("refreshCandidateElectionsBtn");
const saveCandidateElectionBtn = document.getElementById("saveCandidateElectionBtn");
const cancelCandidateElectionEditBtn = document.getElementById("cancelCandidateElectionEditBtn");

const linkCandidateId = document.getElementById("linkCandidateId");
const linkCandidateSearch = document.getElementById("linkCandidateSearch");
const linkCandidateElectionId = document.getElementById("linkCandidateElectionId");
const candidateSearchDropdown = document.getElementById("candidateSearchDropdown");
const candidateSearchHelp = document.getElementById("candidateSearchHelp");
const candidateEmptyNotice = document.getElementById("candidateEmptyNotice");
const linkElectionId = document.getElementById("linkElectionId");
const linkParty = document.getElementById("linkParty");
const linkCandidateNumber = document.getElementById("linkCandidateNumber");
const linkResult = document.getElementById("linkResult");
const winnerDetailSection = document.getElementById("winnerDetailSection");
const linkTermPosition = document.getElementById("linkTermPosition");
const linkTermStart = document.getElementById("linkTermStart");
const linkTermEnd = document.getElementById("linkTermEnd");

const tabButtons = Array.from(document.querySelectorAll("[data-admin-tab-target]"));
const tabPanels = Array.from(document.querySelectorAll("[data-admin-tab-panel]"));

const CANDIDATE_ELECTION_SAVE_LABEL = "선거 후보 저장";
const CANDIDATE_ELECTION_EDIT_LABEL = "선거 후보 수정 저장";
const ELECTION_SAVE_LABEL = "선거 저장";
const ELECTION_EDIT_LABEL = "선거 수정 저장";
const PRESIDENT_ELECTION_TYPE = "대통령";
const CANDIDATE_SEARCH_PLACEHOLDER = "이름을 입력해 후보자를 선택해 주세요";
const CANDIDATE_REQUIRED_PLACEHOLDER = "후보자를 먼저 등록해주세요";

let candidateRows = [];
let electionRows = [];
let candidateElectionRows = [];
let termRows = [];
let candidateDisplayRows = [];
let termByPair = new Map();
let visibleCandidateOptions = [];
let activeCandidateOptionIndex = -1;
let candidateSearchBlurTimer = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function setMessage(text, type = "info") {
  if (!messageEl) return;
  messageEl.className = `candidate-message ${type}`;
  messageEl.textContent = text;
}

async function apiGet(url) {
  const resp = await fetch(url);
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.error || "요청 실패");
  return payload;
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

function toDateLabel(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString("ko-KR");
}

function isElectValue(value) {
  if (value === true || value === 1) return true;
  const text = String(value ?? "").trim().toLowerCase();
  if (!text) return false;
  return ["1", "true", "t", "yes", "y", "당선", "당선자"].includes(text);
}

function toDisplayDate(value) {
  const text = String(value ?? "").trim();
  if (!text) return "-";
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  return toDateLabel(text);
}

function normalizeText(value) {
  return String(value ?? "").trim().toLowerCase();
}

function normalizeElectionRoundValue(value) {
  const text = String(value ?? "").trim();
  if (!/^\d+$/.test(text)) return "";
  const parsed = Number(text);
  if (!Number.isFinite(parsed) || parsed < 1 || parsed > 32767) return "";
  return String(parsed);
}

function formatPresidentialElectionTitle(value) {
  const round = normalizeElectionRoundValue(value);
  if (!round) return String(value ?? "").trim() || "-";
  return `제${round}대 대통령 선거`;
}

function normalizeDateInputValue(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return "";
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseDateLike(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;

  const datePart = raw.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(datePart)) return null;
  const [year, month, day] = datePart.split("-").map(Number);
  const utcDate = new Date(Date.UTC(year, month - 1, day));
  if (Number.isNaN(utcDate.getTime())) return null;
  return utcDate;
}

function formatDateInput(date) {
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  const d = String(date.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function addDaysUtc(date, days) {
  const next = new Date(date.getTime());
  next.setUTCDate(next.getUTCDate() + days);
  return next;
}

function addYearsUtc(date, years) {
  const next = new Date(date.getTime());
  next.setUTCFullYear(next.getUTCFullYear() + years);
  return next;
}

function inferTermYears(electionType) {
  const text = String(electionType || "");
  if (text.includes("대통령")) return 5;
  if (text.includes("국회의원")) return 4;
  return null;
}

function getCandidateElectionPairKey(candidateId, electionId) {
  const cid = String(candidateId ?? "").trim();
  const eid = String(electionId ?? "").trim();
  if (!cid || !eid) return "";
  return `${cid}::${eid}`;
}

function getTermByPair(candidateId, electionId) {
  const key = getCandidateElectionPairKey(candidateId, electionId);
  if (!key) return null;
  return termByPair.get(key) || null;
}

function buildTermMap(rows) {
  const nextMap = new Map();
  (rows || []).forEach((row) => {
    const key = getCandidateElectionPairKey(row?.candidate_id, row?.election_id);
    if (!key || nextMap.has(key)) return;
    nextMap.set(key, row);
  });
  return nextMap;
}

function shouldShowWinnerDetail() {
  const resultText = String(linkResult?.value || "").trim();
  return isElectValue(resultText);
}

function clearWinnerTermInputs() {
  if (linkTermPosition) linkTermPosition.value = "";
  if (linkTermStart) linkTermStart.value = "";
  if (linkTermEnd) linkTermEnd.value = "";
}

function applyWinnerTermAutofill() {
  if (!shouldShowWinnerDetail()) return;
  if (!linkElectionId) return;

  const electionId = String(linkElectionId.value || "").trim();
  if (!electionId) return;

  const electionMap = new Map(electionRows.map((row) => [String(row.id), row]));
  const election = electionMap.get(electionId);
  if (!election) return;

  if (linkTermPosition && !String(linkTermPosition.value || "").trim()) {
    linkTermPosition.value = String(election.election_type || "").trim();
  }

  const electionDate = parseDateLike(election.election_date);
  if (!electionDate) return;

  const termStart = addDaysUtc(electionDate, 1);
  if (linkTermStart && !String(linkTermStart.value || "").trim()) {
    linkTermStart.value = formatDateInput(termStart);
  }

  const years = inferTermYears(election.election_type);
  if (years && linkTermEnd && !String(linkTermEnd.value || "").trim()) {
    const termEnd = addDaysUtc(addYearsUtc(termStart, years), -1);
    linkTermEnd.value = formatDateInput(termEnd);
  }
}

function syncWinnerDetailVisibility({ autofill = true, clearWhenHidden = true } = {}) {
  const visible = shouldShowWinnerDetail();
  if (winnerDetailSection) {
    winnerDetailSection.hidden = !visible;
  }

  [linkTermPosition, linkTermStart, linkTermEnd].forEach((el) => {
    if (!el) return;
    el.disabled = !visible;
  });

  if (visible) {
    if (autofill) applyWinnerTermAutofill();
    return;
  }

  if (clearWhenHidden) clearWinnerTermInputs();
}

function calculateAgeFromBirthDate(value) {
  const text = String(value ?? "").trim();
  if (!text) return null;

  let year = null;
  let month = null;
  let day = null;
  const plainDateMatch = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (plainDateMatch) {
    year = Number(plainDateMatch[1]);
    month = Number(plainDateMatch[2]);
    day = Number(plainDateMatch[3]);
  } else {
    const parsed = new Date(text);
    if (Number.isNaN(parsed.getTime())) return null;
    year = parsed.getFullYear();
    month = parsed.getMonth() + 1;
    day = parsed.getDate();
  }

  const today = new Date();
  let age = today.getFullYear() - year;
  const currentMonth = today.getMonth() + 1;
  const currentDay = today.getDate();
  if (currentMonth < month || (currentMonth === month && currentDay < day)) {
    age -= 1;
  }
  return age >= 0 ? age : null;
}

function getCandidatePrimaryName(row) {
  const name = String(row?.name || "이름 없음").trim();
  return name || "이름 없음";
}

function makeCandidateOptionMeta(row) {
  const birthDateText = toDisplayDate(row?.birth_date);
  const age = calculateAgeFromBirthDate(row?.birth_date);
  const ageText = age === null ? "나이 미상" : `현재 ${age}세`;
  return `생년월일 ${birthDateText} · ${ageText}`;
}

function setupCandidateOptions(rows) {
  candidateDisplayRows = [];

  (rows || []).forEach((row) => {
    const id = String(row?.id ?? "").trim();
    if (!id) return;

    const name = getCandidatePrimaryName(row);
    const meta = makeCandidateOptionMeta(row);
    const normalizedName = normalizeText(name);
    const normalizedMeta = normalizeText(meta);

    candidateDisplayRows.push({
      id,
      name,
      meta,
      normalizedName,
      searchableText: `${normalizedName} ${normalizedMeta}`,
    });
  });
}

function getCandidateDisplayRowById(candidateId) {
  const target = String(candidateId ?? "").trim();
  if (!target) return null;
  return candidateDisplayRows.find((row) => String(row.id) === target) || null;
}

function hideCandidateSearchDropdown() {
  if (!candidateSearchDropdown) return;
  candidateSearchDropdown.hidden = true;
  visibleCandidateOptions = [];
  activeCandidateOptionIndex = -1;
}

function setActiveCandidateOptionIndex(index) {
  if (!candidateSearchDropdown || !visibleCandidateOptions.length) {
    activeCandidateOptionIndex = -1;
    return;
  }

  const nextIndex = Number(index);
  if (!Number.isFinite(nextIndex) || nextIndex < 0 || nextIndex >= visibleCandidateOptions.length) {
    activeCandidateOptionIndex = -1;
  } else {
    activeCandidateOptionIndex = nextIndex;
  }

  const optionEls = candidateSearchDropdown.querySelectorAll("[data-option-index]");
  optionEls.forEach((el) => {
    const optionIndex = Number(el.getAttribute("data-option-index"));
    const isActive = optionIndex === activeCandidateOptionIndex;
    el.classList.toggle("is-active", isActive);
    el.setAttribute("aria-selected", String(isActive));
  });
}

function renderCandidateSearchDropdown(searchText = "", { openWhenEmpty = true } = {}) {
  if (!candidateSearchDropdown) return;
  if (!candidateDisplayRows.length) {
    hideCandidateSearchDropdown();
    return;
  }

  const keyword = normalizeText(searchText);
  const filteredRows = candidateDisplayRows
    .filter((row) => (!keyword ? true : row.searchableText.includes(keyword)))
    .sort((a, b) => {
      if (!keyword) return a.name.localeCompare(b.name, "ko");
      const aExact = a.normalizedName === keyword;
      const bExact = b.normalizedName === keyword;
      if (aExact !== bExact) return aExact ? -1 : 1;
      const aStartsWith = a.normalizedName.startsWith(keyword);
      const bStartsWith = b.normalizedName.startsWith(keyword);
      if (aStartsWith !== bStartsWith) return aStartsWith ? -1 : 1;
      return a.name.localeCompare(b.name, "ko");
    })
    .slice(0, 12);

  if (!filteredRows.length) {
    candidateSearchDropdown.innerHTML = '<div class="candidate-search-empty">일치하는 후보자가 없습니다.</div>';
    visibleCandidateOptions = [];
    activeCandidateOptionIndex = -1;
    candidateSearchDropdown.hidden = false;
    return;
  }

  visibleCandidateOptions = filteredRows;
  candidateSearchDropdown.innerHTML = filteredRows
    .map((row, index) => {
      const isActive = index === 0;
      return `
      <button
        type="button"
        class="candidate-search-option${isActive ? " is-active" : ""}"
        data-option-index="${index}"
        data-candidate-id="${escapeHtml(row.id)}"
        role="option"
        aria-selected="${isActive ? "true" : "false"}">
        <span class="option-name">${escapeHtml(row.name)}</span>
        <span class="option-meta">${escapeHtml(row.meta)}</span>
      </button>
    `;
    })
    .join("");

  activeCandidateOptionIndex = 0;
  candidateSearchDropdown.hidden = false;

  if (!openWhenEmpty && !keyword) {
    hideCandidateSearchDropdown();
  }
}

function selectCandidateById(candidateId) {
  const selected = getCandidateDisplayRowById(candidateId);
  if (!selected) return;
  if (linkCandidateId) linkCandidateId.value = selected.id;
  if (linkCandidateSearch) linkCandidateSearch.value = selected.name;
  hideCandidateSearchDropdown();
}

function updateCandidateAvailability() {
  const hasCandidates = candidateRows.length > 0;
  const hasElections = electionRows.length > 0;
  const canSubmitMapping = hasCandidates && hasElections;

  if (candidateSearchHelp) candidateSearchHelp.hidden = !hasCandidates;
  if (candidateEmptyNotice) candidateEmptyNotice.hidden = hasCandidates;

  if (linkCandidateSearch) {
    linkCandidateSearch.disabled = !hasCandidates;
    linkCandidateSearch.required = hasCandidates;
    linkCandidateSearch.placeholder = hasCandidates ? CANDIDATE_SEARCH_PLACEHOLDER : CANDIDATE_REQUIRED_PLACEHOLDER;
    if (!hasCandidates) {
      linkCandidateSearch.value = "";
      hideCandidateSearchDropdown();
    }
  }

  if (linkCandidateId && !hasCandidates) {
    linkCandidateId.value = "";
  }

  if (saveCandidateElectionBtn) {
    saveCandidateElectionBtn.disabled = !canSubmitMapping;
  }
}

function getCandidateLabelById(candidateId) {
  return getCandidateDisplayRowById(candidateId)?.name || "";
}

function syncCandidateIdFromInput() {
  if (!linkCandidateSearch || !linkCandidateId) return;

  const searchText = String(linkCandidateSearch.value || "").trim();
  if (!searchText) {
    linkCandidateId.value = "";
    return;
  }

  const currentCandidate = getCandidateDisplayRowById(linkCandidateId.value);
  if (currentCandidate && normalizeText(currentCandidate.name) === normalizeText(searchText)) {
    return;
  }

  const normalizedSearch = normalizeText(searchText);
  const matchedByName = candidateDisplayRows.filter((item) => item.normalizedName === normalizedSearch);
  if (matchedByName.length === 1) {
    linkCandidateId.value = matchedByName[0].id;
    return;
  }

  linkCandidateId.value = "";
}

function populateSelect(selectEl, rows, placeholder, labelMaker) {
  if (!selectEl) return;

  const options = rows.map((row) => `<option value="${escapeHtml(row.id)}">${escapeHtml(labelMaker(row))}</option>`).join("");
  selectEl.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>${options}`;
}

function renderElections(rows) {
  if (!electionList) return;

  if (!rows.length) {
    electionList.innerHTML = '<p class="empty">아직 등록된 선거가 없습니다.</p>';
    return;
  }

  electionList.innerHTML = rows
    .map((row) => {
      const rowId = String(row?.id ?? "").trim();
      const createdAt = toDateLabel(row.created_at);
      const electionDate = row.election_date || "-";
      const electionType = row.election_type || PRESIDENT_ELECTION_TYPE;
      const electionTitle = formatPresidentialElectionTitle(row.title);
      const adminActions = isAdminUser && rowId
        ? `
        <div class="relation-actions">
          <button type="button" data-election-action="edit" data-election-id="${escapeHtml(rowId)}">수정</button>
          <button type="button" class="danger" data-election-action="delete" data-election-id="${escapeHtml(rowId)}">삭제</button>
        </div>
      `
        : "";

      return `
      <article class="election-card">
        <span class="tag">${escapeHtml(electionType)}</span>
        <h3 class="card-title">${escapeHtml(electionTitle)}</h3>
        <p class="card-sub">선거일: ${escapeHtml(electionDate)}</p>
        <div class="card-meta">${escapeHtml(createdAt)} 생성</div>
        ${adminActions}
      </article>
    `;
    })
    .join("");
}

function renderCandidateElections(rows) {
  if (!candidateElectionList) return;

  if (!rows.length) {
    candidateElectionList.innerHTML = '<p class="empty">아직 등록된 선거 후보가 없습니다.</p>';
    return;
  }

  const candidateMap = new Map(candidateRows.map((row) => [String(row.id), row]));
  const electionMap = new Map(electionRows.map((row) => [String(row.id), row]));

  candidateElectionList.innerHTML = rows
    .map((row) => {
      const rowId = String(row?.id ?? "").trim();
      const candidate = candidateMap.get(String(row.candidate_id));
      const election = electionMap.get(String(row.election_id));
      const matchedTerm = getTermByPair(row.candidate_id, row.election_id);
      const candidateName = candidate?.name || "이름 미확인 후보";
      const electionTitle = election ? formatPresidentialElectionTitle(election.title) : "선거 정보 없음";
      const electionType = election?.election_type || PRESIDENT_ELECTION_TYPE;
      const createdAt = toDateLabel(row.created_at);
      const isElectText = isElectValue(row.is_elect) ? "당선" : "비당선";
      const termPeriod = matchedTerm
        ? `${matchedTerm.term_start || "-"} ~ ${matchedTerm.term_end || "진행 중"}`
        : "";
      const termLine = matchedTerm
        ? `<p class="card-sub">직책: ${escapeHtml(matchedTerm.position || "-")} · 임기: ${escapeHtml(termPeriod)}</p>`
        : "";

      const adminActions = isAdminUser && rowId
        ? `
        <div class="relation-actions">
          <button type="button" data-candidate-election-action="edit" data-candidate-election-id="${escapeHtml(rowId)}">수정</button>
          <button type="button" class="danger" data-candidate-election-action="delete" data-candidate-election-id="${escapeHtml(rowId)}">삭제</button>
        </div>
      `
        : "";

      return `
      <article class="election-card relation-card">
        <span class="tag">${escapeHtml(row.result || "-")}</span>
        <h3 class="card-title">${escapeHtml(candidateName)}</h3>
        <p class="card-sub">${escapeHtml(electionType)} · ${escapeHtml(electionTitle)}</p>
        <p class="card-sub">${escapeHtml(row.party || "-")} · 기호: ${escapeHtml(row.candidate_number || "-")}</p>
        ${termLine}
        <div class="card-meta">${escapeHtml(isElectText)} · ${escapeHtml(createdAt)} 생성</div>
        ${adminActions}
      </article>
    `;
    })
    .join("");
}

function resetElectionEditState() {
  if (electionIdInput) electionIdInput.value = "";
  if (electionTypeInput) electionTypeInput.value = PRESIDENT_ELECTION_TYPE;
  if (saveElectionBtn) saveElectionBtn.textContent = ELECTION_SAVE_LABEL;
  if (cancelElectionEditBtn) cancelElectionEditBtn.hidden = true;
}

function enterElectionEditMode(row, { silent = false } = {}) {
  if (!row) return;

  const rowId = String(row.id ?? "").trim();
  if (!rowId) return;

  if (electionIdInput) electionIdInput.value = rowId;
  if (electionTypeInput) electionTypeInput.value = PRESIDENT_ELECTION_TYPE;
  if (electionTitleInput) electionTitleInput.value = normalizeElectionRoundValue(row.title);
  if (electionDateInput) electionDateInput.value = normalizeDateInputValue(row.election_date);
  if (saveElectionBtn) saveElectionBtn.textContent = ELECTION_EDIT_LABEL;
  if (cancelElectionEditBtn) cancelElectionEditBtn.hidden = false;

  if (!silent) {
    setActiveAdminTab("election");
    setMessage("선거 수정 모드입니다. 값을 바꾼 뒤 저장해 주세요.", "info");
  }
}

function resetCandidateElectionEditState() {
  if (candidateSearchBlurTimer) {
    window.clearTimeout(candidateSearchBlurTimer);
    candidateSearchBlurTimer = null;
  }
  hideCandidateSearchDropdown();
  if (linkCandidateElectionId) linkCandidateElectionId.value = "";
  if (saveCandidateElectionBtn) saveCandidateElectionBtn.textContent = CANDIDATE_ELECTION_SAVE_LABEL;
  if (cancelCandidateElectionEditBtn) cancelCandidateElectionEditBtn.hidden = true;
  clearWinnerTermInputs();
  syncWinnerDetailVisibility({ autofill: true, clearWhenHidden: true });
}

function enterCandidateElectionEditMode(row, { silent = false } = {}) {
  if (!row) return;

  const rowId = String(row.id ?? "").trim();
  if (!rowId) return;

  if (linkCandidateElectionId) linkCandidateElectionId.value = rowId;
  if (linkCandidateId) linkCandidateId.value = String(row.candidate_id ?? "").trim();
  if (linkCandidateSearch) linkCandidateSearch.value = getCandidateLabelById(row.candidate_id);
  hideCandidateSearchDropdown();
  if (linkElectionId) linkElectionId.value = String(row.election_id ?? "").trim();
  if (linkParty) linkParty.value = String(row.party ?? "").trim();
  if (linkCandidateNumber) linkCandidateNumber.value = String(row.candidate_number ?? "").trim();
  if (linkResult) linkResult.value = String(row.result ?? "").trim() || "기타";
  const matchedTerm = getTermByPair(row.candidate_id, row.election_id);
  if (linkTermPosition) linkTermPosition.value = String(matchedTerm?.position ?? "").trim();
  if (linkTermStart) linkTermStart.value = normalizeDateInputValue(matchedTerm?.term_start);
  if (linkTermEnd) linkTermEnd.value = normalizeDateInputValue(matchedTerm?.term_end);
  syncWinnerDetailVisibility({ autofill: !matchedTerm, clearWhenHidden: true });

  if (saveCandidateElectionBtn) saveCandidateElectionBtn.textContent = CANDIDATE_ELECTION_EDIT_LABEL;
  if (cancelCandidateElectionEditBtn) cancelCandidateElectionEditBtn.hidden = false;

  if (!silent) {
    setActiveAdminTab("mapping");
    setMessage("수정 모드입니다. 값을 바꾼 뒤 저장해 주세요.", "info");
  }
}

function setActiveAdminTab(tabName) {
  tabButtons.forEach((button) => {
    const isActive = button.dataset.adminTabTarget === tabName;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });

  tabPanels.forEach((panel) => {
    const isActive = panel.dataset.adminTabPanel === tabName;
    panel.classList.toggle("is-active", isActive);
    panel.hidden = !isActive;
  });
}

function bindTabEvents() {
  tabButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setActiveAdminTab(button.dataset.adminTabTarget);
    });
  });
}

async function refreshAllElectionAdminData() {
  const editingElectionIdBeforeRefresh = String(electionIdInput?.value || "").trim();
  const editingIdBeforeRefresh = String(linkCandidateElectionId?.value || "").trim();

  const [candidatesResp, electionsResp, linksResp, termsResp] = await Promise.all([
    apiGet("/api/candidate-admin/candidates"),
    apiGet("/api/candidate-admin/elections"),
    apiGet("/api/candidate-admin/candidate-elections"),
    apiGet("/api/candidate-admin/terms"),
  ]);

  candidateRows = candidatesResp.rows || [];
  electionRows = electionsResp.rows || [];
  candidateElectionRows = linksResp.rows || [];
  termRows = termsResp.rows || [];
  termByPair = buildTermMap(termRows);

  setupCandidateOptions(candidateRows);
  if (linkCandidateSearch) {
    const currentCandidateId = String(linkCandidateId?.value || "").trim();
    linkCandidateSearch.value = currentCandidateId ? getCandidateLabelById(currentCandidateId) : "";
  }
  hideCandidateSearchDropdown();

  populateSelect(
    linkElectionId,
    electionRows,
    "선거를 선택해 주세요",
    (row) => `${formatPresidentialElectionTitle(row.title)} (${row.election_date || "일자 미지정"})`,
  );

  renderElections(electionRows);
  renderCandidateElections(candidateElectionRows);
  updateCandidateAvailability();
  syncWinnerDetailVisibility({ autofill: true, clearWhenHidden: false });

  if (editingElectionIdBeforeRefresh) {
    const editingElection = electionRows.find((row) => String(row?.id ?? "") === editingElectionIdBeforeRefresh);
    if (editingElection) {
      enterElectionEditMode(editingElection, { silent: true });
    } else {
      resetElectionEditState();
    }
  }

  if (editingIdBeforeRefresh) {
    const editingRow = candidateElectionRows.find((row) => String(row?.id ?? "") === editingIdBeforeRefresh);
    if (editingRow) {
      enterCandidateElectionEditMode(editingRow, { silent: true });
    } else {
      resetCandidateElectionEditState();
    }
  }
}

electionForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage("선거 저장 중...", "info");
  if (saveElectionBtn) saveElectionBtn.disabled = true;

  try {
    const formData = new FormData(electionForm);
    const editId = String(formData.get("election_id") || "").trim();
    const electionRound = normalizeElectionRoundValue(formData.get("title"));
    if (!electionRound) {
      throw new Error("선거 이름은 1~32767 사이 숫자만 입력해 주세요.");
    }

    const payload = {
      election_type: PRESIDENT_ELECTION_TYPE,
      title: electionRound,
      election_date: formData.get("election_date"),
    };

    if (editId) {
      if (!isAdminUser) {
        throw new Error("관리자만 수정할 수 있습니다.");
      }
      await apiPatch(`/api/admin/elections/${encodeURIComponent(editId)}`, payload);
      setMessage("선거 정보가 수정되었습니다.", "success");
    } else {
      await apiPost("/api/candidate-admin/elections", payload);
      setMessage("선거가 저장되었습니다.", "success");
    }

    electionForm.reset();
    resetElectionEditState();
    await refreshAllElectionAdminData();
  } catch (error) {
    setMessage(error.message || "선거 저장 실패", "error");
  } finally {
    if (saveElectionBtn) saveElectionBtn.disabled = false;
  }
});

electionList?.addEventListener("click", async (event) => {
  const actionButton = event.target?.closest?.("[data-election-action]");
  if (!actionButton) return;

  if (!isAdminUser) {
    setMessage("관리자만 수정/삭제할 수 있습니다.", "error");
    return;
  }

  const action = String(actionButton.dataset.electionAction || "").trim();
  const electionId = String(actionButton.dataset.electionId || "").trim();
  if (!action || !electionId) return;

  if (action === "edit") {
    const row = electionRows.find((item) => String(item?.id ?? "") === electionId);
    if (!row) {
      setMessage("수정할 선거를 찾지 못했습니다.", "error");
      return;
    }
    enterElectionEditMode(row);
    return;
  }

  if (action === "delete") {
    const confirmed = window.confirm("정말 이 선거를 삭제할까요?");
    if (!confirmed) return;

    try {
      await apiDelete(`/api/admin/elections/${encodeURIComponent(electionId)}`);
      if (String(electionIdInput?.value || "") === electionId) {
        electionForm?.reset();
        resetElectionEditState();
      }
      await refreshAllElectionAdminData();
      setMessage("선거가 삭제되었습니다.", "success");
    } catch (error) {
      setMessage(error.message || "선거 삭제 실패", "error");
    }
  }
});

candidateElectionForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage("선거 후보 저장 중...", "info");
  if (saveCandidateElectionBtn) saveCandidateElectionBtn.disabled = true;

  try {
    if (!candidateRows.length) {
      throw new Error("후보자를 먼저 등록해주세요.");
    }
    if (!electionRows.length) {
      throw new Error("선거를 먼저 등록해주세요.");
    }

    syncCandidateIdFromInput();
    const formData = new FormData(candidateElectionForm);
    const candidateId = String(formData.get("candidate_id") || "").trim();
    const electionId = String(formData.get("election_id") || "").trim();
    const editId = String(formData.get("candidate_election_id") || "").trim();

    if (!candidateId) {
      throw new Error("후보자를 목록에서 선택해 주세요.");
    }
    if (!electionId) {
      throw new Error("선거를 선택해 주세요.");
    }

    const candidateNumberRaw = formData.get("candidate_number");
    const candidateNumber = Number(candidateNumberRaw);
    if (!Number.isFinite(candidateNumber) || candidateNumber < 1) {
      throw new Error("기호는 1 이상의 숫자여야 합니다.");
    }

    const payload = {
      candidate_id: candidateId,
      election_id: electionId,
      party: (formData.get("party") || "").trim(),
      result: String(formData.get("result") || "").trim(),
      candidate_number: candidateNumber,
    };
    const isWinner = isElectValue(payload.result);
    const termPosition = String(formData.get("term_position") || "").trim();
    const termStart = normalizeDateInputValue(formData.get("term_start"));
    const termEnd = normalizeDateInputValue(formData.get("term_end"));
    const hasTermPayload = Boolean(termPosition || termStart || termEnd);

    if (isWinner && hasTermPayload && (!termPosition || !termStart)) {
      throw new Error("당선 경력을 저장하려면 직책과 임기 시작일이 필요합니다.");
    }
    if (termEnd && !termStart) {
      throw new Error("임기 종료일을 입력하려면 임기 시작일이 필요합니다.");
    }
    if (termEnd && termStart && String(termEnd) < String(termStart)) {
      throw new Error("임기 종료일은 시작일 이후여야 합니다.");
    }

    payload.term_position = isWinner ? (termPosition || null) : null;
    payload.term_start = isWinner ? (termStart || null) : null;
    payload.term_end = isWinner ? (termEnd || null) : null;

    if (editId) {
      if (!isAdminUser) {
        throw new Error("관리자만 수정할 수 있습니다.");
      }
      await apiPatch(`/api/admin/candidate-elections/${encodeURIComponent(editId)}`, payload);
      setMessage("선거 후보 정보가 수정되었습니다.", "success");
    } else {
      await apiPost("/api/candidate-admin/candidate-elections", payload);
      setMessage("선거 후보 정보가 저장되었습니다.", "success");
    }

    candidateElectionForm.reset();
    if (linkCandidateId) linkCandidateId.value = "";
    if (linkCandidateSearch) linkCandidateSearch.value = "";
    resetCandidateElectionEditState();
    await refreshAllElectionAdminData();
  } catch (error) {
    setMessage(error.message || "선거 후보 저장 실패", "error");
  } finally {
    updateCandidateAvailability();
  }
});

candidateElectionList?.addEventListener("click", async (event) => {
  const actionButton = event.target?.closest?.("[data-candidate-election-action]");
  if (!actionButton) return;

  if (!isAdminUser) {
    setMessage("관리자만 수정/삭제할 수 있습니다.", "error");
    return;
  }

  const action = String(actionButton.dataset.candidateElectionAction || "").trim();
  const rowId = String(actionButton.dataset.candidateElectionId || "").trim();
  if (!action || !rowId) return;

  if (action === "edit") {
    const row = candidateElectionRows.find((item) => String(item?.id ?? "") === rowId);
    if (!row) {
      setMessage("수정할 대상을 찾지 못했습니다.", "error");
      return;
    }
    enterCandidateElectionEditMode(row);
    return;
  }

  if (action === "delete") {
    const confirmed = window.confirm("정말 이 선거 후보 정보를 삭제할까요?");
    if (!confirmed) return;

    try {
      await apiDelete(`/api/admin/candidate-elections/${encodeURIComponent(rowId)}`);
      if (String(linkCandidateElectionId?.value || "") === rowId) {
        candidateElectionForm?.reset();
        if (linkCandidateId) linkCandidateId.value = "";
        if (linkCandidateSearch) linkCandidateSearch.value = "";
        resetCandidateElectionEditState();
      }
      await refreshAllElectionAdminData();
      setMessage("선거 후보 정보가 삭제되었습니다.", "success");
    } catch (error) {
      setMessage(error.message || "선거 후보 삭제 실패", "error");
    }
  }
});

cancelCandidateElectionEditBtn?.addEventListener("click", () => {
  candidateElectionForm?.reset();
  if (linkCandidateId) linkCandidateId.value = "";
  if (linkCandidateSearch) linkCandidateSearch.value = "";
  resetCandidateElectionEditState();
  setMessage("수정 모드를 취소했습니다.", "info");
});

cancelElectionEditBtn?.addEventListener("click", () => {
  electionForm?.reset();
  resetElectionEditState();
  setMessage("선거 수정 모드를 취소했습니다.", "info");
});

refreshElectionsBtn?.addEventListener("click", async () => {
  try {
    await refreshAllElectionAdminData();
    setMessage("선거 목록을 갱신했습니다.", "success");
  } catch (error) {
    setMessage(error.message || "선거 조회 실패", "error");
  }
});

refreshCandidateElectionsBtn?.addEventListener("click", async () => {
  try {
    await refreshAllElectionAdminData();
    setMessage("선거 후보 목록을 갱신했습니다.", "success");
  } catch (error) {
    setMessage(error.message || "선거 후보 조회 실패", "error");
  }
});

linkCandidateSearch?.addEventListener("focus", () => {
  if (candidateSearchBlurTimer) {
    window.clearTimeout(candidateSearchBlurTimer);
    candidateSearchBlurTimer = null;
  }
  renderCandidateSearchDropdown(linkCandidateSearch.value, { openWhenEmpty: true });
});
linkCandidateSearch?.addEventListener("input", () => {
  syncCandidateIdFromInput();
  renderCandidateSearchDropdown(linkCandidateSearch.value, { openWhenEmpty: true });
});
linkCandidateSearch?.addEventListener("change", syncCandidateIdFromInput);
linkCandidateSearch?.addEventListener("keydown", (event) => {
  const isArrowDown = event.key === "ArrowDown";
  const isArrowUp = event.key === "ArrowUp";
  const isEnter = event.key === "Enter";
  const isEscape = event.key === "Escape";

  if ((isArrowDown || isArrowUp) && candidateSearchDropdown?.hidden && candidateDisplayRows.length) {
    renderCandidateSearchDropdown(linkCandidateSearch?.value || "", { openWhenEmpty: true });
    event.preventDefault();
    return;
  }

  if (!visibleCandidateOptions.length || candidateSearchDropdown?.hidden) {
    if (isEscape) hideCandidateSearchDropdown();
    return;
  }

  if (isArrowDown) {
    event.preventDefault();
    const maxIndex = visibleCandidateOptions.length - 1;
    const nextIndex = activeCandidateOptionIndex >= maxIndex ? 0 : activeCandidateOptionIndex + 1;
    setActiveCandidateOptionIndex(nextIndex);
    return;
  }

  if (isArrowUp) {
    event.preventDefault();
    const maxIndex = visibleCandidateOptions.length - 1;
    const nextIndex = activeCandidateOptionIndex <= 0 ? maxIndex : activeCandidateOptionIndex - 1;
    setActiveCandidateOptionIndex(nextIndex);
    return;
  }

  if (isEnter && activeCandidateOptionIndex >= 0) {
    event.preventDefault();
    const selected = visibleCandidateOptions[activeCandidateOptionIndex];
    if (selected?.id) selectCandidateById(selected.id);
    return;
  }

  if (isEscape) {
    event.preventDefault();
    hideCandidateSearchDropdown();
  }
});
linkCandidateSearch?.addEventListener("blur", () => {
  syncCandidateIdFromInput();
  if (candidateSearchBlurTimer) {
    window.clearTimeout(candidateSearchBlurTimer);
  }
  candidateSearchBlurTimer = window.setTimeout(() => {
    hideCandidateSearchDropdown();
    candidateSearchBlurTimer = null;
  }, 120);
});
candidateSearchDropdown?.addEventListener("mousedown", (event) => {
  event.preventDefault();
});
candidateSearchDropdown?.addEventListener("click", (event) => {
  const optionEl = event.target?.closest?.("[data-candidate-id]");
  if (!optionEl) return;
  const candidateId = String(optionEl.dataset.candidateId || "").trim();
  if (!candidateId) return;
  selectCandidateById(candidateId);
  syncCandidateIdFromInput();
});
linkResult?.addEventListener("change", () => {
  syncWinnerDetailVisibility({ autofill: true, clearWhenHidden: true });
});
linkElectionId?.addEventListener("change", () => {
  syncWinnerDetailVisibility({ autofill: true, clearWhenHidden: false });
});

document.addEventListener("DOMContentLoaded", async () => {
  if (window.location.pathname !== "/election") return;

  resetElectionEditState();
  resetCandidateElectionEditState();
  syncWinnerDetailVisibility({ autofill: true, clearWhenHidden: true });
  bindTabEvents();
  setActiveAdminTab("election");

  try {
    await refreshAllElectionAdminData();
    setMessage("선거 등록 페이지가 준비되었습니다.", "success");
  } catch (error) {
    setMessage(error.message || "초기 로딩 실패", "error");
  }
});
