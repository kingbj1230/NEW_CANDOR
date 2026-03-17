const MYPAGE_SUPABASE_URL = "https://txumpkghskgiprwqpigg.supabase.co";
const MYPAGE_SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR4dW1wa2doc2tnaXByd3FwaWdnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njc3NzU1MDksImV4cCI6MjA4MzM1MTUwOX0.kpChb4rlwOU_q8_q9DMn_0ZbOizhmwsjl4rjA9ZCQWk";

let mypageClient = null;
let currentUser = null;
let currentProfile = null;
let cachedCandidates = [];
let cachedPledges = [];
let cachedReports = [];
let candidateNameMap = new Map();
let candidateElectionMap = new Map();
let electionMap = new Map();
const REPORT_STATUS_OPTIONS = ["접수", "검토중", "처리완료", "반려"];

function getMypageClient() {
  if (!window.supabase) throw new Error("Supabase SDK가 로드되지 않았습니다.");
  if (!mypageClient) {
    mypageClient = window.supabase.createClient(MYPAGE_SUPABASE_URL, MYPAGE_SUPABASE_KEY);
  }
  return mypageClient;
}

function byId(id) {
  return document.getElementById(id);
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

function normalizeCandidateId(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  const lowered = text.toLowerCase();
  if (["undefined", "null", "none", "nan"].includes(lowered)) return "";
  return text;
}

function setMypageMessage(text, type = "info") {
  const el = byId("mypageMessage");
  if (!el) return;
  el.className = `mypage-message ${type}`;
  el.textContent = text;
}

function text(id, value) {
  const el = byId(id);
  if (!el) return;
  el.textContent = value ?? "-";
}

function formatDate(value, withTime = false) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

function isAdminRole(role) {
  const r = String(role || "").toLowerCase();
  return r === "admin" || r === "super_admin";
}

function roleLabel(role) {
  const r = String(role || "").toLowerCase();
  if (r === "super_admin") return "super_admin";
  if (r === "admin") return "admin";
  if (r) return r;
  return "-";
}

function setRoleBadge(role) {
  const el = byId("profileRole");
  if (!el) return;
  el.textContent = roleLabel(role);
  el.className = `role-badge${isAdminRole(role) ? " admin" : ""}`;
}

function activateTab(tabKey) {
  document.querySelectorAll("[data-mypage-tab]").forEach((btn) => {
    const isActive = btn.getAttribute("data-mypage-tab") === tabKey;
    btn.classList.toggle("is-active", isActive);
  });

  const panelMap = {
    profile: "mypagePanelProfile",
    candidates: "mypagePanelCandidates",
    pledges: "mypagePanelPledges",
    reports: "mypagePanelReports",
  };

  Object.values(panelMap).forEach((panelId) => {
    const panel = byId(panelId);
    if (!panel) return;
    panel.classList.remove("is-active");
  });

  const activePanel = byId(panelMap[tabKey]);
  if (activePanel) activePanel.classList.add("is-active");
}

function bindTabs() {
  document.querySelectorAll("[data-mypage-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      activateTab(btn.getAttribute("data-mypage-tab") || "profile");
    });
  });
}

async function resolveCurrentUser() {
  let userId = window.APP_CONTEXT?.userId || "";
  let email = window.APP_CONTEXT?.email || "";
  const client = getMypageClient();

  if (!userId) {
    const { data, error } = await client.auth.getUser();
    if (error || !data?.user?.id) throw new Error("로그인 사용자 정보를 확인하지 못했습니다.");
    userId = data.user.id;
    email = data.user.email || "";
  }

  currentUser = { id: userId, email };
}

async function fetchUserProfile(userId) {
  const client = getMypageClient();
  const attempts = [
    { idColumn: "user__id", createdColumn: "create_at", updatedColumn: "update_at" },
    { idColumn: "user_id", createdColumn: "create_at", updatedColumn: "update_at" },
    { idColumn: "user__id", createdColumn: "created_at", updatedColumn: "updated_at" },
    { idColumn: "user_id", createdColumn: "created_at", updatedColumn: "updated_at" },
  ];

  for (const attempt of attempts) {
    const { data, error } = await client
      .from("user_profiles")
      .select(`${attempt.idColumn}, nickname, role, status, ${attempt.createdColumn}, ${attempt.updatedColumn}, reputation_score`)
      .eq(attempt.idColumn, userId)
      .maybeSingle();

    if (!error) {
      return data
        ? {
            ...data,
            created_at: data[attempt.createdColumn],
            updated_at: data[attempt.updatedColumn],
          }
        : null;
    }

    if (!String(error.message || "").includes("column")) {
      throw new Error(error.message || "프로필 조회 실패");
    }
  }

  throw new Error("user_profiles 컬럼명을 확인해 주세요.");
}

