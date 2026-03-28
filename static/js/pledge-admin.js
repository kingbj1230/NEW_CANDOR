const utils = window.PledgeAdminUtils;
const preview = window.PledgeAdminPreview;

const dom = {
  pledgeGridEl: document.querySelector(".pledge-grid"),
  messageEl: document.getElementById("pledgeMessage"),
  pledgeForm: document.getElementById("pledgeForm"),

  electionSelect: document.getElementById("pledgeElectionId"),
  candidateSearchInput: document.getElementById("pledgeCandidateSearch"),
  candidateSearchDropdown: document.getElementById("pledgeCandidateSearchDropdown"),
  candidateSearchHelp: document.getElementById("pledgeCandidateSearchHelp"),
  candidateElectionIdInput: document.getElementById("candidateElectionId"),

  pledgeTitleInput: document.getElementById("pledgeTitle"),
  pledgeCategoryInput: document.getElementById("pledgeCategory"),
  pledgeSortOrderInput: document.getElementById("pledgeSortOrder"),

  editorTabButtons: Array.from(document.querySelectorAll("[data-editor-tab-target]")),
  editorPanels: Array.from(document.querySelectorAll("[data-editor-tab-panel]")),

  pledgeRawTextInput: document.getElementById("pledgeRawText"),

  structuredSectionTypeSelect: document.getElementById("structuredSectionType"),
  structuredItemTextInput: document.getElementById("structuredItemText"),
  addStructuredItemBtn: document.getElementById("addStructuredItemBtn"),
  structuredTopicGrid: document.querySelector(".structured-topic-stack"),
  structuredTopicListEls: {
    goal: document.querySelector('[data-structured-topic-list="goal"]'),
    method: document.querySelector('[data-structured-topic-list="method"]'),
    timeline: document.querySelector('[data-structured-topic-list="timeline"]'),
    finance: document.querySelector('[data-structured-topic-list="finance"]'),
  },
  structuredTopicCountEls: {
    goal: document.querySelector('[data-structured-topic-count="goal"]'),
    method: document.querySelector('[data-structured-topic-count="method"]'),
    timeline: document.querySelector('[data-structured-topic-count="timeline"]'),
    finance: document.querySelector('[data-structured-topic-count="finance"]'),
  },

  sourceModeInputs: Array.from(document.querySelectorAll("input[name='sourceLinkMode']")),
  sourceModeHelp: document.getElementById("sourceModeHelp"),
  sourceEmptyHint: document.getElementById("sourceEmptyHint"),
  sourceSummaryBar: document.getElementById("sourceSummaryBar"),
  sourceCountBadge: document.getElementById("sourceCountBadge"),
  sourceQuickList: document.getElementById("sourceQuickList"),
  sourceRowsContainer: document.getElementById("sourceRowsContainer"),
  sourceRowTemplate: document.getElementById("sourceRowTemplate"),
  addSourceRowBtn: document.getElementById("addSourceRowBtn"),

  parsePledgeBtn: document.getElementById("parsePledgeBtn"),
  savePledgeBtn: document.getElementById("savePledgeBtn"),

  detectedTypeEl: document.getElementById("detectedType"),
  warningTextEl: document.getElementById("warningText"),
  goalsBoxEl: document.getElementById("goalsBox"),
  strategiesBoxEl: document.getElementById("strategiesBox"),
  timelineBoxEl: document.getElementById("timelineBox"),
  financeBoxEl: document.getElementById("financeBox"),
  jsonBoxEl: document.getElementById("jsonBox"),

  loadingEl: document.getElementById("pledgeLoading"),
  loadingTextEl: document.getElementById("pledgeLoadingText"),
};

const state = {
  loadingCount: 0,
  candidateRows: [],
  electionRows: [],
  candidateElectionRows: [],
  candidateMap: new Map(),
  electionMap: new Map(),

  selectedCandidateOption: null,
  visibleCandidateOptions: [],
  activeCandidateOptionIndex: -1,
  candidateSearchBlurTimer: null,

  activeEditorTab: "free",
  latestParsedModel: null,
  structuredItems: {
    goal: [],
    method: [],
    timeline: [],
    finance: [],
  },
  sourceLibraryRows: [],
  sourceLibraryCandidateElectionId: "",
  sourceLibraryRequestSeq: 0,
  sourceRowSequence: 0,
};

const CIRCLED_NUMBERS = [
  "①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩",
  "⑪", "⑫", "⑬", "⑭", "⑮", "⑯", "⑰", "⑱", "⑲", "⑳",
];

const STRUCTURED_TOPICS = ["goal", "method", "timeline", "finance"];
const STRUCTURED_TOPIC_LABELS = {
  goal: "목표",
  method: "이행방법",
  timeline: "이행기간",
  finance: "재원조달방안 등",
};

function normalizeText(value) {
  return String(value || "").trim().toLowerCase();
}

function setCandidateSearchHelp(text, type = "info") {
  if (!dom.candidateSearchHelp) return;
  dom.candidateSearchHelp.classList.remove("warning", "success");
  if (type === "warning") dom.candidateSearchHelp.classList.add("warning");
  if (type === "success") dom.candidateSearchHelp.classList.add("success");
  dom.candidateSearchHelp.textContent = text;
}

