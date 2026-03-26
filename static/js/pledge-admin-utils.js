(function attachPledgeAdminUtils() {
  function setMessage(messageEl, text, type = "info") {
    if (!messageEl) return;
    messageEl.className = `pledge-message ${type}`;
    messageEl.textContent = text;
  }

  function setLoading(state, loadingEl, loadingTextEl, isLoading, text = "처리 중입니다. 잠시만 기다려 주세요...") {
    if (!loadingEl) return;
    if (isLoading) {
      state.loadingCount += 1;
      if (loadingTextEl) loadingTextEl.textContent = text;
      loadingEl.hidden = false;
      return;
    }
    state.loadingCount = Math.max(0, state.loadingCount - 1);
    if (state.loadingCount === 0) loadingEl.hidden = true;
  }

  async function apiGet(url) {
    const resp = await fetch(url);
    const payload = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(payload.error || "요청에 실패했습니다.");
    return payload;
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

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function normalizeSortOrder(value) {
    if (value === undefined || value === null || String(value).trim() === "") return null;
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed < 1) {
      throw new Error("정렬 순서는 1 이상의 숫자여야 합니다.");
    }
    return Math.floor(parsed);
  }

  function normalizeHttpUrl(value) {
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

  function toDateLabel(value) {
    const text = String(value || "").trim();
    if (!text) return "날짜 미정";
    const date = new Date(text);
    if (Number.isNaN(date.getTime())) return text;
    return date.toLocaleDateString("ko-KR");
  }

  function normalizeElectionTitle(value) {
    const text = String(value || "").trim();
    if (!/^\d+$/.test(text)) return text || "선거";
    return `제${Number(text)}대 대통령 선거`;
  }

  function buildElectionLabel(row) {
    return `${normalizeElectionTitle(row?.title)} (${toDateLabel(row?.election_date)})`;
  }

  function sortByRecentElection(a, b) {
    const aDate = String(a?.election_date || "");
    const bDate = String(b?.election_date || "");
    return bDate.localeCompare(aDate);
  }

  function sortByName(a, b) {
    const aName = String(a?.name || "");
    const bName = String(b?.name || "");
    return aName.localeCompare(bName, "ko");
  }

  window.PledgeAdminUtils = {
    setMessage,
    setLoading,
    apiGet,
    apiPost,
    escapeHtml,
    normalizeSortOrder,
    normalizeHttpUrl,
    toDateLabel,
    normalizeElectionTitle,
    buildElectionLabel,
    sortByRecentElection,
    sortByName,
  };
})();