async function fetchMyCandidates(userId) {
  const { data, error } = await getMypageClient()
    .from("candidates")
    .select("id,name,image,created_at,created_by,updated_at,updated_by")
    .eq("created_by", userId)
    .order("created_at", { ascending: false });

  if (error) throw new Error(error.message || "후보자 조회 실패");
  return data || [];
}

async function fetchMyPledges(userId) {
  const { data, error } = await getMypageClient()
    .from("pledges")
    .select("id,candidate_election_id,sort_order,title,raw_text,category,status,created_at,created_by,updated_at,updated_by")
    .eq("created_by", userId)
    .order("created_at", { ascending: false });

  if (error) throw new Error(error.message || "공약 조회 실패");
  return (data || []).filter((row) => String(row?.status || "active") !== "deleted");
}

async function fetchCandidateElectionMap(candidateElectionIds) {
  if (!candidateElectionIds.length) return new Map();
  const { data, error } = await getMypageClient()
    .from("candidate_elections")
    .select("id,candidate_id,election_id,party,result,candidate_number")
    .in("id", candidateElectionIds);

  if (error) throw new Error(error.message || "후보-선거 매칭 조회 실패");
  return new Map((data || []).map((row) => [String(row.id), row]));
}

async function fetchCandidateNameMap(candidateIds) {
  if (!candidateIds.length) return new Map();
  const { data, error } = await getMypageClient().from("candidates").select("id,name").in("id", candidateIds);
  if (error) throw new Error(error.message || "후보자 이름 조회 실패");
  return new Map((data || []).map((row) => [String(row.id), row.name || "이름 없음"]));
}

async function fetchElectionMap(electionIds) {
  if (!electionIds.length) return new Map();
  const { data, error } = await getMypageClient()
    .from("elections")
    .select("id,election_type,title,election_date")
    .in("id", electionIds);

  if (error) throw new Error(error.message || "선거 정보 조회 실패");
  return new Map((data || []).map((row) => [String(row.id), row]));
}

async function fetchAdminReports() {
  const payload = await apiGet("/api/mypage/reports");
  return payload.reports || [];
}

function renderSummary() {
  text("summaryCandidateCount", String(cachedCandidates.length));
  text("summaryPledgeCount", String(cachedPledges.length));
  text("summaryRole", roleLabel(currentProfile?.role));

  const reportCard = byId("summaryReportCard");
  if (!reportCard) return;

  if (isAdminRole(currentProfile?.role)) {
    reportCard.hidden = false;
    text("summaryReportCount", String(cachedReports.length));
  } else {
    reportCard.hidden = true;
  }
}

function renderProfile() {
  text("profileNickname", currentProfile?.nickname || "-");
  text("profileEmail", currentUser?.email || "-");
  setRoleBadge(currentProfile?.role || "-");
  text("profileStatus", currentProfile?.status || "-");
  text("profileCreatedAt", formatDate(currentProfile?.created_at));
  text("profileReputation", String(currentProfile?.reputation_score ?? "-"));
}

function renderCandidates() {
  const list = byId("myCandidateList");
  const count = byId("myCandidateCount");
  if (!list || !count) return;

  count.textContent = `${cachedCandidates.length}건`;

  if (!cachedCandidates.length) {
    list.innerHTML = "<li><p class='item-meta'>등록한 후보자가 없습니다.</p></li>";
    return;
  }

  list.innerHTML = cachedCandidates
    .map((item) => {
      const candidateId = normalizeCandidateId(item.id);
      const detailHref = candidateId ? `/politicians/${encodeURIComponent(candidateId)}` : "";
      return `
      <li>
        <div class="item-row">
          <div class="item-main">
            <p class="item-title">${escapeHtml(item.name || "-")}</p>
            <p class="item-meta">등록일: ${escapeHtml(formatDate(item.created_at, true))}</p>
          </div>
          <div class="item-actions">
            <button type="button" class="mypage-action-btn" data-action="edit-candidate" data-id="${escapeHtml(item.id)}">수정</button>
            ${detailHref ? `<a class="mypage-action-link" href="${detailHref}">상세</a>` : ""}
          </div>
        </div>
      </li>`;
    })
    .join("");
}