function hideCandidateDropdown() {
  if (!dom.candidateSearchDropdown) return;
  dom.candidateSearchDropdown.hidden = true;
  state.activeCandidateOptionIndex = -1;
}

function setActiveCandidateOption(index) {
  const optionEls = Array.from(dom.candidateSearchDropdown?.querySelectorAll("[data-candidate-option-index]") || []);
  optionEls.forEach((el) => {
    const isActive = Number(el.dataset.candidateOptionIndex) === index;
    el.classList.toggle("is-active", isActive);
  });
  state.activeCandidateOptionIndex = index;
}

function selectedElectionId() {
  return String(dom.electionSelect?.value || "").trim();
}

function selectedCandidateElectionId() {
  return String(dom.candidateElectionIdInput?.value || "").trim();
}

function getCandidateOptionsForElection(electionId) {
  const electionKey = String(electionId || "").trim();
  if (!electionKey) return [];

  const options = [];
  for (const row of state.candidateElectionRows) {
    if (String(row?.election_id || "") !== electionKey) continue;
    const candidateId = String(row?.candidate_id || "").trim();
    const candidateElectionId = String(row?.id || "").trim();
    if (!candidateId || !candidateElectionId) continue;
    const candidate = state.candidateMap.get(candidateId) || {};
    const name = String(candidate?.name || "").trim() || "이름 없음";
    options.push({
      candidateElectionId,
      candidateId,
      name,
      searchableText: normalizeText(name),
    });
  }

  options.sort((a, b) => a.name.localeCompare(b.name, "ko"));
  return options;
}

function renderCandidateDropdown(query = "") {
  if (!dom.candidateSearchDropdown) return;
  const electionId = selectedElectionId();
  if (!electionId) {
    hideCandidateDropdown();
    return;
  }

  const options = getCandidateOptionsForElection(electionId);
  const normalizedQuery = normalizeText(query);
  const filtered = normalizedQuery
    ? options.filter((option) => option.searchableText.includes(normalizedQuery))
    : options;

  state.visibleCandidateOptions = filtered;
  state.activeCandidateOptionIndex = -1;

  if (!filtered.length) {
    dom.candidateSearchDropdown.innerHTML = '<div class="candidate-option-empty">조건에 맞는 후보자가 없습니다.</div>';
    dom.candidateSearchDropdown.hidden = false;
    return;
  }

  dom.candidateSearchDropdown.innerHTML = filtered
    .map((option, index) => {
      const safeName = utils.escapeHtml(option.name);
      const safeId = utils.escapeHtml(option.candidateElectionId);
      return `
        <button
          type="button"
          class="candidate-option"
          role="option"
          data-candidate-option-index="${index}"
          data-candidate-election-id="${safeId}">
          ${safeName}
        </button>
      `;
    })
    .join("");
  dom.candidateSearchDropdown.hidden = false;
}

function clearSelectedCandidate({ clearInput = false } = {}) {
  state.selectedCandidateOption = null;
  if (dom.candidateElectionIdInput) dom.candidateElectionIdInput.value = "";
  if (clearInput && dom.candidateSearchInput) dom.candidateSearchInput.value = "";
  setSourceLibraryRows([], "");
}

function selectCandidateOption(option) {
  state.selectedCandidateOption = option;
  if (dom.candidateElectionIdInput) dom.candidateElectionIdInput.value = option.candidateElectionId;
  if (dom.candidateSearchInput) dom.candidateSearchInput.value = option.name;
  hideCandidateDropdown();
  setCandidateSearchHelp(`선택된 후보자: ${option.name}`, "success");
  void loadSourceLibraryForCandidateElection(option.candidateElectionId);
}

function updateCandidateSearchAvailability() {
  const electionId = selectedElectionId();
  const hasElection = Boolean(electionId);

  if (!dom.candidateSearchInput) return;

  dom.candidateSearchInput.disabled = !hasElection;
  dom.candidateSearchInput.placeholder = hasElection
    ? "이름을 입력해 후보자를 선택해 주세요"
    : "선거를 먼저 선택해 주세요";

  clearSelectedCandidate({ clearInput: true });
  hideCandidateDropdown();

  if (!hasElection) {
    setCandidateSearchHelp("선거를 먼저 선택한 뒤 후보자를 검색해 주세요.");
    return;
  }

  const optionCount = getCandidateOptionsForElection(electionId).length;
  if (!optionCount) {
    setCandidateSearchHelp("선택한 선거에 등록된 후보자가 없습니다. 먼저 선거 후보 등록을 진행해 주세요.", "warning");
    return;
  }

  setCandidateSearchHelp(`후보자 ${optionCount}명이 검색 대상입니다.`);
}

function populateElectionSelect() {
  if (!dom.electionSelect) return;

  const selected = String(dom.electionSelect.value || "").trim();
  const options = state.electionRows
    .slice()
    .sort(utils.sortByRecentElection)
    .map((row) => {
      const id = String(row?.id || "").trim();
      if (!id) return "";
      const label = utils.buildElectionLabel(row);
      return `<option value="${utils.escapeHtml(id)}">${utils.escapeHtml(label)}</option>`;
    })
    .filter(Boolean)
    .join("");

  dom.electionSelect.innerHTML = `<option value="">선거를 먼저 선택해 주세요</option>${options}`;

  if (selected && state.electionMap.has(selected)) {
    dom.electionSelect.value = selected;
  }
}

