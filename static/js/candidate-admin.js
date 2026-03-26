const messageEl = document.getElementById("candidateMessage");

const candidateForm = document.getElementById("candidateForm");
const candidateList = document.getElementById("candidateList");
const refreshCandidatesBtn = document.getElementById("refreshCandidatesBtn");
const saveCandidateBtn = document.getElementById("saveCandidateBtn");

const termForm = document.getElementById("termForm");
const termList = document.getElementById("termList");
const termWinnerPair = document.getElementById("termWinnerPair");
const termPositionInput = document.getElementById("termPosition");
const termStartInput = document.getElementById("termStart");
const termEndInput = document.getElementById("termEnd");
const saveTermBtn = document.getElementById("saveTermBtn");
const refreshTermsBtn = document.getElementById("refreshTermsBtn");

const tabButtons = Array.from(document.querySelectorAll("[data-admin-tab-target]"));
const tabPanels = Array.from(document.querySelectorAll("[data-admin-tab-panel]"));

let candidateRows = [];
let electionRows = [];
let electedPairs = [];

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

async function uploadImage(file) {
  const formData = new FormData();
  formData.append("image", file);

  const resp = await fetch("/api/upload-image", { method: "POST", body: formData });
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.error || "이미지 업로드 실패");
  return payload.path;
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