function getPledgeContext(item) {
  const candidateElection = candidateElectionMap.get(String(item.candidate_election_id)) || {};
  const candidateId = normalizeCandidateId(candidateElection.candidate_id) || null;
  const candidateName = candidateId ? candidateNameMap.get(String(candidateId)) || "후보자 정보 없음" : "후보자 정보 없음";
  const election = electionMap.get(String(candidateElection.election_id)) || {};
  const electionParts = [election.election_type, election.title, formatDate(election.election_date)]
    .map((v) => String(v || "").trim())
    .filter(Boolean);
  return {
    candidateId,
    candidateName,
    electionText: electionParts.length ? electionParts.join(" · ") : "선거 정보 없음",
  };
}

function renderPledges() {
  const list = byId("myPledgeList");
  const count = byId("myPledgeCount");
  if (!list || !count) return;

  count.textContent = `${cachedPledges.length}건`;

  if (!cachedPledges.length) {
    list.innerHTML = "<li><p class='item-meta'>등록한 공약이 없습니다.</p></li>";
    return;
  }

  list.innerHTML = cachedPledges
    .map((item) => {
      const context = getPledgeContext(item);
      const detailHref =
        context.candidateId
          ? `/politicians/${encodeURIComponent(context.candidateId)}?ce=${encodeURIComponent(item.candidate_election_id)}&pledge=${encodeURIComponent(item.id)}`
          : "";

      return `
      <li>
        <div class="item-row">
          <div class="item-main">
            <p class="item-title">#${escapeHtml(item.sort_order || "-")} ${escapeHtml(item.title || "-")}</p>
            <p class="item-meta">${escapeHtml(context.candidateName)} · ${escapeHtml(context.electionText)}</p>
            <p class="item-meta">카테고리: ${escapeHtml(item.category || "미분류")} · 상태: ${escapeHtml(item.status || "active")} · 등록일: ${escapeHtml(formatDate(item.created_at, true))}</p>
          </div>
          <div class="item-actions">
            <button type="button" class="mypage-action-btn" data-action="edit-pledge" data-id="${escapeHtml(item.id)}">수정</button>
            ${detailHref ? `<a class="mypage-action-link" href="${detailHref}">상세</a>` : ""}
          </div>
        </div>
      </li>`;
    })
    .join("");
}

function renderAdminReports() {
  const tabButton = byId("adminReportTabBtn");
  const panel = byId("mypagePanelReports");
  const list = byId("adminReportList");
  const count = byId("adminReportCount");

  if (!tabButton || !panel || !list || !count) return;

  if (!isAdminRole(currentProfile?.role)) {
    tabButton.hidden = true;
    panel.hidden = true;
    if (panel.classList.contains("is-active")) activateTab("profile");
    return;
  }

  tabButton.hidden = false;
  panel.hidden = false;
  count.textContent = `${cachedReports.length}건`;

  if (!cachedReports.length) {
    list.innerHTML = "<li><p class='item-meta'>접수된 신고가 없습니다.</p></li>";
    return;
  }

  list.innerHTML = cachedReports
    .map((r) => {
      const statusValue = String(r.status || "접수");
      const statusOptions = REPORT_STATUS_OPTIONS.map(
        (status) => `<option value="${escapeHtml(status)}" ${statusValue === status ? "selected" : ""}>${escapeHtml(status)}</option>`
      ).join("");
      const targetUrl = sanitizeUrl(r.target_url);
      const targetUrlMarkup = targetUrl
        ? `<a class="mypage-report-link" href="${escapeHtml(targetUrl)}" target="_blank" rel="noopener noreferrer">대상 페이지 열기</a>`
        : '<span class="item-meta">대상 URL 없음</span>';

      return `
      <li class="report-item" data-report-id="${escapeHtml(r.id)}">
        <div class="item-row">
          <div class="item-main">
            <p class="item-title">[${escapeHtml(r.target_type || "의견")}] ${escapeHtml(r.target_name || "대상 없음")}</p>
            <p class="item-meta">유형: ${escapeHtml(r.report_type || "신고")} · 분류: ${escapeHtml(r.reason_category || "미지정")} · 신고자: ${escapeHtml(r.user_id || "-")}</p>
            <p class="item-meta">접수: ${escapeHtml(formatDate(r.created_at, true))} · 최종수정: ${escapeHtml(formatDate(r.updated_at, true))} · 해결일: ${escapeHtml(formatDate(r.resolved_at, true))}</p>
            <p class="item-meta">사유: ${escapeHtml(r.reason || "-")}</p>
            ${targetUrlMarkup}
          </div>
        </div>
        <div class="report-controls">
          <label>상태
            <select class="mypage-report-status">${statusOptions}</select>
          </label>
          <label>관리자 메모
            <textarea class="mypage-report-note" rows="2" placeholder="검토 메모를 입력해 주세요.">${escapeHtml(r.admin_note || "")}</textarea>
          </label>
          <button type="button" class="mypage-action-btn" data-action="save-report">저장</button>
        </div>
      </li>`;
    })
    .join("");
}