function renderStructuredTopicLists() {
  STRUCTURED_TOPICS.forEach((topic) => {
    const listEl = dom.structuredTopicListEls[topic];
    const countEl = dom.structuredTopicCountEls[topic];
    const rows = state.structuredItems[topic] || [];

    if (countEl) countEl.textContent = String(rows.length);
    if (!listEl) return;

    if (!rows.length) {
      listEl.innerHTML = '<li class="structured-empty">아직 추가된 항목이 없습니다.</li>';
      return;
    }

    listEl.innerHTML = rows
      .map((text, index) => {
        const safeText = utils.escapeHtml(text);
        return `
          <li class="structured-item" data-structured-item data-structured-topic="${utils.escapeHtml(topic)}" data-structured-index="${index}">
            <span class="structured-item-text">${safeText}</span>
            <button type="button" class="secondary small" data-action="remove-structured-item">삭제</button>
          </li>
        `;
      })
      .join("");
  });
}

function resetStructuredItems() {
  state.structuredItems = {
    goal: [],
    method: [],
    timeline: [],
    finance: [],
  };
  renderStructuredTopicLists();

  const goalCard = dom.structuredTopicGrid?.querySelector('[data-structured-topic-card="goal"]');
  if (goalCard instanceof HTMLDetailsElement) {
    goalCard.open = true;
  }
  dom.structuredTopicGrid?.querySelectorAll("details.structured-topic").forEach((el) => {
    if (el !== goalCard) el.open = false;
  });
}

function addStructuredItem(topic, value) {
  const normalizedTopic = String(topic || "").trim();
  if (!STRUCTURED_TOPICS.includes(normalizedTopic)) {
    throw new Error("대제목을 선택해 주세요.");
  }

  const text = String(value || "").trim();
  if (!text) {
    throw new Error("추가할 항목 내용을 입력해 주세요.");
  }

  state.structuredItems[normalizedTopic].push(text);
  renderStructuredTopicLists();

  const selectedTopicCard = dom.structuredTopicGrid?.querySelector(`[data-structured-topic-card="${normalizedTopic}"]`);
  if (selectedTopicCard instanceof HTMLDetailsElement) {
    selectedTopicCard.open = true;
    dom.structuredTopicGrid?.querySelectorAll("details.structured-topic[open]").forEach((el) => {
      if (el !== selectedTopicCard) el.open = false;
    });
  }

  state.latestParsedModel = null;
  updateSourceModeUI();
}

function collectStructuredInput() {
  return {
    goals: (state.structuredItems.goal || []).slice(),
    methods: (state.structuredItems.method || []).slice(),
    timeline: (state.structuredItems.timeline || []).slice(),
    finance: (state.structuredItems.finance || []).slice(),
  };
}

function buildRawTextFromStructured(structured) {
  const goals = structured.goals || [];
  const methods = structured.methods || [];
  const timeline = structured.timeline || [];
  const finance = structured.finance || [];

  const lines = [];

  if (goals.length) {
    lines.push("목표");
    goals.forEach((goal) => lines.push(`- ${goal}`));
  }

  if (methods.length) {
    if (lines.length) lines.push("");
    lines.push("이행방법");
    methods.forEach((method, index) => {
      const marker = CIRCLED_NUMBERS[index] || `${index + 1}.`;
      lines.push(`${marker} ${method}`);
    });
  }

  if (timeline.length) {
    if (lines.length) lines.push("");
    lines.push("이행기간");
    timeline.forEach((item) => lines.push(`- ${item}`));
  }

  if (finance.length) {
    if (lines.length) lines.push("");
    lines.push("재원조달방안 등");
    finance.forEach((item) => lines.push(`- ${item}`));
  }

  return lines.join("\n").trim();
}

function getActiveSourceMode() {
  const selected = dom.sourceModeInputs.find((input) => input.checked);
  return selected?.value === "advanced" ? "advanced" : "basic";
}

function refreshGoalTargetOptions(parsedModel) {
  const options = preview.getGoalTargetOptions(parsedModel || null);
  const targetSelects = Array.from(dom.sourceRowsContainer?.querySelectorAll("[data-source-target-path]") || []);

  targetSelects.forEach((selectEl) => {
    const currentValue = String(selectEl.value || "").trim();
    selectEl.innerHTML = `<option value="">목표(goal)를 선택해 주세요</option>${options
      .map((option) => `<option value="${utils.escapeHtml(option.value)}">${utils.escapeHtml(option.label)}</option>`)
      .join("")}`;
    if (currentValue && options.some((option) => option.value === currentValue)) {
      selectEl.value = currentValue;
    }
  });

  return options;
}

function updateSourceModeUI() {
  const mode = getActiveSourceMode();
  const isAdvanced = mode === "advanced";

  const targetWrapEls = Array.from(dom.sourceRowsContainer?.querySelectorAll("[data-goal-target-wrap]") || []);
  targetWrapEls.forEach((wrapEl) => {
    wrapEl.hidden = !isAdvanced;
  });

  const goalOptions = refreshGoalTargetOptions(state.latestParsedModel);

  if (!dom.sourceModeHelp) return;
  if (!isAdvanced) {
    dom.sourceModeHelp.textContent = "기본 모드는 전체 공약 연결입니다.";
    return;
  }

  if (!goalOptions.length) {
    dom.sourceModeHelp.textContent = "고급 모드는 각 항목 세부 연결입니다. 먼저 구조 분석으로 연결 항목을 준비해 주세요.";
    return;
  }

  const labels = goalOptions.map((option) => option.label).join(", ");
  dom.sourceModeHelp.textContent = `고급 모드는 각 항목 세부 연결입니다. 현재 연결 가능 항목: ${labels}`;
}

