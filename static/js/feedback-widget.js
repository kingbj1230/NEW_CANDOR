(() => {
  function byId(id) {
    return document.getElementById(id);
  }

  function isLoggedIn() {
    return Boolean(window.APP_CONTEXT?.userId);
  }

  async function apiPost(url, body) {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const payload = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(payload.error || "\uC694\uCCAD\uC5D0 \uC2E4\uD328\uD588\uC2B5\uB2C8\uB2E4.");
    return payload;
  }

  function initFeedbackWidget() {
    const fabBtn = byId("feedbackFabBtn");
    const modal = byId("feedbackModal");
    const form = byId("feedbackForm");
    const reasonInput = byId("feedbackReasonText");
    const categoryInput = byId("feedbackReasonCategory");
    const targetUrlInput = byId("feedbackTargetUrl");
    const submitBtn = byId("feedbackSubmitBtn");
    if (!fabBtn || !modal || !form || !reasonInput || !categoryInput || !targetUrlInput || !submitBtn) return;

    const state = {
      reportType: "\uC758\uACAC",
      candidateId: null,
      pledgeId: null,
    };

    function setTargetUrl(url) {
      targetUrlInput.value = String(url || window.location.href || "").trim();
    }

    function openModal(options = {}) {
      state.reportType = String(options.reportType || "\uC758\uACAC").trim() || "\uC758\uACAC";
      state.candidateId = options.candidateId || null;
      state.pledgeId = options.pledgeId || null;
      categoryInput.value =
        String(options.reasonCategory || "\uAE30\uB2A5 \uAC1C\uC120").trim() || "\uAE30\uB2A5 \uAC1C\uC120";
      reasonInput.value = String(options.reason || "").trim();
      setTargetUrl(options.targetUrl || window.location.href);
      modal.hidden = false;
      document.body.style.overflow = "hidden";
      setTimeout(() => reasonInput.focus(), 30);
    }

    function closeModal() {
      modal.hidden = true;
      document.body.style.overflow = "";
      form.reset();
      setTargetUrl(window.location.href);
      state.reportType = "\uC758\uACAC";
      state.candidateId = null;
      state.pledgeId = null;
    }

    async function submitFeedback(event) {
      event.preventDefault();
      const reason = reasonInput.value.trim();
      if (!reason) {
        alert("\uB0B4\uC6A9\uC744 \uC785\uB825\uD574 \uC8FC\uC138\uC694.");
        reasonInput.focus();
        return;
      }

      if (!isLoggedIn()) {
        alert("\uB85C\uADF8\uC778 \uD6C4 \uC774\uC6A9\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.");
        window.location.href = "/login";
        return;
      }

      submitBtn.disabled = true;
      const previousText = submitBtn.textContent;
      submitBtn.textContent = "\uC804\uC1A1 \uC911...";
      try {
        await apiPost("/api/report", {
          reason,
          reason_category: categoryInput.value || "\uAE30\uD0C0",
          report_type: state.reportType || "\uC758\uACAC",
          candidate_id: state.candidateId,
          pledge_id: state.pledgeId,
          target_url: targetUrlInput.value || window.location.href,
        });
        closeModal();
        alert("\uC758\uACAC\uC774 \uC811\uC218\uB418\uC5C8\uC2B5\uB2C8\uB2E4.");
      } catch (error) {
        alert(error.message || "\uC758\uACAC \uC811\uC218\uC5D0 \uC2E4\uD328\uD588\uC2B5\uB2C8\uB2E4.");
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = previousText;
      }
    }

    fabBtn.addEventListener("click", () => openModal());
    modal.addEventListener("click", (event) => {
      if (event.target.closest("[data-feedback-close]")) closeModal();
    });
    form.addEventListener("submit", submitFeedback);
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (!modal.hidden) closeModal();
    });
    setTargetUrl(window.location.href);

    window.openFeedbackModal = openModal;
  }

  document.addEventListener("DOMContentLoaded", initFeedbackWidget);
})();