function openModal(modalEl) {
  if (!modalEl) return;
  modalEl.hidden = false;
  document.body.style.overflow = "hidden";
}

function closeModal(modalEl) {
  if (!modalEl) return;
  modalEl.hidden = true;
  document.body.style.overflow = "";
}

function openCandidateEditModal(candidateId) {
  const item = cachedCandidates.find((row) => String(row.id) === String(candidateId));
  if (!item) return;

  byId("candidateEditId").value = item.id || "";
  byId("candidateEditName").value = item.name || "";
  byId("candidateEditImage").value = item.image || "";
  openModal(byId("candidateEditModal"));
}

function openPledgeEditModal(pledgeId) {
  const item = cachedPledges.find((row) => String(row.id) === String(pledgeId));
  if (!item) return;

  byId("pledgeEditId").value = item.id || "";
  byId("pledgeEditCandidateElectionId").value = item.candidate_election_id || "";
  byId("pledgeEditSortOrder").value = item.sort_order || 1;
  byId("pledgeEditTitle").value = item.title || "";
  byId("pledgeEditCategory").value = item.category || "";
  byId("pledgeEditStatus").value = item.status || "active";
  byId("pledgeEditRawText").value = item.raw_text || "";
  openModal(byId("pledgeEditModal"));
}

function bindModalEvents() {
  document.querySelectorAll("[data-modal-close]").forEach((el) => {
    el.addEventListener("click", () => {
      closeModal(byId("candidateEditModal"));
      closeModal(byId("pledgeEditModal"));
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeModal(byId("candidateEditModal"));
    closeModal(byId("pledgeEditModal"));
  });
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

async function apiGet(url) {
  const resp = await fetch(url);
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.error || "요청 실패");
  return payload;
}

async function saveAdminReport(reportId, status, adminNote) {
  await apiPatch(`/api/mypage/reports/${encodeURIComponent(reportId)}`, {
    status,
    admin_note: adminNote,
  });
}

function bindListActions() {
  byId("myCandidateList")?.addEventListener("click", (event) => {
    const editBtn = event.target.closest("button[data-action='edit-candidate']");
    if (editBtn) openCandidateEditModal(editBtn.getAttribute("data-id"));
  });

  byId("myPledgeList")?.addEventListener("click", (event) => {
    const editBtn = event.target.closest("button[data-action='edit-pledge']");
    if (editBtn) openPledgeEditModal(editBtn.getAttribute("data-id"));
  });

  byId("adminReportList")?.addEventListener("click", async (event) => {
    const saveBtn = event.target.closest("button[data-action='save-report']");
    if (!saveBtn) return;

    const item = saveBtn.closest(".report-item");
    const reportId = item?.getAttribute("data-report-id");
    const status = item?.querySelector(".mypage-report-status")?.value || "접수";
    const adminNote = item?.querySelector(".mypage-report-note")?.value || "";
    if (!reportId) return;

    try {
      saveBtn.disabled = true;
      await saveAdminReport(reportId, status, adminNote);
      await loadMypageData();
      setMypageMessage("신고 처리 내용을 저장했습니다.", "success");
    } catch (error) {
      setMypageMessage(error.message || "신고 저장 실패", "error");
    } finally {
      saveBtn.disabled = false;
    }
  });
}

function bindEditForms() {
  byId("candidateEditForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = byId("candidateEditId").value;
    const name = byId("candidateEditName").value.trim();
    const image = byId("candidateEditImage").value.trim();

    if (!name) {
      setMypageMessage("후보자 이름은 필수입니다.", "error");
      return;
    }

    try {
      const original = cachedCandidates.find((row) => String(row.id) === String(id));
      const payload = {
        name,
      };
      if (image || original?.image) {
        payload.image = image || original.image;
      }

      await apiPatch(`/api/mypage/candidates/${encodeURIComponent(id)}`, payload);
      closeModal(byId("candidateEditModal"));
      await loadMypageData();
      setMypageMessage("후보자 정보를 수정했습니다.", "success");
    } catch (error) {
      setMypageMessage(error.message || "후보자 수정 실패", "error");
    }
  });

  byId("pledgeEditForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = byId("pledgeEditId").value;
    const candidateElectionId = byId("pledgeEditCandidateElectionId").value.trim();
    const sortOrderRaw = byId("pledgeEditSortOrder").value;
    const title = byId("pledgeEditTitle").value.trim();
    const category = byId("pledgeEditCategory").value.trim();
    const status = byId("pledgeEditStatus").value.trim() || "active";
    const rawText = byId("pledgeEditRawText").value.trim();

    const sortOrder = Number(sortOrderRaw);
    if (!Number.isInteger(sortOrder) || sortOrder < 1) {
      setMypageMessage("정렬 순서는 1 이상의 숫자여야 합니다.", "error");
      return;
    }
    if (!candidateElectionId || !title || !category || !rawText) {
      setMypageMessage("필수 항목을 입력해 주세요.", "error");
      return;
    }

    try {
      await apiPatch(`/api/mypage/pledges/${encodeURIComponent(id)}`, {
        candidate_election_id: candidateElectionId,
        sort_order: sortOrder,
        title,
        raw_text: rawText,
        category,
        status,
      });
      closeModal(byId("pledgeEditModal"));
      await loadMypageData();
      setMypageMessage("공약을 수정했습니다.", "success");
    } catch (error) {
      setMypageMessage(error.message || "공약 수정 실패", "error");
    }
  });
}