function sourceLibraryRows() {
  return Array.isArray(state.sourceLibraryRows) ? state.sourceLibraryRows : [];
}

function sourceLibraryOptionLabel(row) {
  const title = String(row?.title || "").trim() || "제목 없음";
  const publisher = String(row?.publisher || "").trim();
  const publishedAt = String(row?.published_at || "").trim();
  const usageCount = Number(row?.usage_count);
  const parts = [title];
  if (publisher) parts.push(publisher);
  if (publishedAt) parts.push(publishedAt);
  if (Number.isFinite(usageCount) && usageCount > 0) parts.push(`${usageCount}회 사용`);
  return parts.join(" · ");
}

function renderSourceLibraryOptions(selectedSourceId = "") {
  const rows = sourceLibraryRows();
  if (!rows.length) {
    return '<option value="">사용 가능한 기존 자료가 없습니다.</option>';
  }
  const selectedId = String(selectedSourceId || "").trim();
  const options = rows
    .map((row) => {
      const sourceId = String(row?.id || "").trim();
      if (!sourceId) return "";
      const label = sourceLibraryOptionLabel(row);
      return `<option value="${utils.escapeHtml(sourceId)}"${sourceId === selectedId ? " selected" : ""}>${utils.escapeHtml(label)}</option>`;
    })
    .filter(Boolean)
    .join("");
  return `<option value="">기존 자료를 선택해 주세요</option>${options}`;
}

function populateSourceLibrarySelect(rowEl, selectedSourceId = "") {
  if (!rowEl) return;
  const selectEl = rowEl.querySelector("[data-source-existing-id]");
  if (!selectEl) return;

  const currentValue = String(selectedSourceId || selectEl.value || "").trim();
  selectEl.innerHTML = renderSourceLibraryOptions(currentValue);

  const canUseCurrent = sourceLibraryRows().some((row) => String(row?.id || "").trim() === currentValue);
  selectEl.value = canUseCurrent ? currentValue : "";

  const helpEl = rowEl.querySelector("[data-source-existing-help]");
  if (helpEl) {
    helpEl.textContent = sourceLibraryRows().length
      ? "같은 후보/선거에서 이미 사용된 출처를 선택할 수 있습니다."
      : "재사용 가능한 출처가 없습니다. 새 자료 등록을 사용해 주세요.";
  }
}

function getSourceEntryMode(rowEl) {
  const checked = rowEl?.querySelector("[data-source-entry-mode]:checked");
  return checked?.value === "existing" ? "existing" : "new";
}

function applySourceEntryMode(rowEl) {
  if (!rowEl) return;
  const mode = getSourceEntryMode(rowEl);
  rowEl.dataset.sourceEntryMode = mode;

  const existingWrap = rowEl.querySelector("[data-source-existing-wrap]");
  if (existingWrap) existingWrap.hidden = mode !== "existing";

  const newFieldEls = Array.from(rowEl.querySelectorAll("[data-source-new-field]"));
  newFieldEls.forEach((fieldEl) => {
    fieldEl.hidden = mode === "existing";
  });

  if (mode === "existing") {
    populateSourceLibrarySelect(rowEl);
  }
}

function setSourceLibraryRows(rows, candidateElectionId = "") {
  state.sourceLibraryRows = (Array.isArray(rows) ? rows : [])
    .map((row) => ({ ...(row || {}), id: String(row?.id || "").trim() }))
    .filter((row) => row.id);
  state.sourceLibraryCandidateElectionId = String(candidateElectionId || "").trim();

  const rowEls = Array.from(dom.sourceRowsContainer?.querySelectorAll("[data-source-row]") || []);
  rowEls.forEach((rowEl) => {
    populateSourceLibrarySelect(rowEl);
    applySourceEntryMode(rowEl);
  });
  refreshSourceRowsUI();
}

async function loadSourceLibraryForCandidateElection(candidateElectionId) {
  const normalizedCandidateElectionId = String(candidateElectionId || "").trim();
  if (!normalizedCandidateElectionId) {
    setSourceLibraryRows([], "");
    return;
  }

  const requestSeq = ++state.sourceLibraryRequestSeq;
  try {
    const response = await utils.apiGet(
      `/api/pledges/source-library?candidate_election_id=${encodeURIComponent(normalizedCandidateElectionId)}`,
    );
    if (requestSeq !== state.sourceLibraryRequestSeq) return;
    if (selectedCandidateElectionId() !== normalizedCandidateElectionId) return;
    setSourceLibraryRows(response?.rows || [], normalizedCandidateElectionId);
  } catch (_error) {
    if (requestSeq !== state.sourceLibraryRequestSeq) return;
    if (selectedCandidateElectionId() !== normalizedCandidateElectionId) return;
    setSourceLibraryRows([], normalizedCandidateElectionId);
  }
}

