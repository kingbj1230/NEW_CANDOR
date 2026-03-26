(function attachPledgeAdminPreview() {
  const utils = window.PledgeAdminUtils || {};

  function displayParseType(type) {
    if (type === "type1") return "type1 (①②③)";
    if (type === "type2") return "type2 (□ ○ -)";
    if (type === "type3") return "type3 (단순 리스트)";
    return "미감지";
  }

  function renderList(container, items) {
    if (!container) return;
    const rows = Array.isArray(items) ? items.filter((v) => String(v || "").trim()) : [];
    if (!rows.length) {
      container.innerHTML = '<p class="preview-empty">분석된 내용이 없습니다.</p>';
      return;
    }
    container.innerHTML = `<ul class="preview-list">${rows
      .map((row) => `<li>${utils.escapeHtml(row)}</li>`)
      .join("")}</ul>`;
  }

  function renderStrategies(container, strategies) {
    if (!container) return;
    const rows = Array.isArray(strategies) ? strategies : [];
    if (!rows.length) {
      container.innerHTML = '<p class="preview-empty">분석된 내용이 없습니다.</p>';
      return;
    }

    container.innerHTML = rows
      .map((strategy) => {
        const title = String(strategy?.title || "").trim() || "(제목 없음)";
        const actions = Array.isArray(strategy?.actions)
          ? strategy.actions.filter((v) => String(v || "").trim())
          : [];

        const actionHtml = actions.length
          ? `<ul class="strategy-actions">${actions
              .map((action) => `<li>${utils.escapeHtml(action)}</li>`)
              .join("")}</ul>`
          : '<p class="preview-empty">실행항목이 없습니다.</p>';

        return `
          <article class="strategy-card">
            <p class="strategy-title">${utils.escapeHtml(title)}</p>
            ${actionHtml}
          </article>
        `;
      })
      .join("");
  }

  function getGoalTargetOptions(parsedModel) {
    const parsed = parsedModel?.parsed || {};
    const options = [];
    let index = 1;

    if ((parsed.goals || []).length) {
      options.push({ value: `g:${index}`, label: "목표" });
      index += 1;
    }

    if ((parsed.strategies || []).length) {
      options.push({ value: `g:${index}`, label: "이행방법" });
    }

    return options;
  }

  function renderParsedPreview(parsedModel, dom) {
    const parsed = parsedModel?.parsed || {};
    if (dom.detectedTypeEl) dom.detectedTypeEl.textContent = displayParseType(parsed.parse_type);

    if (dom.warningTextEl) {
      dom.warningTextEl.textContent = (parsed.warnings || []).length
        ? `경고: ${parsed.warnings[0]}`
        : "정상";
    }

    renderList(dom.goalsBoxEl, parsed.goals || []);
    renderStrategies(dom.strategiesBoxEl, parsed.strategies || []);
    renderList(dom.timelineBoxEl, parsed.timeline || []);
    renderList(dom.financeBoxEl, parsed.finance || []);

    if (dom.jsonBoxEl) {
      dom.jsonBoxEl.textContent = JSON.stringify(parsed, null, 2);
    }
  }

  function clearParsedPreview(dom) {
    if (dom.detectedTypeEl) dom.detectedTypeEl.textContent = "-";
    if (dom.warningTextEl) dom.warningTextEl.textContent = "-";

    if (dom.goalsBoxEl) dom.goalsBoxEl.innerHTML = '<p class="preview-empty">분석 전입니다.</p>';
    if (dom.strategiesBoxEl) dom.strategiesBoxEl.innerHTML = '<p class="preview-empty">분석 전입니다.</p>';
    if (dom.timelineBoxEl) dom.timelineBoxEl.innerHTML = '<p class="preview-empty">분석 전입니다.</p>';
    if (dom.financeBoxEl) dom.financeBoxEl.innerHTML = '<p class="preview-empty">분석 전입니다.</p>';
    if (dom.jsonBoxEl) dom.jsonBoxEl.textContent = "";
  }

  function parseRawText(rawText, { requireText = false } = {}) {
    const text = String(rawText || "").trim();
    if (!text) {
      if (requireText) throw new Error("공약 본문을 입력해 주세요.");
      return null;
    }
    return window.PledgeParseUtils.getParsedModel(text);
  }

  window.PledgeAdminPreview = {
    renderParsedPreview,
    clearParsedPreview,
    parseRawText,
    getGoalTargetOptions,
  };
})();