async function loadMypageData() {
  await resolveCurrentUser();
  currentProfile = await fetchUserProfile(currentUser.id);

  const [candidates, pledges] = await Promise.all([
    fetchMyCandidates(currentUser.id),
    fetchMyPledges(currentUser.id),
  ]);
  cachedCandidates = candidates;
  cachedPledges = pledges;

  const candidateElectionIds = Array.from(new Set(cachedPledges.map((p) => p.candidate_election_id).filter(Boolean)));
  candidateElectionMap = await fetchCandidateElectionMap(candidateElectionIds);

  const candidateIdsFromPledges = Array.from(
    new Set(
      cachedPledges
        .map((p) => candidateElectionMap.get(String(p.candidate_election_id))?.candidate_id)
        .filter(Boolean)
    )
  );
  const allCandidateIds = Array.from(new Set([...candidateIdsFromPledges, ...cachedCandidates.map((c) => c.id).filter(Boolean)]));
  candidateNameMap = await fetchCandidateNameMap(allCandidateIds);

  const electionIds = Array.from(
    new Set(
      Array.from(candidateElectionMap.values())
        .map((row) => row.election_id)
        .filter(Boolean)
    )
  );
  electionMap = await fetchElectionMap(electionIds);

  if (isAdminRole(currentProfile?.role)) {
    cachedReports = await fetchAdminReports();
  } else {
    cachedReports = [];
  }

  renderProfile();
  renderCandidates();
  renderPledges();
  renderAdminReports();
  renderSummary();
}

document.addEventListener("DOMContentLoaded", () => {
  if (window.location.pathname !== "/mypage") return;

  bindTabs();
  bindListActions();
  bindModalEvents();
  bindEditForms();
  activateTab("profile");

  setMypageMessage("마이페이지 데이터를 불러오는 중입니다...", "info");
  loadMypageData()
    .then(() => setMypageMessage("마이페이지를 불러왔습니다.", "success"))
    .catch((error) => setMypageMessage(error.message || "마이페이지 로딩 실패", "error"));
});