function addSourceRow(initial = {}) {
  if (!dom.sourceRowTemplate || !dom.sourceRowsContainer) return;
  const fragment = dom.sourceRowTemplate.content.cloneNode(true);
  const rowEl = fragment.querySelector("[data-source-row]");
  state.sourceRowSequence += 1;
  const entryModeGroupName = `source-entry-mode-${state.sourceRowSequence}`;
  const entryModeInputs = Array.from(rowEl.querySelectorAll("[data-source-entry-mode]"));
  entryModeInputs.forEach((inputEl) => {
    inputEl.name = entryModeGroupName;
  });

  rowEl.querySelector("[data-source-title]").value = String(initial.title || "");
  rowEl.querySelector("[data-source-url]").value = String(initial.url || "");
  rowEl.querySelector("[data-source-type]").value = String(initial.source_type || "");
  rowEl.querySelector("[data-source-role]").value = String(initial.source_role || "참고출처");
  rowEl.querySelector("[data-source-publisher]").value = String(initial.publisher || "");
  rowEl.querySelector("[data-source-published-at]").value = String(initial.published_at || "");
  rowEl.querySelector("[data-source-summary]").value = String(initial.summary || "");
  rowEl.querySelector("[data-source-note]").value = String(initial.note || "");
  rowEl.querySelector("[data-source-existing-id]").value = String(initial.source_id || "");

  const sourceEntryMode = String(initial.source_id || "").trim() ? "existing" : "new";
  entryModeInputs.forEach((inputEl) => {
    inputEl.checked = inputEl.value === sourceEntryMode;
  });

  populateSourceLibrarySelect(rowEl, initial.source_id);
  applySourceEntryMode(rowEl);

  dom.sourceRowsContainer.appendChild(fragment);
  refreshSourceRowsUI();
  updateSourceModeUI();
}

function sourceMetaTextFromRow(rowEl) {
  if (getSourceEntryMode(rowEl) === "existing") {
    const selectEl = rowEl.querySelector("[data-source-existing-id]");
    const selectedId = String(selectEl?.value || "").trim();
    if (!selectedId) return "기존 자료를 선택해 주세요";
    const selectedRow = sourceLibraryRows().find((row) => String(row?.id || "").trim() === selectedId);
    const selectedLabel = selectedRow ? sourceLibraryOptionLabel(selectedRow) : String(selectEl?.selectedOptions?.[0]?.textContent || "").trim();
    return selectedLabel ? `[기존] ${selectedLabel}` : "기존 자료를 선택해 주세요";
  }

  const title = String(rowEl.querySelector("[data-source-title]")?.value || "").trim();
  const urlRaw = String(rowEl.querySelector("[data-source-url]")?.value || "").trim();
  if (title) return title;
  if (urlRaw) {
    try {
      return new URL(urlRaw).host || urlRaw;
    } catch (_err) {
      return urlRaw;
    }
  }
  return "제목을 입력해 주세요";
}

function refreshSourceRowsUI() {
  const rowEls = Array.from(dom.sourceRowsContainer?.querySelectorAll("[data-source-row]") || []);
  const count = rowEls.length;

  if (dom.sourceEmptyHint) dom.sourceEmptyHint.hidden = count > 0;
  if (dom.sourceSummaryBar) dom.sourceSummaryBar.hidden = count === 0;
  if (dom.sourceCountBadge) dom.sourceCountBadge.textContent = `출처 ${count}개`;

  rowEls.forEach((rowEl, index) => {
    const order = index + 1;
    rowEl.dataset.sourceIndex = String(order);
    const labelEl = rowEl.querySelector("[data-source-label]");
    const metaEl = rowEl.querySelector("[data-source-meta]");
    if (labelEl) labelEl.textContent = `출처 ${order}`;
    if (metaEl) metaEl.textContent = sourceMetaTextFromRow(rowEl);
  });

  if (dom.sourceQuickList) {
    dom.sourceQuickList.innerHTML = rowEls
      .map((rowEl, index) => {
        const order = index + 1;
        const meta = sourceMetaTextFromRow(rowEl);
        return `
          <button type="button" class="source-quick-chip" data-action="jump-source-row" data-source-index="${order}">
            #${order} ${utils.escapeHtml(meta)}
          </button>
        `;
      })
      .join("");
  }
}

function clearSourcesToDefault() {
  if (!dom.sourceRowsContainer) return;
  dom.sourceRowsContainer.innerHTML = "";
  refreshSourceRowsUI();
}

function getCurrentEditorRawText() {
  if (state.activeEditorTab === "free") {
    return String(dom.pledgeRawTextInput?.value || "").trim();
  }

  const structured = collectStructuredInput();
  return buildRawTextFromStructured(structured);
}

function renderPreviewFromCurrentEditor({ requireText = false } = {}) {
  const rawText = getCurrentEditorRawText();
  if (requireText && !rawText && state.activeEditorTab === "structured") {
    throw new Error("단계별 입력에서 항목을 하나 이상 추가해 주세요.");
  }
  const parsedModel = preview.parseRawText(rawText, { requireText });
  if (!parsedModel) return null;

  parsedModel.raw_text = rawText;
  state.latestParsedModel = parsedModel;

  preview.renderParsedPreview(parsedModel, dom);
  refreshGoalTargetOptions(parsedModel);
  updateSourceModeUI();
  return parsedModel;
}