function toDateInputValue(value) {
  const text = String(value || "").trim();
  const match = text.match(/^(\d{4}-\d{2}-\d{2})/);
  return match ? match[1] : "";
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

function applyTermAutofillFromWinnerPair() {
  if (!termWinnerPair) return;

  const winnerPair = String(termWinnerPair.value || "");
  const [, electionId] = winnerPair.split("::");
  if (!electionId) {
    if (termPositionInput) termPositionInput.value = "";
    if (termStartInput) termStartInput.value = "";
    if (termEndInput) termEndInput.value = "";
    return;
  }

  const electionMap = new Map(electionRows.map((row) => [String(row.id), row]));
  const election = electionMap.get(String(electionId));
  if (!election) return;

  const electionType = String(election.election_type || "").trim();
  const electionDate = parseDateLike(election.election_date);

  if (termPositionInput) {
    termPositionInput.value = electionType;
  }

  if (!electionDate) {
    if (termStartInput) termStartInput.value = "";
    if (termEndInput) termEndInput.value = "";
    return;
  }

  const termStart = addDaysUtc(electionDate, 1);
  if (termStartInput) {
    termStartInput.value = formatDateInput(termStart);
  }

  const years = inferTermYears(electionType);
  if (termEndInput) {
    if (!years) {
      termEndInput.value = "";
    } else {
      // 임기 시작일 기준으로 N년 후 하루 전까지
      const termEnd = addDaysUtc(addYearsUtc(termStart, years), -1);
      termEndInput.value = formatDateInput(termEnd);
    }
  }
}

function isElectTrue(value) {
  return value === true || value === 1 || value === "1" || value === "t";
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

function renderCandidates(rows) {
  if (!candidateList) return;

  if (!rows.length) {
    candidateList.innerHTML = '<p class="empty">아직 등록된 후보자가 없습니다.</p>';
    return;
  }

  candidateList.innerHTML = rows
    .map((row) => {
      const createdAt = toDateLabel(row.created_at);
      const age = calculateAgeFromBirthDate(row.birth_date);
      const ageText = age === null ? "나이 미상" : `현재 ${age}세`;
      const imageUrl = sanitizeUrl(row.image);
      const imageMarkup = imageUrl
        ? `<img class="candidate-avatar" src="${imageUrl}" alt="${escapeHtml(row.name || "후보자")}">`
        : '<div class="candidate-avatar placeholder">No Image</div>';

      return `
      <article class="candidate-card">
        <div class="candidate-media">${imageMarkup}</div>
        <div>
          <h3 class="card-title">${escapeHtml(row.name || "-")}</h3>
          <p class="card-sub">생년월일: ${escapeHtml(toDateLabel(row.birth_date))} · ${escapeHtml(ageText)}</p>
          <div class="card-meta">등록일: ${escapeHtml(createdAt)}</div>
        </div>
      </article>
    `;
    })
    .join("");
}

function buildElectedPairs(candidateElectionRows) {
  const seen = new Set();
  const rows = [];

  candidateElectionRows.forEach((row) => {
    if (!isElectTrue(row.is_elect)) return;

    const candidateId = String(row.candidate_id || "");
    const electionId = String(row.election_id || "");
    if (!candidateId || !electionId) return;

    const key = `${candidateId}::${electionId}`;
    if (seen.has(key)) return;
    seen.add(key);

    rows.push({
      candidate_id: candidateId,
      election_id: electionId,
    });
  });

  return rows;
}

function populateElectedPairSelect() {
  if (!termWinnerPair) return;

  const candidateMap = new Map(candidateRows.map((row) => [String(row.id), row]));
  const electionMap = new Map(electionRows.map((row) => [String(row.id), row]));

  if (!electedPairs.length) {
    termWinnerPair.innerHTML = '<option value="">당선 이력이 없습니다. 먼저 후보자 매칭에서 당선자를 등록해 주세요.</option>';
    if (saveTermBtn) saveTermBtn.disabled = true;
    return;
  }

  const options = electedPairs
    .map((pair) => {
      const candidate = candidateMap.get(String(pair.candidate_id));
      const election = electionMap.get(String(pair.election_id));
      const candidateName = candidate?.name || `후보자 ID ${pair.candidate_id}`;
      const electionTitle = election ? formatPresidentialElectionTitle(election.title) : `선거 ID ${pair.election_id}`;
      const electionDate = election?.election_date || "일자 미지정";
      return `<option value="${escapeHtml(pair.candidate_id)}::${escapeHtml(pair.election_id)}">${escapeHtml(candidateName)} - ${escapeHtml(electionTitle)} (${escapeHtml(electionDate)})</option>`;
    })
    .join("");

  termWinnerPair.innerHTML = `<option value="">당선 이력을 선택해 주세요</option>${options}`;
  if (saveTermBtn) saveTermBtn.disabled = false;
  applyTermAutofillFromWinnerPair();
}

function renderTerms(rows) {
  if (!termList) return;

  if (!rows.length) {
    termList.innerHTML = '<p class="empty">아직 등록된 당선 경력이 없습니다.</p>';
    return;
  }

  const candidateMap = new Map(candidateRows.map((row) => [String(row.id), row]));
  const electionMap = new Map(electionRows.map((row) => [String(row.id), row]));

  termList.innerHTML = rows
    .map((row) => {
      const candidate = candidateMap.get(String(row.candidate_id));
      const election = electionMap.get(String(row.election_id));
      const candidateName = candidate?.name || `후보자 ID ${row.candidate_id}`;
      const electionTitle = election ? formatPresidentialElectionTitle(election.title) : `선거 ID ${row.election_id}`;
      const termStart = row.term_start || "-";
      const termEnd = row.term_end || "진행 중";
      const createdAt = toDateLabel(row.created_at);

      return `
      <article class="election-card term-card">
        <span class="tag">${escapeHtml(row.position || "직책 미지정")}</span>
        <h3 class="card-title">${escapeHtml(candidateName)}</h3>
        <p class="card-sub">선거: ${escapeHtml(electionTitle)}</p>
        <p class="card-sub">임기: ${escapeHtml(termStart)} ~ ${escapeHtml(termEnd)}</p>
        <div class="card-meta">등록일: ${escapeHtml(createdAt)}</div>
      </article>
    `;
    })
    .join("");
}

async function refreshAllCandidateAdminData() {
  const [candidatesResp, electionsResp, candidateElectionsResp, termsResp] = await Promise.all([
    apiGet("/api/candidate-admin/candidates"),
    apiGet("/api/candidate-admin/elections"),
    apiGet("/api/candidate-admin/candidate-elections"),
    apiGet("/api/candidate-admin/terms"),
  ]);

  candidateRows = candidatesResp.rows || [];
  electionRows = electionsResp.rows || [];
  electedPairs = buildElectedPairs(candidateElectionsResp.rows || []);

  renderCandidates(candidateRows);
  populateElectedPairSelect();
  renderTerms(termsResp.rows || []);
}

candidateForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage("후보자 저장 중...", "info");
  if (saveCandidateBtn) saveCandidateBtn.disabled = true;

  try {
    const formData = new FormData(candidateForm);
    const name = (formData.get("name") || "").trim();
    const imageFile = formData.get("image");
    const birthDateRaw = String(formData.get("birth_date") || "").trim();
    const birthDate = toDateInputValue(birthDateRaw);

    if (!name || !imageFile) {
      throw new Error("이름과 이미지를 입력해 주세요.");
    }
    if (birthDateRaw && !birthDate) {
      throw new Error("생년월일 형식을 확인해 주세요. (YYYY-MM-DD)");
    }

    const imagePath = await uploadImage(imageFile);
    await apiPost("/api/candidate-admin/candidates", {
      name,
      image: imagePath,
      birth_date: birthDate || null,
    });

    candidateForm.reset();
    await refreshAllCandidateAdminData();
    setMessage("후보자가 저장되었습니다.", "success");
  } catch (error) {
    setMessage(error.message || "후보자 저장 실패", "error");
  } finally {
    if (saveCandidateBtn) saveCandidateBtn.disabled = false;
  }
});

termForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage("당선 경력 저장 중...", "info");
  if (saveTermBtn) saveTermBtn.disabled = true;

  try {
    const formData = new FormData(termForm);
    const winnerPair = String(formData.get("winner_pair") || "");
    const [candidateId, electionId] = winnerPair.split("::");
    const termStart = formData.get("term_start");
    const termEnd = formData.get("term_end");

    if (!candidateId || !electionId) {
      throw new Error("당선 이력을 선택해 주세요.");
    }

    if (termEnd && String(termEnd) < String(termStart)) {
      throw new Error("임기 종료일은 시작일 이후여야 합니다.");
    }

    await apiPost("/api/candidate-admin/terms", {
      candidate_id: candidateId,
      election_id: electionId,
      position: (formData.get("position") || "").trim(),
      term_start: termStart,
      term_end: termEnd || null,
    });

    termForm.reset();
    await refreshAllCandidateAdminData();
    setMessage("당선 경력이 저장되었습니다.", "success");
  } catch (error) {
    setMessage(error.message || "당선 경력 저장 실패", "error");
  } finally {
    if (saveTermBtn) saveTermBtn.disabled = false;
  }
});

termWinnerPair?.addEventListener("change", () => {
  applyTermAutofillFromWinnerPair();
});

refreshCandidatesBtn?.addEventListener("click", async () => {
  try {
    await refreshAllCandidateAdminData();
    setMessage("후보자 목록을 갱신했습니다.", "success");
  } catch (error) {
    setMessage(error.message || "후보자 조회 실패", "error");
  }
});

refreshTermsBtn?.addEventListener("click", async () => {
  try {
    await refreshAllCandidateAdminData();
    setMessage("당선 경력 목록을 갱신했습니다.", "success");
  } catch (error) {
    setMessage(error.message || "당선 경력 조회 실패", "error");
  }
});

document.addEventListener("DOMContentLoaded", async () => {
  if (window.location.pathname !== "/candidate") return;

  bindTabEvents();
  setActiveAdminTab("candidate");

  try {
    await refreshAllCandidateAdminData();
    setMessage("후보자 등록 페이지가 준비되었습니다.", "success");
  } catch (error) {
    setMessage(error.message || "초기 로딩 실패", "error");
  }
});
