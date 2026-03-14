const messageEl = document.getElementById("candidateMessage");
const electionForm = document.getElementById("electionForm");
const electionList = document.getElementById("electionList");
const refreshElectionsBtn = document.getElementById("refreshElectionsBtn");
const saveElectionBtn = document.getElementById("saveElectionBtn");

const candidateElectionForm = document.getElementById("candidateElectionForm");
const candidateElectionList = document.getElementById("candidateElectionList");
const refreshCandidateElectionsBtn = document.getElementById("refreshCandidateElectionsBtn");
const saveCandidateElectionBtn = document.getElementById("saveCandidateElectionBtn");

const linkCandidateId = document.getElementById("linkCandidateId");
const linkElectionId = document.getElementById("linkElectionId");

const tabButtons = Array.from(document.querySelectorAll("[data-admin-tab-target]"));
const tabPanels = Array.from(document.querySelectorAll("[data-admin-tab-panel]"));

let candidateRows = [];
let electionRows = [];

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

function toDateLabel(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString("ko-KR");
}

function populateSelect(selectEl, rows, placeholder, labelMaker) {
  if (!selectEl) return;

  const options = rows.map((row) => `<option value="${row.id}">${labelMaker(row)}</option>`).join("");
  selectEl.innerHTML = `<option value="">${placeholder}</option>${options}`;
}

function renderElections(rows) {
  if (!electionList) return;

  if (!rows.length) {
    electionList.innerHTML = '<p class="empty">아직 등록된 선거가 없습니다.</p>';
    return;
  }

  electionList.innerHTML = rows
    .map((row) => {
      const createdAt = toDateLabel(row.created_at);
      const electionDate = row.election_date || "-";

      return `
      <article class="election-card">
        <span class="tag">${row.election_type || "-"}</span>
        <h3 class="card-title">${row.title || "-"}</h3>
        <p class="card-sub">선거일: ${electionDate}</p>
        <div class="card-meta">등록자: ${row.created_by || "-"} · ${createdAt} 생성</div>
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
      const candidate = candidateMap.get(String(row.candidate_id));
      const election = electionMap.get(String(row.election_id));
      const candidateName = candidate?.name || `후보자 ID ${row.candidate_id}`;
      const electionTitle = election?.title || `선거 ID ${row.election_id}`;
      const electionType = election?.election_type || "유형 미지정";
      const createdAt = toDateLabel(row.created_at);
      const isElectText = row.is_elect ? "당선(1)" : "비당선(0)";

      return `
      <article class="election-card relation-card">
        <span class="tag">${row.result || "-"}</span>
        <h3 class="card-title">${candidateName}</h3>
        <p class="card-sub">${electionType} · ${electionTitle}</p>
        <p class="card-sub">정당: ${row.party || "-"} · 기호: ${row.candidate_number || "-"}</p>
        <div class="card-meta">${isElectText} · 등록자: ${row.created_by || "-"} · ${createdAt} 생성</div>
      </article>
    `;
    })
    .join("");
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
  const [candidatesResp, electionsResp, linksResp] = await Promise.all([
    apiGet("/api/candidate-admin/candidates"),
    apiGet("/api/candidate-admin/elections"),
    apiGet("/api/candidate-admin/candidate-elections"),
  ]);

  candidateRows = candidatesResp.rows || [];
  electionRows = electionsResp.rows || [];

  populateSelect(linkCandidateId, candidateRows, "후보자를 선택해 주세요", (row) => `${row.name || "이름 없음"} (ID ${row.id})`);
  populateSelect(linkElectionId, electionRows, "선거를 선택해 주세요", (row) => `${row.title || "제목 없음"} (${row.election_date || "일자 미지정"})`);

  renderElections(electionRows);
  renderCandidateElections(linksResp.rows || []);
}

electionForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage("선거 저장 중...", "info");
  if (saveElectionBtn) saveElectionBtn.disabled = true;

  try {
    const formData = new FormData(electionForm);
    await apiPost("/api/candidate-admin/elections", {
      election_type: (formData.get("election_type") || "").trim(),
      title: (formData.get("title") || "").trim(),
      election_date: formData.get("election_date"),
    });

    electionForm.reset();
    await refreshAllElectionAdminData();
    setMessage("선거가 저장되었습니다.", "success");
  } catch (error) {
    setMessage(error.message || "선거 저장 실패", "error");
  } finally {
    if (saveElectionBtn) saveElectionBtn.disabled = false;
  }
});

candidateElectionForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage("선거 후보 저장 중...", "info");
  if (saveCandidateElectionBtn) saveCandidateElectionBtn.disabled = true;

  try {
    const formData = new FormData(candidateElectionForm);
    const candidateNumberRaw = formData.get("candidate_number");
    const result = String(formData.get("result") || "").trim();

    await apiPost("/api/candidate-admin/candidate-elections", {
      candidate_id: formData.get("candidate_id"),
      election_id: formData.get("election_id"),
      party: (formData.get("party") || "").trim(),
      result,
      candidate_number: Number(candidateNumberRaw),
    });

    candidateElectionForm.reset();
    await refreshAllElectionAdminData();
    setMessage("선거 후보 정보가 저장되었습니다.", "success");
  } catch (error) {
    setMessage(error.message || "선거 후보 저장 실패", "error");
  } finally {
    if (saveCandidateElectionBtn) saveCandidateElectionBtn.disabled = false;
  }
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

document.addEventListener("DOMContentLoaded", async () => {
  if (window.location.pathname !== "/election") return;

  bindTabEvents();
  setActiveAdminTab("election");

  try {
    await refreshAllElectionAdminData();
    setMessage("선거 등록 페이지가 준비되었습니다.", "success");
  } catch (error) {
    setMessage(error.message || "초기 로딩 실패", "error");
  }
});