function collectSourcesPayload(parsedModel) {
  const rows = Array.from(dom.sourceRowsContainer?.querySelectorAll("[data-source-row]") || []);
  const mode = getActiveSourceMode();
  const payloadRows = [];

  rows.forEach((rowEl, rowIndex) => {
    const sourceEntryMode = getSourceEntryMode(rowEl);
    const sourceId = String(rowEl.querySelector("[data-source-existing-id]")?.value || "").trim();
    const title = String(rowEl.querySelector("[data-source-title]")?.value || "").trim();
    const urlRaw = String(rowEl.querySelector("[data-source-url]")?.value || "").trim();
    const sourceType = String(rowEl.querySelector("[data-source-type]")?.value || "").trim();
    const sourceRole = String(rowEl.querySelector("[data-source-role]")?.value || "").trim() || "참고출처";
    const publisher = String(rowEl.querySelector("[data-source-publisher]")?.value || "").trim();
    const publishedAt = String(rowEl.querySelector("[data-source-published-at]")?.value || "").trim();
    const summary = String(rowEl.querySelector("[data-source-summary]")?.value || "").trim();
    const note = String(rowEl.querySelector("[data-source-note]")?.value || "").trim();
    const targetPath = String(rowEl.querySelector("[data-source-target-path]")?.value || "").trim();
    const linkScope = mode === "advanced" ? "goal" : "pledge";

    if (sourceEntryMode === "existing") {
      const hasAny = [sourceId, note, targetPath].some(Boolean);
      if (!hasAny) return;

      if (!sourceId) {
        throw new Error(`출처 ${rowIndex + 1}: 기존 자료를 선택해 주세요.`);
      }

      if (mode === "advanced" && !targetPath) {
        throw new Error(`출처 ${rowIndex + 1}: 연결 항목을 선택해 주세요.`);
      }

      payloadRows.push({
        source_id: sourceId,
        source_role: sourceRole,
        note: note || "",
        link_scope: linkScope,
        target_path: mode === "advanced" ? targetPath : "",
      });
      return;
    }

    const hasAny = [title, urlRaw, sourceType, publisher, publishedAt, summary, note, targetPath].some(Boolean);
    if (!hasAny) return;

    if (!title) {
      throw new Error(`출처 ${rowIndex + 1}: 출처 제목을 입력해 주세요.`);
    }

    const normalizedUrl = utils.normalizeHttpUrl(urlRaw);
    if (urlRaw && !normalizedUrl) {
      throw new Error(`출처 ${rowIndex + 1}: URL 형식은 http(s)만 허용됩니다.`);
    }

    if (mode === "advanced" && !targetPath) {
      throw new Error(`출처 ${rowIndex + 1}: 연결 항목을 선택해 주세요.`);
    }

    payloadRows.push({
      title,
      url: normalizedUrl || "",
      source_type: sourceType || "",
      source_role: sourceRole,
      publisher: publisher || "",
      published_at: publishedAt || "",
      summary: summary || "",
      note: note || "",
      link_scope: linkScope,
      target_path: mode === "advanced" ? targetPath : "",
    });
  });

  if (mode === "advanced" && payloadRows.length) {
    const goalOptions = preview.getGoalTargetOptions(parsedModel || null);
    if (!goalOptions.length) {
      throw new Error("고급 모드를 사용하려면 먼저 구조 분석을 실행해 연결 항목을 생성해 주세요.");
    }

    const covered = new Set(payloadRows.map((row) => String(row.target_path || "").trim()));
    const missing = goalOptions.filter((option) => !covered.has(option.value));
    if (missing.length) {
      const labels = missing.map((item) => item.label).join(", ");
      throw new Error(`고급 모드는 모든 목표(goal)에 출처가 필요합니다: ${labels}`);
    }
  }

  return payloadRows;
}

function setActiveEditorTab(tabName) {
  state.activeEditorTab = tabName === "structured" ? "structured" : "free";

  dom.editorTabButtons.forEach((buttonEl) => {
    const isActive = buttonEl.dataset.editorTabTarget === state.activeEditorTab;
    buttonEl.classList.toggle("active", isActive);
    buttonEl.setAttribute("aria-selected", String(isActive));
  });

  dom.editorPanels.forEach((panelEl) => {
    const isActive = panelEl.dataset.editorTabPanel === state.activeEditorTab;
    panelEl.classList.toggle("is-active", isActive);
    panelEl.hidden = !isActive;
  });

  dom.pledgeGridEl?.classList.toggle("structured-focus", state.activeEditorTab === "structured");
}

function resetEditorState() {
  state.latestParsedModel = null;
  preview.clearParsedPreview(dom);
  refreshGoalTargetOptions(null);
  updateSourceModeUI();
}

function bindCandidateSearchEvents() {
  dom.electionSelect?.addEventListener("change", () => {
    updateCandidateSearchAvailability();
    resetEditorState();
  });

  dom.candidateSearchInput?.addEventListener("focus", () => {
    if (state.candidateSearchBlurTimer) {
      window.clearTimeout(state.candidateSearchBlurTimer);
      state.candidateSearchBlurTimer = null;
    }
    if (dom.candidateSearchInput.disabled) return;
    renderCandidateDropdown(dom.candidateSearchInput.value || "");
  });

  dom.candidateSearchInput?.addEventListener("blur", () => {
    state.candidateSearchBlurTimer = window.setTimeout(() => hideCandidateDropdown(), 150);
  });

  dom.candidateSearchInput?.addEventListener("input", () => {
    const typed = String(dom.candidateSearchInput.value || "").trim();
    if (state.selectedCandidateOption && typed !== state.selectedCandidateOption.name) {
      clearSelectedCandidate({ clearInput: false });
    }
    renderCandidateDropdown(typed);
  });

  dom.candidateSearchInput?.addEventListener("keydown", (event) => {
    if (dom.candidateSearchDropdown?.hidden) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!state.visibleCandidateOptions.length) return;
      const nextIndex = state.activeCandidateOptionIndex + 1;
      setActiveCandidateOption(Math.min(nextIndex, state.visibleCandidateOptions.length - 1));
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!state.visibleCandidateOptions.length) return;
      const prevIndex = state.activeCandidateOptionIndex - 1;
      setActiveCandidateOption(Math.max(prevIndex, 0));
      return;
    }

    if (event.key === "Enter") {
      if (state.activeCandidateOptionIndex < 0 || state.activeCandidateOptionIndex >= state.visibleCandidateOptions.length) return;
      event.preventDefault();
      selectCandidateOption(state.visibleCandidateOptions[state.activeCandidateOptionIndex]);
    }
  });

  dom.candidateSearchDropdown?.addEventListener("mousedown", (event) => {
    const optionEl = event.target.closest("[data-candidate-election-id]");
    if (!optionEl) return;

    const candidateElectionId = String(optionEl.dataset.candidateElectionId || "");
    const option = state.visibleCandidateOptions.find((item) => item.candidateElectionId === candidateElectionId);
    if (!option) return;

    event.preventDefault();
    selectCandidateOption(option);
  });
}

function bindEditorTabEvents() {
  dom.editorTabButtons.forEach((buttonEl) => {
    buttonEl.addEventListener("click", () => {
      const target = buttonEl.dataset.editorTabTarget;
      setActiveEditorTab(target);
      resetEditorState();
    });
  });
}

function bindStructuredEditorEvents() {
  dom.addStructuredItemBtn?.addEventListener("click", () => {
    try {
      const topic = dom.structuredSectionTypeSelect?.value;
      const text = dom.structuredItemTextInput?.value;
      addStructuredItem(topic, text);
      if (dom.structuredItemTextInput) dom.structuredItemTextInput.value = "";
      dom.structuredItemTextInput?.focus();
      utils.setMessage(dom.messageEl, `${STRUCTURED_TOPIC_LABELS[String(topic || "").trim()] || "선택 항목"} 항목이 추가되었습니다.`, "success");
    } catch (error) {
      utils.setMessage(dom.messageEl, error.message || "단계별 입력 항목 추가에 실패했습니다.", "error");
    }
  });

  dom.structuredItemTextInput?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    dom.addStructuredItemBtn?.click();
  });

  dom.structuredTopicGrid?.addEventListener("toggle", (event) => {
    const opened = event.target;
    if (!(opened instanceof HTMLDetailsElement)) return;
    if (!opened.classList.contains("structured-topic")) return;
    if (!opened.open) return;

    dom.structuredTopicGrid.querySelectorAll("details.structured-topic[open]").forEach((el) => {
      if (el !== opened) el.open = false;
    });
  });

  dom.structuredTopicGrid?.addEventListener("click", (event) => {
    const removeBtn = event.target.closest("[data-action='remove-structured-item']");
    if (!removeBtn) return;

    const rowEl = removeBtn.closest("[data-structured-item]");
    if (!rowEl) return;

    const topic = String(rowEl.dataset.structuredTopic || "").trim();
    const index = Number(rowEl.dataset.structuredIndex);
    if (!STRUCTURED_TOPICS.includes(topic)) return;
    if (!Number.isInteger(index) || index < 0) return;

    const rows = state.structuredItems[topic] || [];
    if (index >= rows.length) return;
    rows.splice(index, 1);
    renderStructuredTopicLists();

    if (state.activeEditorTab === "structured") {
      state.latestParsedModel = null;
      updateSourceModeUI();
    }
  });
}

function bindSourceEvents() {
  dom.addSourceRowBtn?.addEventListener("click", () => addSourceRow());

  dom.sourceRowsContainer?.addEventListener("click", (event) => {
    const removeBtn = event.target.closest("[data-action='remove-source-row']");
    if (!removeBtn) return;
    const rowEl = removeBtn.closest("[data-source-row]");
    rowEl?.remove();
    refreshSourceRowsUI();
    updateSourceModeUI();
  });

  dom.sourceRowsContainer?.addEventListener("input", () => {
    refreshSourceRowsUI();
  });

  dom.sourceRowsContainer?.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    if (target.closest("[data-source-entry-mode]")) {
      const rowEl = target.closest("[data-source-row]");
      if (!rowEl) return;
      applySourceEntryMode(rowEl);
      refreshSourceRowsUI();
      return;
    }

    if (target.closest("[data-source-existing-id]")) {
      refreshSourceRowsUI();
    }
  });

  dom.sourceQuickList?.addEventListener("click", (event) => {
    const jumpBtn = event.target.closest("[data-action='jump-source-row']");
    if (!jumpBtn) return;
    const index = Number(jumpBtn.dataset.sourceIndex);
    if (!Number.isInteger(index) || index < 1) return;
    const targetRow = dom.sourceRowsContainer?.querySelector(`[data-source-index="${index}"]`);
    if (!targetRow) return;

    targetRow.scrollIntoView({ behavior: "smooth", block: "center" });
    targetRow.classList.add("source-row-focus");
    window.setTimeout(() => targetRow.classList.remove("source-row-focus"), 700);
  });

  dom.sourceModeInputs.forEach((inputEl) => {
    inputEl.addEventListener("change", () => updateSourceModeUI());
  });
}

function bindParseSaveEvents() {
  dom.parsePledgeBtn?.addEventListener("click", () => {
    try {
      renderPreviewFromCurrentEditor({ requireText: true });
      utils.setMessage(dom.messageEl, "구조 분석이 완료되었습니다. 미리보기를 확인해 주세요.", "success");
    } catch (error) {
      utils.setMessage(dom.messageEl, error.message || "구조 분석에 실패했습니다.", "error");
    }
  });

  dom.pledgeRawTextInput?.addEventListener("input", () => {
    if (state.activeEditorTab !== "free") return;
    state.latestParsedModel = null;
    updateSourceModeUI();
  });

  dom.pledgeForm?.addEventListener("submit", async (event) => {
    event.preventDefault();

    utils.setMessage(dom.messageEl, "공약을 저장하는 중입니다...", "info");
    if (dom.savePledgeBtn) dom.savePledgeBtn.disabled = true;
    utils.setLoading(state, dom.loadingEl, dom.loadingTextEl, true, "공약과 출처를 저장하는 중입니다...");

    try {
      const candidateElectionId = String(dom.candidateElectionIdInput?.value || "").trim();
      const title = String(dom.pledgeTitleInput?.value || "").trim();
      const category = String(dom.pledgeCategoryInput?.value || "").trim();

      if (!selectedElectionId()) throw new Error("선거를 선택해 주세요.");
      if (!candidateElectionId) throw new Error("선거 후보자를 선택해 주세요.");
      if (!title || !category) throw new Error("공약 제목과 카테고리를 입력해 주세요.");

      const sortOrder = utils.normalizeSortOrder(dom.pledgeSortOrderInput?.value);
      const parsedModel = renderPreviewFromCurrentEditor({ requireText: true });
      const sources = collectSourcesPayload(parsedModel);

      const payload = {
        candidate_election_id: candidateElectionId,
        title,
        raw_text: parsedModel.raw_text,
        category,
        sort_order: sortOrder,
        status: "active",
        parse_type: parsedModel.parse_type,
        structure_version: parsedModel.structure_version,
        sources,
      };

      await utils.apiPost("/api/pledges", payload);

      utils.setMessage(dom.messageEl, "공약이 저장되었습니다.", "success");

      dom.pledgeForm.reset();
      setActiveEditorTab("free");
      updateCandidateSearchAvailability();
      resetStructuredItems();
      clearSourcesToDefault();

      state.latestParsedModel = null;
      preview.clearParsedPreview(dom);
      refreshGoalTargetOptions(null);
      updateSourceModeUI();
    } catch (error) {
      utils.setMessage(dom.messageEl, error.message || "공약 저장에 실패했습니다.", "error");
    } finally {
      if (dom.savePledgeBtn) dom.savePledgeBtn.disabled = false;
      utils.setLoading(state, dom.loadingEl, dom.loadingTextEl, false);
    }
  });
}

async function refreshInitData() {
  const [candidatesResp, electionsResp, candidateElectionsResp] = await Promise.all([
    utils.apiGet("/api/candidate-admin/candidates"),
    utils.apiGet("/api/candidate-admin/elections"),
    utils.apiGet("/api/candidate-admin/candidate-elections"),
  ]);

  state.candidateRows = (candidatesResp.rows || []).slice().sort(utils.sortByName);
  state.electionRows = electionsResp.rows || [];
  state.candidateElectionRows = candidateElectionsResp.rows || [];

  state.candidateMap = new Map(
    state.candidateRows
      .filter((row) => row?.id !== undefined && row?.id !== null)
      .map((row) => [String(row.id), row]),
  );

  state.electionMap = new Map(
    state.electionRows
      .filter((row) => row?.id !== undefined && row?.id !== null)
      .map((row) => [String(row.id), row]),
  );

  populateElectionSelect();
  updateCandidateSearchAvailability();
}

function bindAllEvents() {
  bindEditorTabEvents();
  bindCandidateSearchEvents();
  bindStructuredEditorEvents();
  bindSourceEvents();
  bindParseSaveEvents();
}

document.addEventListener("DOMContentLoaded", async () => {
  if (window.location.pathname !== "/pledge") return;

  setActiveEditorTab("free");
  resetStructuredItems();
  refreshSourceRowsUI();
  preview.clearParsedPreview(dom);
  updateSourceModeUI();

  bindAllEvents();

  utils.setMessage(dom.messageEl, "공약 등록 페이지를 준비하는 중입니다...", "info");
  utils.setLoading(state, dom.loadingEl, dom.loadingTextEl, true, "기본 데이터를 불러오는 중입니다...");

  try {
    await refreshInitData();
    utils.setMessage(dom.messageEl, "공약 등록 페이지가 준비되었습니다.", "success");
  } catch (error) {
    utils.setMessage(dom.messageEl, error.message || "초기 로딩에 실패했습니다.", "error");
  } finally {
    utils.setLoading(state, dom.loadingEl, dom.loadingTextEl, false);
  }
});
