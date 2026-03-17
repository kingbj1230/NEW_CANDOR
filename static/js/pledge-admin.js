const TEXT = {
  processing: "처리 중입니다. 잠시만 기다려 주세요...",
  requestFail: "요청 실패",
  defaultGoal: "기본 목표",
  defaultPromise: "세부 공약",
  noItems: "실행 항목 없음",
  noPromises: "세부 공약이 아직 없습니다.",
  candidateId: "후보자 ID ",
  electionId: "선거 ID ",
  noResult: "결과 미지정",
  selectCandidateElection: "후보자-선거를 선택하세요",
  needCandidateElection: "후보자-선거 매칭을 선택해 주세요.",
  needTitleCategory: "공약 제목과 카테고리를 모두 입력해 주세요.",
  parseFail: "본문을 구조화할 수 없습니다. 첫 문단은 목표, 다음 문단은 세부 공약 형태로 작성해 주세요.",
  badSort: "공약 정렬 순서는 1 이상의 숫자여야 합니다.",
  preparing: "공약 등록 화면을 준비하는 중입니다...",
  ready: "공약 등록 페이지가 준비되었습니다.",
  initFail: "초기 로딩 실패",
  guidedTokenProtected: "기호와 공백은 한 세트로 유지됩니다. 지우려면 Backspace/Delete로 한 번에 지워주세요.",
  guidedNeedTextAfterMarker: "기호만 남아 있으면 저장할 수 없습니다. 뒤에 내용을 입력해 주세요.",
  guidedTabOnly: "이 버튼은 '자유 작성' 탭에서 사용할 수 있습니다.",
  goalOtherPrompt: "기타 항목에 들어갈 제목을 입력해 주세요.",
  goalOtherRequired: "기타 항목은 비워 둘 수 없습니다.",
  blogNeedGoal: "대항목을 먼저 등록해 주세요.",
  blogNeedPromise: "상위 대항목을 선택하고 중항목 내용을 입력해 주세요.",
  blogNeedItem: "상위 중항목을 선택하고 세부항목 내용을 입력해 주세요.",
  blogNeedGoalType: "대항목 구분을 선택해 주세요.",
  blogNeedNodeType: "추가할 유형을 선택해 주세요.",
  blogEmpty: "아직 추가된 구조가 없습니다.",
  confirmDeleteGoalNode: "대항목을 삭제할까요? 하위 중항목/세부항목도 함께 삭제됩니다.",
  confirmDeletePromiseNode: "중항목을 삭제할까요? 하위 세부항목도 함께 삭제됩니다.",
  confirmDeleteItemNode: "세부항목을 삭제할까요?",
  sourceEmpty: "아직 등록된 출처가 없습니다.",
  sourceNeedTitle: "출처 제목은 필수입니다.",
  sourceNeedAtLeastOne: "공약 출처를 최소 1개 이상 등록해 주세요.",
  sourceNeedReusable: "재사용할 기존 출처를 선택해 주세요.",
  sourceSaving: "공약과 출처를 함께 저장하는 중입니다...",
  sourceSaved: "공약과 출처가 저장되었습니다.",
  sourceSaveFail: "공약 출처 저장 실패",
};

const messageEl = document.getElementById("pledgeMessage");
const pledgeForm = document.getElementById("pledgeForm");
const candidateElectionSelect = document.getElementById("candidateElectionId");
const savePledgeBtn = document.getElementById("savePledgeBtn");
const pledgeTitleInput = document.getElementById("pledgeTitle");
const pledgeSortOrderInput = document.getElementById("pledgeSortOrder");
const pledgeRawTextPlainInput = document.getElementById("pledgeRawTextPlain");
const pledgeRawTextGuidedInput = document.getElementById("pledgeRawTextGuided");
const pledgeCategoryInput = document.getElementById("pledgeCategory");
const loadingEl = document.getElementById("pledgeLoading");
const loadingTextEl = document.getElementById("pledgeLoadingText");
const editorValidationMessageEl = document.getElementById("editorValidationMessage");
const editorModeTabs = Array.from(document.querySelectorAll(".editor-mode-tab"));
const editorPanels = Array.from(document.querySelectorAll(".editor-panel"));
const goalMenuToggleBtn = document.querySelector("[data-goal-menu-toggle]");
const goalOptionMenuEl = document.getElementById("goalOptionMenu");
const blogNodeTypeSelect = document.getElementById("blogNodeType");
const blogGoalTypeSelect = document.getElementById("blogGoalType");
const blogGoalTypeField = document.getElementById("blogGoalTypeField");
const blogParentGoalField = document.getElementById("blogParentGoalField");
const blogParentGoalSelect = document.getElementById("blogParentGoalSelect");
const blogParentPromiseField = document.getElementById("blogParentPromiseField");
const blogParentPromiseSelect = document.getElementById("blogParentPromiseSelect");
const blogNodeTextField = document.getElementById("blogNodeTextField");
const blogNodeTextInput = document.getElementById("blogNodeText");
const addBlogNodeBtn = document.getElementById("addBlogNodeBtn");
const blogStructureTreeEl = document.getElementById("blogStructureTree");
const addPledgeSourceBtn = document.getElementById("addPledgeSourceBtn");
const pledgeSourceListEl = document.getElementById("pledgeSourceList");

let candidates = [];
let elections = [];
let candidateElections = [];
let loadingCount = 0;
let activeEditorMode = "paste";
let blogDraftGoals = [];
let blogGoalSeq = 1;
let blogPromiseSeq = 1;
let blogItemSeq = 1;
const GOAL_OPTION_OTHER = "\uae30\ud0c0";
let pledgeSourceSeq = 1;
let pledgeSourceDraftRows = [];
let reusableSourceRows = [];
const SOURCE_ROLE_OPTIONS = ["공식 공약집", "보조 근거", "참고 출처", "관련 자료"];
const SOURCE_TYPE_OPTIONS = ["정부", "언론", "보고서", "연구", "예산", "보도자료", "연설", "법령", "기타"];
const SOURCE_LINK_SCOPE_PLEDGE = "pledge";
const SOURCE_LINK_SCOPE_GOAL = "goal";
const SOURCE_MODE_NEW = "new";
const SOURCE_MODE_REUSE = "reuse";

function setMessage(text, type = "info") {
  if (!messageEl) return;
  messageEl.className = `pledge-message ${type}`;
  messageEl.textContent = text;
}

function setLoading(isLoading, text = TEXT.processing) {
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
  const raw = await resp.text();
  let payload = {};
  try {
    payload = raw ? JSON.parse(raw) : {};
  } catch (error) {
    payload = {};
  }
  if (!resp.ok) {
    const fallback = raw ? raw.slice(0, 200) : `${TEXT.requestFail} (HTTP ${resp.status})`;
    throw new Error(payload.error || fallback);
  }
  return payload;
}

async function apiPost(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const raw = await resp.text();
  let payload = {};
  try {
    payload = raw ? JSON.parse(raw) : {};
  } catch (error) {
    payload = {};
  }
  if (!resp.ok) {
    const fallback = raw ? raw.slice(0, 200) : `${TEXT.requestFail} (HTTP ${resp.status})`;
    throw new Error(payload.error || fallback);
  }
  return payload;
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function stripHeadingDecoration(value) {
  return String(value || "").trim().replace(/^#{1,6}\s+/, "");
}

function isBulletLine(value) {
  return /^([-*]|\d+[.)])\s+/.test(String(value || "").trim());
}

function stripBullet(value) {
  return String(value || "").trim().replace(/^([-*]|\d+[.)])\s+/, "");
}

function splitBlocks(text) {
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let current = [];
  lines.forEach((line) => {
    if (!line.trim()) {
      if (current.length) {
        blocks.push(current);
        current = [];
      }
      return;
    }
    current.push(line.trim());
  });
  if (current.length) blocks.push(current);
  return blocks;
}

function getActiveEditorInput() {
  return activeEditorMode === "guided" ? pledgeRawTextGuidedInput : pledgeRawTextPlainInput;
}

function nextBlogId(type) {
  if (type === "goal") return `g-${blogGoalSeq++}`;
  if (type === "promise") return `p-${blogPromiseSeq++}`;
  return `i-${blogItemSeq++}`;
}

function normalizeBlogGoalTitle(sectionType) {
  const typeLabel = cleanText(sectionType);
  if (!typeLabel) return "";
  if (typeLabel === "목표") return "목 표";
  return typeLabel;
}

function goalsToBlogDraft(goals) {
  blogGoalSeq = 1;
  blogPromiseSeq = 1;
  blogItemSeq = 1;
  const nextGoals = [];
  (goals || []).forEach((goal) => {
    const goalTitle = cleanText(goal?.title || "");
    if (!goalTitle) return;
    const nextGoal = { id: nextBlogId("goal"), title: goalTitle, promises: [] };
    (goal.promises || []).forEach((promise) => {
      const promiseTitle = cleanText(promise?.title || "");
      if (!promiseTitle) return;
      const nextPromise = { id: nextBlogId("promise"), title: promiseTitle, items: [] };
      (promise.items || []).forEach((item) => {
        const itemText = cleanText(item?.detail || "");
        if (!itemText) return;
        nextPromise.items.push({ id: nextBlogId("item"), detail: itemText });
      });
      nextGoal.promises.push(nextPromise);
    });
    nextGoals.push(nextGoal);
  });
  return nextGoals;
}

function setBlogDraftFromGoals(goals) {
  blogDraftGoals = goalsToBlogDraft(goals);
  syncBlogRawTextFromDraft();
  populateBlogSelects();
  syncBlogComposerState();
  renderBlogStructureTree();
  renderPledgeSourceDraftRows();
}

function serializeBlogDraft() {
  return serializeTree(blogDraftGoals).trim();
}

function syncBlogRawTextFromDraft() {
  if (!pledgeRawTextPlainInput) return;
  pledgeRawTextPlainInput.value = serializeBlogDraft();
}

function populateBlogSelects() {
  if (blogParentGoalSelect) {
    const goalOptions = blogDraftGoals.length
      ? blogDraftGoals.map((goal, idx) => `<option value="${goal.id}">${escapeHtml(`${idx + 1}. ${goal.title}`)}</option>`).join("")
      : `<option value="">${TEXT.blogNeedGoal}</option>`;
    const currentGoalId = blogParentGoalSelect.value;
    blogParentGoalSelect.innerHTML = goalOptions;
    if (currentGoalId) blogParentGoalSelect.value = currentGoalId;
  }

  if (blogParentPromiseSelect) {
    const promiseOptions = [];
    blogDraftGoals.forEach((goal) => {
      (goal.promises || []).forEach((promise, idx) => {
        const label = `${goal.title} > ${idx + 1}. ${promise.title}`;
        promiseOptions.push(`<option value="${promise.id}">${escapeHtml(label)}</option>`);
      });
    });
    const currentPromiseId = blogParentPromiseSelect.value;
    blogParentPromiseSelect.innerHTML = promiseOptions.length
      ? promiseOptions.join("")
      : `<option value="">${TEXT.blogNeedPromise}</option>`;
    if (currentPromiseId) blogParentPromiseSelect.value = currentPromiseId;
  }
}

function syncBlogComposerState() {
  const type = cleanText(blogNodeTypeSelect?.value || "goal").toLowerCase();
  const isGoal = type === "goal";
  const isPromise = type === "promise";
  const isItem = type === "item";

  if (blogGoalTypeField) blogGoalTypeField.hidden = !isGoal;
  if (blogParentGoalField) blogParentGoalField.hidden = !isPromise;
  if (blogParentPromiseField) blogParentPromiseField.hidden = !isItem;
  if (blogNodeTextField) blogNodeTextField.hidden = isGoal;

  if (blogNodeTextInput) {
    if (isPromise) blogNodeTextInput.placeholder = "중항목 내용을 입력하세요";
    else if (isItem) blogNodeTextInput.placeholder = "세부항목 내용을 입력하세요";
    else blogNodeTextInput.placeholder = "";
  }

  if (addBlogNodeBtn) {
    if (isGoal) addBlogNodeBtn.textContent = "대항목 등록";
    else if (isPromise) addBlogNodeBtn.textContent = "중항목 등록";
    else addBlogNodeBtn.textContent = "세부항목 등록";
  }
}

function renderBlogStructureTree() {
  if (!blogStructureTreeEl) return;
  if (!blogDraftGoals.length) {
    blogStructureTreeEl.innerHTML = `<p class="blog-empty">${TEXT.blogEmpty}</p>`;
    return;
  }
  blogStructureTreeEl.innerHTML = blogDraftGoals.map((goal, goalIdx) => `
    <section class="blog-node goal">
      <header class="blog-node-head">
        <span class="blog-badge">대항목 ${goalIdx + 1}</span>
        <strong>${escapeHtml(goal.title)}</strong>
        <button type="button" class="blog-delete-btn" data-blog-action="delete-goal" data-goal-id="${goal.id}">삭제</button>
      </header>
      ${(goal.promises || []).length ? `
        <div class="blog-node-children">
          ${(goal.promises || []).map((promise, promiseIdx) => `
            <article class="blog-node promise">
              <header class="blog-node-head">
                <span class="blog-badge">중항목 ${promiseIdx + 1}</span>
                <strong>${escapeHtml(promise.title)}</strong>
                <button type="button" class="blog-delete-btn" data-blog-action="delete-promise" data-goal-id="${goal.id}" data-promise-id="${promise.id}">삭제</button>
              </header>
              ${(promise.items || []).length ? `
                <ul class="blog-item-list">
                  ${(promise.items || []).map((item) => `
                    <li>
                      <span>${escapeHtml(item.detail)}</span>
                      <button type="button" class="blog-delete-btn" data-blog-action="delete-item" data-goal-id="${goal.id}" data-promise-id="${promise.id}" data-item-id="${item.id}">삭제</button>
                    </li>
                  `).join("")}
                </ul>
              ` : `<p class="blog-empty-inline">${TEXT.noItems}</p>`}
            </article>
          `).join("")}
        </div>
      ` : `<p class="blog-empty-inline">${TEXT.noPromises}</p>`}
    </section>
  `).join("");
}

function setGuidedValidation(message = "") {
  if (!editorValidationMessageEl) return;
  editorValidationMessageEl.textContent = message;
  editorValidationMessageEl.hidden = !message;
}

function focusEditor() {
  if (activeEditorMode === "paste") {
    const type = cleanText(blogNodeTypeSelect?.value || "goal").toLowerCase();
    if (type === "goal") blogGoalTypeSelect?.focus();
    else blogNodeTextInput?.focus();
    return;
  }
  getActiveEditorInput()?.focus();
}

function syncEditors(fromMode, toMode) {
  if (fromMode === toMode) return;
  if (fromMode === "guided" && toMode === "paste") {
    const parsedGoals = parseEditorText(pledgeRawTextGuidedInput?.value || "");
    setBlogDraftFromGoals(parsedGoals);
    return;
  }
  if (fromMode === "paste" && toMode === "guided") {
    syncBlogRawTextFromDraft();
    if (pledgeRawTextGuidedInput) pledgeRawTextGuidedInput.value = pledgeRawTextPlainInput?.value || "";
  }
}

function openGoalMenu() {
  if (!goalOptionMenuEl || !goalMenuToggleBtn || activeEditorMode !== "guided") return;
  goalOptionMenuEl.hidden = false;
  goalMenuToggleBtn.setAttribute("aria-expanded", "true");
}

function closeGoalMenu() {
  if (!goalOptionMenuEl || !goalMenuToggleBtn) return;
  goalOptionMenuEl.hidden = true;
  goalMenuToggleBtn.setAttribute("aria-expanded", "false");
}

function toggleGoalMenu() {
  if (!goalOptionMenuEl || !goalMenuToggleBtn || activeEditorMode !== "guided") return;
  if (goalOptionMenuEl.hidden) {
    openGoalMenu();
    return;
  }
  closeGoalMenu();
}

function resolveGoalOption(optionValue) {
  const label = cleanText(optionValue);
  if (!label) return null;
  if (label !== GOAL_OPTION_OTHER) return label;
  const custom = window.prompt(TEXT.goalOtherPrompt, "");
  if (custom === null) return null;
  const customLabel = cleanText(custom);
  if (!customLabel) {
    setGuidedValidation(TEXT.goalOtherRequired);
    return null;
  }
  return customLabel;
}

function insertGoalOption(label) {
  const title = cleanText(label);
  if (!title) return;
  insertIntoEditor(`\u25a1 ${title} `, "line");
}

function setEditorMode(mode) {
  activeEditorMode = mode === "guided" ? "guided" : "paste";
  if (activeEditorMode !== "guided") closeGoalMenu();
  editorModeTabs.forEach((button) => {
    const isActive = button.dataset.editorMode === activeEditorMode;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  editorPanels.forEach((panel) => {
    const isActive = panel.dataset.editorPanel === activeEditorMode;
    panel.classList.toggle("active", isActive);
    panel.classList.toggle("is-active", isActive);
    panel.hidden = !isActive;
  });
  setGuidedValidation(activeEditorMode === "guided" ? validateGuidedEditor(pledgeRawTextGuidedInput?.value || "") : "");
  renderPledgeSourceDraftRows();
}

function getLineContext(value, cursor) {
  const safeCursor = Math.max(0, Math.min(cursor, value.length));
  const lineStart = value.lastIndexOf("\n", safeCursor - 1) + 1;
  const lineEndIndex = value.indexOf("\n", safeCursor);
  const lineEnd = lineEndIndex === -1 ? value.length : lineEndIndex;
  const line = value.slice(lineStart, lineEnd);
  return { lineStart, lineEnd, line };
}

function getLeadingToken(line) {
  if (line.startsWith(" \u25a1 ")) return " \u25a1 ";
  if (line.startsWith(" \u25cb ")) return " \u25cb ";
  if (line.startsWith(" - ")) return " - ";
  if (line.startsWith("\u25a1 ")) return "\u25a1 ";
  if (line.startsWith("\u25cb ")) return "\u25cb ";
  if (line.startsWith("- ")) return "- ";
  return "";
}

function validateGuidedEditor(text) {
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  for (const rawLine of lines) {
    const line = String(rawLine || "");
    if (!line) continue;
    const normalized = line.trimStart();
    if (/^(?:\u25a1|\u25cb|-)\s*$/.test(normalized)) return TEXT.guidedNeedTextAfterMarker;
  }
  return "";
}

function insertIntoEditor(token, mode = "cursor") {
  if (!pledgeRawTextGuidedInput) return;

  const input = pledgeRawTextGuidedInput;
  const value = input.value || "";
  const start = input.selectionStart ?? value.length;
  const end = input.selectionEnd ?? start;
  let chunk = token;

  if (mode === "line") {
    const before = value.slice(0, start);
    const after = value.slice(end);
    const needsLeadingBreak = before.length > 0 && !before.endsWith("\n");
    const needsTrailingBreak = after.length > 0 && !after.startsWith("\n");
    chunk = `${needsLeadingBreak ? "\n" : ""}${token}${needsTrailingBreak ? "\n" : ""}`;
  }

  const nextValue = `${value.slice(0, start)}${chunk}${value.slice(end)}`;
  const caret = start + chunk.length;
  input.value = nextValue;
  input.focus();
  input.setSelectionRange(caret, caret);
  setGuidedValidation(validateGuidedEditor(nextValue));
}

function handleEditorShortcut(event) {
  if (!pledgeRawTextGuidedInput || event.defaultPrevented || !event.altKey || event.shiftKey || event.ctrlKey || event.metaKey) return;

  if (event.key === "1") {
    event.preventDefault();
    insertIntoEditor("\u25a1 \ubaa9 \ud45c ", "line");
  } else if (event.key === "2") {
    event.preventDefault();
    insertIntoEditor("\u25cb ", "line");
  } else if (event.key === "3") {
    event.preventDefault();
    insertIntoEditor("- ", "line");
  }
}

function parseMarkedLines(lines) {
  const goals = [];
  let currentGoal = null;
  let currentPromise = null;
  let currentItem = null;

  lines.forEach((rawLine) => {
    const line = String(rawLine || "").trim();
    if (!line) {
      currentItem = null;
      return;
    }

    if (/^\u25a1\s+/.test(line)) {
      const title = cleanText(line.replace(/^\u25a1\s+/, ""));
      if (!title) return;
      currentGoal = { title, promises: [] };
      goals.push(currentGoal);
      currentPromise = null;
      currentItem = null;
      return;
    }

    if (/^\u25cb\s+/.test(line)) {
      const title = cleanText(line.replace(/^\u25cb\s+/, ""));
      if (!title) return;
      if (!currentGoal) {
        currentGoal = { title: TEXT.defaultGoal, promises: [] };
        goals.push(currentGoal);
      }
      currentPromise = { title, items: [] };
      currentGoal.promises.push(currentPromise);
      currentItem = null;
      return;
    }

    if (/^-\s+/.test(line) || isBulletLine(line)) {
      const detail = cleanText(stripBullet(line));
      if (!detail) return;
      if (!currentGoal) {
        currentGoal = { title: TEXT.defaultGoal, promises: [] };
        goals.push(currentGoal);
      }
      if (!currentPromise) {
        currentPromise = { title: TEXT.defaultPromise, items: [] };
        currentGoal.promises.push(currentPromise);
      }
      currentItem = { detail };
      currentPromise.items.push(currentItem);
      return;
    }

    const content = cleanText(stripHeadingDecoration(line));
    if (!content) return;
    if (currentItem) {
      currentItem.detail = `${currentItem.detail} ${content}`.trim();
      return;
    }
    if (currentPromise) {
      currentPromise.title = `${currentPromise.title} ${content}`.trim();
      return;
    }
    if (currentGoal) {
      currentGoal.title = `${currentGoal.title} ${content}`.trim();
      return;
    }
    currentGoal = { title: content, promises: [] };
    goals.push(currentGoal);
  });

  return goals.filter((goal) => cleanText(goal.title));
}
function parseBlogBlocks(blocks) {
  const goals = [];
  let currentGoal = null;

  blocks.forEach((block) => {
    const lines = block.map((line) => String(line || "").trim()).filter(Boolean);
    if (!lines.length) return;
    const proseLines = lines.filter((line) => !isBulletLine(line));
    const bulletLines = lines.filter((line) => isBulletLine(line));

    if (!currentGoal) {
      const goalTitle = cleanText(stripHeadingDecoration(proseLines[0] || stripBullet(lines[0])));
      if (!goalTitle) return;
      currentGoal = { title: goalTitle, promises: [] };
      goals.push(currentGoal);

      const remainingProse = proseLines.slice(proseLines.length ? 1 : 0).map((line) => cleanText(stripHeadingDecoration(line))).filter(Boolean);
      if (remainingProse.length || bulletLines.length) {
        const promise = { title: remainingProse.shift() || TEXT.defaultPromise, items: [] };
        remainingProse.forEach((line) => promise.items.push({ detail: line }));
        bulletLines.forEach((line) => promise.items.push({ detail: cleanText(stripBullet(line)) }));
        if (cleanText(promise.title) || promise.items.length) currentGoal.promises.push(promise);
      }
      return;
    }

    if (proseLines.length) {
      const promise = { title: cleanText(stripHeadingDecoration(proseLines[0])), items: [] };
      proseLines.slice(1).map((line) => cleanText(stripHeadingDecoration(line))).filter(Boolean).forEach((line) => promise.items.push({ detail: line }));
      bulletLines.map((line) => cleanText(stripBullet(line))).filter(Boolean).forEach((line) => promise.items.push({ detail: line }));
      if (cleanText(promise.title)) currentGoal.promises.push(promise);
      return;
    }

    bulletLines.map((line) => cleanText(stripBullet(line))).filter(Boolean).forEach((line) => currentGoal.promises.push({ title: line, items: [] }));
  });

  return goals.filter((goal) => cleanText(goal.title));
}

function parseEditorText(text) {
  const blocks = splitBlocks(text);
  if (!blocks.length) return [];
  const flatLines = blocks.flat();
  const hasExplicitMarkers = flatLines.some((line) => /^(?:\u25a1|\u25cb)\s+/.test(String(line || "").trim()));
  return hasExplicitMarkers ? parseMarkedLines(flatLines) : parseBlogBlocks(blocks);
}

function serializeTree(goals) {
  const lines = [];
  goals.forEach((goal) => {
    if (!cleanText(goal.title)) return;
    lines.push(`\u25a1 ${cleanText(goal.title)}`);
    (goal.promises || []).forEach((promise) => {
      if (!cleanText(promise.title)) return;
      lines.push(`\u25cb ${cleanText(promise.title)}`);
      (promise.items || []).forEach((item) => {
        if (!cleanText(item.detail)) return;
        lines.push(`- ${cleanText(item.detail)}`);
      });
    });
  });
  return lines.join("\n");
}

function getParsedModel(text) {
  const goals = parseEditorText(text);
  const normalizedText = serializeTree(goals).trim();
  return { goals, normalizedText };
}

function normalizeNodeSourceRole(value) {
  const raw = cleanText(value);
  const compact = raw.toLowerCase().replace(/\s+/g, "");
  const mapping = {
    "공식공약집": "원문출처",
    "원문출처": "원문출처",
    "보조근거": "참고출처",
    "참고출처": "참고출처",
    "관련자료": "관련자료",
    "관련출처": "관련자료",
  };
  return mapping[compact] || "참고출처";
}

function normalizeSourceTypeForApi(value) {
  const raw = cleanText(value);
  return raw || "기타";
}

function getReusablePledgeOptions() {
  if (!Array.isArray(reusableSourceRows) || !reusableSourceRows.length) return [];
  const byId = new Map();
  reusableSourceRows.forEach((row) => {
    (row?.links || []).forEach((link) => {
      const pledgeId = cleanText(link?.pledge_id || "");
      if (!pledgeId || byId.has(pledgeId)) return;
      const pledgeTitle = cleanText(link?.pledge_title || "") || `공약 ${pledgeId}`;
      byId.set(pledgeId, { value: pledgeId, label: pledgeTitle });
    });
  });
  return Array.from(byId.values());
}

function getReusableSourceOptions(reusePledgeId = "") {
  if (!Array.isArray(reusableSourceRows) || !reusableSourceRows.length) return [];
  const pledgeIdFilter = cleanText(reusePledgeId || "");
  return reusableSourceRows.map((row, idx) => {
    const links = Array.isArray(row?.links) ? row.links : [];
    if (pledgeIdFilter) {
      const matched = links.some((link) => String(link?.pledge_id || "") === pledgeIdFilter);
      if (!matched) return null;
    }
    const title = cleanText(row?.title || "") || `기존 출처 ${idx + 1}`;
    const sourceType = cleanText(row?.source_type || "");
    const publisher = cleanText(row?.publisher || "");
    const used = Number(row?.usage_count || 0);
    const representativePledge = cleanText((links[0] || {})?.pledge_title || "");
    const parts = [title];
    if (representativePledge) parts.push(`공약: ${representativePledge}`);
    if (publisher) parts.push(publisher);
    if (sourceType) parts.push(sourceType);
    if (used > 0) parts.push(`사용 ${used}회`);
    return {
      value: String(row?.source_id || ""),
      label: parts.join(" · "),
    };
  }).filter((row) => row && row.value);
}

function findReusableSourceRow(sourceId, reusePledgeId = "") {
  const id = cleanText(sourceId);
  if (!id) return null;
  const pledgeIdFilter = cleanText(reusePledgeId || "");
  return reusableSourceRows.find((row) => {
    if (String(row?.source_id || "") !== id) return false;
    if (!pledgeIdFilter) return true;
    return (row?.links || []).some((link) => String(link?.pledge_id || "") === pledgeIdFilter);
  }) || null;
}

function applyReusableSourceToDraftRow(row, sourceId) {
  if (!row) return;
  const source = findReusableSourceRow(sourceId, row.reusePledgeId);
  if (!source) return;
  row.sourceId = String(source.source_id || "");
  row.title = cleanText(source.title || row.title || "");
  row.url = cleanText(source.url || "");
  row.sourceType = cleanText(source.source_type || row.sourceType || SOURCE_TYPE_OPTIONS[0]) || SOURCE_TYPE_OPTIONS[0];
  row.publisher = cleanText(source.publisher || "");
  row.publishedAt = cleanText(source.published_at || "");
  row.summary = cleanText(source.summary || "");
  if (!cleanText(row.note)) row.note = cleanText(source.note || "");
}

async function refreshReusableSources() {
  const candidateElectionId = cleanText(candidateElectionSelect?.value || "");
  if (!candidateElectionId) {
    reusableSourceRows = [];
    pledgeSourceDraftRows.forEach((row) => {
      row.sourceMode = SOURCE_MODE_NEW;
      row.sourceId = "";
    });
    renderPledgeSourceDraftRows();
    return;
  }
  const payload = await apiGet(`/api/pledges/source-library?candidate_election_id=${encodeURIComponent(candidateElectionId)}`);
  reusableSourceRows = Array.isArray(payload?.rows) ? payload.rows : [];
  if (!reusableSourceRows.length) {
    pledgeSourceDraftRows.forEach((row) => {
      if (cleanText(row.sourceMode || SOURCE_MODE_NEW) === SOURCE_MODE_REUSE) {
        row.sourceMode = SOURCE_MODE_NEW;
      }
      row.sourceId = "";
    });
    renderPledgeSourceDraftRows();
    return;
  }
  const pledgeOptions = getReusablePledgeOptions();
  const defaultReusePledgeId = pledgeOptions[0]?.value || "";
  pledgeSourceDraftRows.forEach((row) => {
    if (cleanText(row.sourceMode || SOURCE_MODE_NEW) !== SOURCE_MODE_REUSE) return;
    if (!cleanText(row.reusePledgeId) && defaultReusePledgeId) {
      row.reusePledgeId = defaultReusePledgeId;
    }
    const sourceOptions = getReusableSourceOptions(row.reusePledgeId);
    if (!cleanText(row.sourceId) && sourceOptions.length) {
      applyReusableSourceToDraftRow(row, sourceOptions[0]?.value);
      return;
    }
    if (cleanText(row.sourceId)) applyReusableSourceToDraftRow(row, row.sourceId);
  });
  renderPledgeSourceDraftRows();
}

function getSourceTargetGoals() {
  if (activeEditorMode === "guided") {
    return parseEditorText(pledgeRawTextGuidedInput?.value || "");
  }
  return blogDraftGoals || [];
}

function getPledgeSourceTargetOptions() {
  const options = [];
  const goals = getSourceTargetGoals();

  goals.forEach((goal, goalIdx) => {
    const goalTitle = cleanText(goal?.title || "") || `대항목 ${goalIdx + 1}`;
    const goalPath = `g:${goalIdx + 1}`;
    options.push({ value: goalPath, label: `${goalIdx + 1}. ${goalTitle}` });
  });

  return options;
}

function createEmptySourceRow() {
  const pledgeOptions = getReusablePledgeOptions();
  const reusePledgeId = pledgeOptions[0]?.value || "";
  const reusableOptions = getReusableSourceOptions(reusePledgeId);
  const firstReusableId = reusableOptions[0]?.value || "";
  return {
    id: `src-${pledgeSourceSeq++}`,
    linkScope: SOURCE_LINK_SCOPE_PLEDGE,
    targetPath: "",
    sourceMode: SOURCE_MODE_NEW,
    reusePledgeId,
    sourceId: firstReusableId,
    sourceRole: SOURCE_ROLE_OPTIONS[0],
    title: "",
    url: "",
    sourceType: SOURCE_TYPE_OPTIONS[0],
    publisher: "",
    publishedAt: "",
    summary: "",
    note: "",
  };
}

function renderPledgeSourceDraftRows() {
  if (!pledgeSourceListEl) return;

  if (!pledgeSourceDraftRows.length) {
    pledgeSourceListEl.innerHTML = `<p class="source-empty">${TEXT.sourceEmpty}</p>`;
    return;
  }

  const targetOptions = getPledgeSourceTargetOptions();
  const pledgeOptions = getReusablePledgeOptions();
  pledgeSourceListEl.innerHTML = pledgeSourceDraftRows.map((row, idx) => {
    const selectedScope = cleanText(row.linkScope || SOURCE_LINK_SCOPE_PLEDGE) === SOURCE_LINK_SCOPE_GOAL
      ? SOURCE_LINK_SCOPE_GOAL
      : SOURCE_LINK_SCOPE_PLEDGE;
    const selectedSourceMode = cleanText(row.sourceMode || SOURCE_MODE_NEW) === SOURCE_MODE_REUSE
      ? SOURCE_MODE_REUSE
      : SOURCE_MODE_NEW;
    const selectedReusePledgeId = cleanText(row.reusePledgeId || "");
    const reusableOptions = getReusableSourceOptions(selectedReusePledgeId);
    const selectedSourceId = cleanText(row.sourceId || "");
    const selectedTargetPath = cleanText(row.targetPath || "");
    const targetOptionHtml = targetOptions
      .map((option) => `<option value="${escapeHtml(option.value)}" ${selectedTargetPath === option.value ? "selected" : ""}>${escapeHtml(option.label)}</option>`)
      .join("");
    const pledgeOptionHtml = pledgeOptions.length
      ? pledgeOptions.map((option) => `<option value="${escapeHtml(option.value)}" ${selectedReusePledgeId === option.value ? "selected" : ""}>${escapeHtml(option.label)}</option>`).join("")
      : `<option value="">공약 없음</option>`;
    const reusableOptionHtml = reusableOptions.length
      ? reusableOptions.map((option) => `<option value="${escapeHtml(option.value)}" ${selectedSourceId === option.value ? "selected" : ""}>${escapeHtml(option.label)}</option>`).join("")
      : `<option value="">재사용 가능한 출처 없음</option>`;
    const scopeOptions = `
      <option value="${SOURCE_LINK_SCOPE_PLEDGE}" ${selectedScope === SOURCE_LINK_SCOPE_PLEDGE ? "selected" : ""}>공약(pledges.id) 연결</option>
      <option value="${SOURCE_LINK_SCOPE_GOAL}" ${selectedScope === SOURCE_LINK_SCOPE_GOAL ? "selected" : ""}>대항목(goal) 연결</option>
    `;
    const sourceModeOptions = `
      <option value="${SOURCE_MODE_NEW}" ${selectedSourceMode === SOURCE_MODE_NEW ? "selected" : ""}>새 출처 입력</option>
      <option value="${SOURCE_MODE_REUSE}" ${selectedSourceMode === SOURCE_MODE_REUSE ? "selected" : ""}>기존 출처 재사용</option>
    `;
    const disableSourceInputs = selectedSourceMode === SOURCE_MODE_REUSE ? "disabled" : "";
    const roleOptions = SOURCE_ROLE_OPTIONS.map((role) => `<option value="${escapeHtml(role)}" ${row.sourceRole === role ? "selected" : ""}>${escapeHtml(role)}</option>`).join("");
    const typeOptions = SOURCE_TYPE_OPTIONS.map((type) => `<option value="${escapeHtml(type)}" ${row.sourceType === type ? "selected" : ""}>${escapeHtml(type)}</option>`).join("");

    return `
      <article class="source-item" data-source-row-id="${row.id}">
        <div class="source-item-head">
          <strong>출처 ${idx + 1}</strong>
          <button type="button" class="source-remove-btn" data-source-action="remove" data-source-row-id="${row.id}">삭제</button>
        </div>
        <div class="source-item-grid">
          <div class="full">
            <label>연결 범위</label>
            <select data-source-field="linkScope">${scopeOptions}</select>
          </div>
          <div class="full">
            <label>출처 입력 방식</label>
            <select data-source-field="sourceMode">${sourceModeOptions}</select>
          </div>
          <div class="full" ${selectedSourceMode === SOURCE_MODE_REUSE ? "" : 'style="display:none;"'}>
            <label>기존 공약 선택</label>
            <select data-source-field="reusePledgeId" ${pledgeOptions.length ? "" : "disabled"}>${pledgeOptionHtml}</select>
          </div>
          <div class="full" ${selectedSourceMode === SOURCE_MODE_REUSE ? "" : 'style="display:none;"'}>
            <label>기존 출처 선택</label>
            <select data-source-field="sourceId" ${reusableOptions.length ? "" : "disabled"}>${reusableOptionHtml}</select>
          </div>
          <div class="full" ${selectedScope === SOURCE_LINK_SCOPE_GOAL ? "" : 'style="display:none;"'}>
            <label>연결 대상 대항목(goal)</label>
            <select data-source-field="targetPath">${targetOptionHtml}</select>
          </div>
          <div>
            <label>출처 역할</label>
            <select data-source-field="sourceRole">${roleOptions}</select>
          </div>
          <div class="full">
            <label>출처 제목</label>
            <input type="text" data-source-field="title" value="${escapeHtml(row.title)}" placeholder="예: 제21대 대통령선거 후보자 공약집" ${disableSourceInputs} />
          </div>
          <div class="full">
            <label>URL</label>
            <input type="url" data-source-field="url" value="${escapeHtml(row.url)}" placeholder="https://..." ${disableSourceInputs} />
          </div>
          <div>
            <label>출처 유형</label>
            <select data-source-field="sourceType" ${disableSourceInputs}>${typeOptions}</select>
          </div>
          <div>
            <label>발행 기관</label>
            <input type="text" data-source-field="publisher" value="${escapeHtml(row.publisher)}" placeholder="예: 중앙선거관리위원회" ${disableSourceInputs} />
          </div>
          <div>
            <label>발행일</label>
            <input type="date" data-source-field="publishedAt" value="${escapeHtml(row.publishedAt)}" ${disableSourceInputs} />
          </div>
          <div class="full">
            <label>요약</label>
            <input type="text" data-source-field="summary" value="${escapeHtml(row.summary)}" placeholder="출처 요약" ${disableSourceInputs} />
          </div>
          <div class="full">
            <label>메모</label>
            <input type="text" data-source-field="note" value="${escapeHtml(row.note)}" placeholder="출처 설명 또는 연결 메모" />
          </div>
        </div>
      </article>
    `;
  }).join("");
}

function addPledgeSourceRow() {
  pledgeSourceDraftRows.push(createEmptySourceRow());
  renderPledgeSourceDraftRows();
}

function removePledgeSourceRow(rowId) {
  pledgeSourceDraftRows = pledgeSourceDraftRows.filter((row) => String(row.id) !== String(rowId));
  renderPledgeSourceDraftRows();
}

function updatePledgeSourceRowField(rowId, field, value) {
  const row = pledgeSourceDraftRows.find((item) => String(item.id) === String(rowId));
  if (!row || !field) return;
  if (field === "linkScope") {
    row.linkScope = cleanText(value) === SOURCE_LINK_SCOPE_GOAL ? SOURCE_LINK_SCOPE_GOAL : SOURCE_LINK_SCOPE_PLEDGE;
    if (row.linkScope === SOURCE_LINK_SCOPE_PLEDGE) row.targetPath = "";
    if (row.linkScope === SOURCE_LINK_SCOPE_GOAL && !cleanText(row.targetPath || "")) {
      const goals = getPledgeSourceTargetOptions();
      if (goals.length) row.targetPath = goals[0].value;
    }
    renderPledgeSourceDraftRows();
    return;
  }
  if (field === "sourceMode") {
    row.sourceMode = cleanText(value) === SOURCE_MODE_REUSE ? SOURCE_MODE_REUSE : SOURCE_MODE_NEW;
    if (row.sourceMode === SOURCE_MODE_REUSE) {
      const pledgeOptions = getReusablePledgeOptions();
      const defaultReusePledgeId = pledgeOptions[0]?.value || "";
      if (!cleanText(row.reusePledgeId || "") && defaultReusePledgeId) {
        row.reusePledgeId = defaultReusePledgeId;
      }
      const options = getReusableSourceOptions(row.reusePledgeId);
      if (!options.length) {
        row.sourceMode = SOURCE_MODE_NEW;
        setMessage("재사용 가능한 기존 출처가 없습니다. 새 출처를 입력해 주세요.", "info");
      } else {
        const preferredId = cleanText(row.sourceId || "") || options[0].value;
        applyReusableSourceToDraftRow(row, preferredId);
      }
    }
    renderPledgeSourceDraftRows();
    return;
  }
  if (field === "reusePledgeId") {
    row.reusePledgeId = cleanText(value);
    const options = getReusableSourceOptions(row.reusePledgeId);
    if (!options.length) {
      row.sourceId = "";
      renderPledgeSourceDraftRows();
      return;
    }
    const nextSourceId = options.some((option) => option.value === cleanText(row.sourceId || ""))
      ? cleanText(row.sourceId || "")
      : options[0].value;
    applyReusableSourceToDraftRow(row, nextSourceId);
    renderPledgeSourceDraftRows();
    return;
  }
  if (field === "sourceId") {
    row.sourceId = cleanText(value);
    if (row.sourceMode === SOURCE_MODE_REUSE) {
      applyReusableSourceToDraftRow(row, row.sourceId);
    }
    renderPledgeSourceDraftRows();
    return;
  }
  row[field] = value;
}

function resetPledgeSourceRows() {
  pledgeSourceDraftRows = [];
  renderPledgeSourceDraftRows();
}

function collectPledgeSourceRowsForSave() {
  if (!pledgeSourceDraftRows.length) throw new Error(TEXT.sourceNeedAtLeastOne);
  const goals = getPledgeSourceTargetOptions();
  const goalPathSet = new Set(goals.map((goal) => goal.value));
  const collected = pledgeSourceDraftRows.map((row) => {
    const linkScope = cleanText(row.linkScope || SOURCE_LINK_SCOPE_PLEDGE) === SOURCE_LINK_SCOPE_GOAL
      ? SOURCE_LINK_SCOPE_GOAL
      : SOURCE_LINK_SCOPE_PLEDGE;
    const sourceMode = cleanText(row.sourceMode || SOURCE_MODE_NEW) === SOURCE_MODE_REUSE
      ? SOURCE_MODE_REUSE
      : SOURCE_MODE_NEW;
    const sourceId = cleanText(row.sourceId || "") || null;
    const title = cleanText(row.title);
    if (sourceMode === SOURCE_MODE_REUSE && !sourceId) throw new Error(TEXT.sourceNeedReusable);
    if (sourceMode !== SOURCE_MODE_REUSE && !title) throw new Error(TEXT.sourceNeedTitle);

    return {
      source_id: sourceId,
      link_scope: linkScope,
      target_path: linkScope === SOURCE_LINK_SCOPE_GOAL
        ? (cleanText(row.targetPath || "") || null)
        : null,
      source_role: normalizeNodeSourceRole(row.sourceRole),
      title: title || null,
      url: cleanText(row.url) || null,
      source_type: normalizeSourceTypeForApi(row.sourceType),
      publisher: cleanText(row.publisher) || null,
      published_at: cleanText(row.publishedAt) || null,
      summary: cleanText(row.summary) || null,
      note: cleanText(row.note) || null,
    };
  });
  const goalScopedRows = collected.filter((row) => row.link_scope === SOURCE_LINK_SCOPE_GOAL);
  if (goalScopedRows.length) {
    if (!goals.length) throw new Error("대항목(goal)이 없어 goal 연결을 사용할 수 없습니다.");
    const assigned = new Set();
    goalScopedRows.forEach((row) => {
      if (!row.target_path || !goalPathSet.has(row.target_path)) {
        throw new Error("goal 연결 대상은 대항목(goal)만 선택할 수 있습니다.");
      }
      assigned.add(row.target_path);
    });
    const missing = goals.filter((goal) => !assigned.has(goal.value));
    if (missing.length) {
      const missingNames = missing.map((goal) => goal.label).join(", ");
      throw new Error(`goal 연결을 선택한 경우 모든 대항목에 출처가 필요합니다: ${missingNames}`);
    }
  }
  return collected;
}

function findBlogGoal(goalId) {
  return blogDraftGoals.find((goal) => String(goal.id) === String(goalId)) || null;
}

function findBlogPromise(promiseId) {
  for (const goal of blogDraftGoals) {
    const promise = (goal.promises || []).find((row) => String(row.id) === String(promiseId));
    if (promise) return { goal, promise };
  }
  return null;
}

function addBlogNode() {
  const nodeType = cleanText(blogNodeTypeSelect?.value || "").toLowerCase();
  const nodeText = cleanText(blogNodeTextInput?.value || "");
  if (!nodeType) throw new Error(TEXT.blogNeedNodeType);

  if (nodeType === "goal") {
    const sectionType = cleanText(blogGoalTypeSelect?.value || "");
    if (!sectionType) throw new Error(TEXT.blogNeedGoalType);
    const title = normalizeBlogGoalTitle(sectionType);
    if (!title) throw new Error(TEXT.blogNeedGoalType);
    blogDraftGoals.push({ id: nextBlogId("goal"), title, promises: [] });
  } else if (nodeType === "promise") {
    const goalId = cleanText(blogParentGoalSelect?.value || "");
    if (!goalId || !nodeText) throw new Error(TEXT.blogNeedPromise);
    const goal = findBlogGoal(goalId);
    if (!goal) throw new Error(TEXT.blogNeedGoal);
    goal.promises.push({ id: nextBlogId("promise"), title: nodeText, items: [] });
  } else if (nodeType === "item") {
    const promiseId = cleanText(blogParentPromiseSelect?.value || "");
    if (!promiseId || !nodeText) throw new Error(TEXT.blogNeedItem);
    const found = findBlogPromise(promiseId);
    if (!found) throw new Error(TEXT.blogNeedPromise);
    found.promise.items.push({ id: nextBlogId("item"), detail: nodeText });
  } else {
    throw new Error(TEXT.blogNeedNodeType);
  }

  if (blogNodeTextInput) blogNodeTextInput.value = "";
  syncBlogRawTextFromDraft();
  populateBlogSelects();
  syncBlogComposerState();
  renderBlogStructureTree();
}

function deleteBlogNode(action, goalId, promiseId, itemId) {
  if (action === "delete-goal") {
    if (!window.confirm(TEXT.confirmDeleteGoalNode)) return;
    blogDraftGoals = blogDraftGoals.filter((goal) => String(goal.id) !== String(goalId));
  } else if (action === "delete-promise") {
    if (!window.confirm(TEXT.confirmDeletePromiseNode)) return;
    const goal = findBlogGoal(goalId);
    if (goal) goal.promises = (goal.promises || []).filter((promise) => String(promise.id) !== String(promiseId));
  } else if (action === "delete-item") {
    if (!window.confirm(TEXT.confirmDeleteItemNode)) return;
    const found = findBlogPromise(promiseId);
    if (found) found.promise.items = (found.promise.items || []).filter((item) => String(item.id) !== String(itemId));
  }
  syncBlogRawTextFromDraft();
  populateBlogSelects();
  renderBlogStructureTree();
}

function getCandidateMap() { return new Map(candidates.map((row) => [String(row.id), row])); }
function getElectionMap() { return new Map(elections.map((row) => [String(row.id), row])); }

function populateCandidateElectionSelects() {
  const candidateMap = getCandidateMap();
  const electionMap = getElectionMap();
  const options = candidateElections.map((row) => {
    const candidate = candidateMap.get(String(row.candidate_id));
    const election = electionMap.get(String(row.election_id));
    const candidateName = candidate?.name || `${TEXT.candidateId}${row.candidate_id}`;
    const electionTitle = election?.title || `${TEXT.electionId}${row.election_id}`;
    const result = row.result || TEXT.noResult;
    return `<option value="${row.id}">${escapeHtml(candidateName)} · ${escapeHtml(electionTitle)} · ${escapeHtml(result)}</option>`;
  }).join("");

  if (candidateElectionSelect) {
    const current = candidateElectionSelect.value;
    candidateElectionSelect.innerHTML = `<option value="">${TEXT.selectCandidateElection}</option>${options}`;
    if (current) candidateElectionSelect.value = current;
  }
}

function resetParserForm() {
  pledgeForm?.reset();
  closeGoalMenu();
  setBlogDraftFromGoals([]);
  if (pledgeRawTextGuidedInput) pledgeRawTextGuidedInput.value = "";
  resetPledgeSourceRows();
  setGuidedValidation("");
  focusEditor();
}

function buildParserPayload() {
  const candidateElectionId = candidateElectionSelect?.value;
  const candidateElection = candidateElections.find((row) => String(row.id) === String(candidateElectionId));
  if (!candidateElectionId || !candidateElection) throw new Error(TEXT.needCandidateElection);

  const title = (pledgeTitleInput?.value || "").trim();
  const category = (pledgeCategoryInput?.value || "").trim();
  if (!title || !category) throw new Error(TEXT.needTitleCategory);

  let normalizedText = "";
  if (activeEditorMode === "paste") {
    normalizedText = serializeBlogDraft();
  } else {
    const editorValue = pledgeRawTextGuidedInput?.value || "";
    const guidedValidation = validateGuidedEditor(editorValue);
    if (guidedValidation) throw new Error(guidedValidation);
    normalizedText = getParsedModel(editorValue).normalizedText;
  }
  if (!normalizedText) throw new Error(TEXT.parseFail);

  const sortRaw = (pledgeSortOrderInput?.value || "").trim();
  let sort_order = null;
  if (sortRaw) {
    const n = Number(sortRaw);
    if (!Number.isFinite(n) || n < 1) throw new Error(TEXT.badSort);
    sort_order = Math.floor(n);
  }

  return { candidate_election_id: candidateElection.id, sort_order, title, raw_text: normalizedText, category, status: "active" };
}

async function refreshAllData() {
  const [candidateResp, electionResp, candidateElectionResp] = await Promise.all([
    apiGet("/api/candidate-admin/candidates"),
    apiGet("/api/candidate-admin/elections"),
    apiGet("/api/candidate-admin/candidate-elections"),
  ]);
  candidates = candidateResp.rows || [];
  elections = electionResp.rows || [];
  candidateElections = candidateElectionResp.rows || [];
  populateCandidateElectionSelects();
  await refreshReusableSources();
}

function handleGuidedEditorKeydown(event) {
  const input = pledgeRawTextGuidedInput;
  if (!input) return;

  handleEditorShortcut(event);
  if (event.defaultPrevented) return;

  const value = input.value || "";
  const start = input.selectionStart ?? 0;
  const end = input.selectionEnd ?? start;
  const { lineStart, line } = getLineContext(value, start);
  const token = getLeadingToken(line);
  const tokenEnd = lineStart + token.length;
  const atProtectedToken = token && start === end && start >= lineStart && start < tokenEnd;

  if (event.key === "Backspace" && start === end && token) {
    if (start > lineStart && start <= tokenEnd) {
      event.preventDefault();
      input.value = `${value.slice(0, lineStart)}${value.slice(tokenEnd)}`;
      input.setSelectionRange(lineStart, lineStart);
      setGuidedValidation(validateGuidedEditor(input.value));
      return;
    }
  }

  if (event.key === "Delete" && start === end && token) {
    if (start >= lineStart && start < tokenEnd) {
      event.preventDefault();
      input.value = `${value.slice(0, lineStart)}${value.slice(tokenEnd)}`;
      input.setSelectionRange(lineStart, lineStart);
      setGuidedValidation(validateGuidedEditor(input.value));
      return;
    }
  }

  if (atProtectedToken && event.key.length === 1 && event.key !== " " && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault();
    input.setSelectionRange(tokenEnd, tokenEnd);
    setGuidedValidation(TEXT.guidedTokenProtected);
  }
}

pledgeRawTextGuidedInput?.addEventListener("input", () => {
  setGuidedValidation(validateGuidedEditor(pledgeRawTextGuidedInput.value || ""));
  renderPledgeSourceDraftRows();
});

pledgeRawTextGuidedInput?.addEventListener("keydown", handleGuidedEditorKeydown);
candidateElectionSelect?.addEventListener("change", async () => {
  try {
    await refreshReusableSources();
  } catch (error) {
    reusableSourceRows = [];
    renderPledgeSourceDraftRows();
    setMessage(error.message || TEXT.requestFail, "error");
  }
});
blogNodeTypeSelect?.addEventListener("change", () => {
  syncBlogComposerState();
});
addBlogNodeBtn?.addEventListener("click", () => {
  try {
    addBlogNode();
  } catch (error) {
    setMessage(error.message || TEXT.requestFail, "error");
  }
});
blogStructureTreeEl?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-blog-action]");
  if (!button) return;
  const action = button.getAttribute("data-blog-action");
  const goalId = button.getAttribute("data-goal-id");
  const promiseId = button.getAttribute("data-promise-id");
  const itemId = button.getAttribute("data-item-id");
  deleteBlogNode(action, goalId, promiseId, itemId);
});

addPledgeSourceBtn?.addEventListener("click", () => {
  try {
    addPledgeSourceRow();
  } catch (error) {
    setMessage(error.message || TEXT.sourceSaveFail, "error");
  }
});

pledgeSourceListEl?.addEventListener("click", (event) => {
  const removeButton = event.target.closest("button[data-source-action='remove']");
  if (!removeButton) return;
  removePledgeSourceRow(removeButton.getAttribute("data-source-row-id"));
});

pledgeSourceListEl?.addEventListener("input", (event) => {
  const rowEl = event.target.closest("[data-source-row-id]");
  const field = event.target.getAttribute("data-source-field");
  if (!rowEl || !field) return;
  updatePledgeSourceRowField(rowEl.getAttribute("data-source-row-id"), field, event.target.value);
});

pledgeSourceListEl?.addEventListener("change", (event) => {
  const rowEl = event.target.closest("[data-source-row-id]");
  const field = event.target.getAttribute("data-source-field");
  if (!rowEl || !field) return;
  updatePledgeSourceRowField(rowEl.getAttribute("data-source-row-id"), field, event.target.value);
});

editorModeTabs.forEach((button) => {
  button.addEventListener("click", () => {
    const nextMode = button.dataset.editorMode === "guided" ? "guided" : "paste";
    if (nextMode === activeEditorMode) return;
    syncEditors(activeEditorMode, nextMode);
    setEditorMode(nextMode);
    focusEditor();
  });
});

pledgeForm?.addEventListener("click", (event) => {
  const menuToggleButton = event.target.closest("button[data-goal-menu-toggle]");
  if (menuToggleButton) {
    event.preventDefault();
    if (activeEditorMode !== "guided") return;
    toggleGoalMenu();
    return;
  }

  const goalOptionButton = event.target.closest("button[data-goal-option]");
  if (goalOptionButton) {
    event.preventDefault();
    if (activeEditorMode !== "guided") return;
    const option = goalOptionButton.getAttribute("data-goal-option") || "";
    const label = resolveGoalOption(option);
    if (label) {
      setGuidedValidation(validateGuidedEditor(pledgeRawTextGuidedInput?.value || ""));
      insertGoalOption(label);
    }
    closeGoalMenu();
    return;
  }

  const insertButton = event.target.closest("button[data-insert-token]");
  if (!insertButton) return;
  if (activeEditorMode !== "guided") {
    setMessage(TEXT.guidedTabOnly, "info");
    return;
  }
  const token = insertButton.getAttribute("data-insert-token") || "";
  const mode = insertButton.getAttribute("data-insert-mode") || "cursor";
  insertIntoEditor(token, mode);
});

document.addEventListener("click", (event) => {
  if (!goalOptionMenuEl || goalOptionMenuEl.hidden) return;
  const target = event.target;
  if (!(target instanceof Element)) return;
  if (target.closest("#goalOptionMenu")) return;
  if (target.closest("button[data-goal-menu-toggle]")) return;
  closeGoalMenu();
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (!goalOptionMenuEl || goalOptionMenuEl.hidden) return;
  closeGoalMenu();
});

pledgeForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (savePledgeBtn) savePledgeBtn.disabled = true;
  try {
    const payload = buildParserPayload();
    const sourceRows = collectPledgeSourceRowsForSave();
    payload.sources = sourceRows;
    setLoading(true, TEXT.sourceSaving);

    await apiPost("/api/pledges", payload);

    setMessage(TEXT.sourceSaved, "success");
    resetParserForm();
  } catch (error) {
    setMessage(error.message || TEXT.sourceSaveFail, "error");
  } finally {
    if (savePledgeBtn) savePledgeBtn.disabled = false;
    setLoading(false);
  }
});

document.addEventListener("DOMContentLoaded", async () => {
  if (window.location.pathname !== "/pledge") return;
  setBlogDraftFromGoals([]);
  setEditorMode("paste");
  setLoading(true, TEXT.preparing);
  try {
    await refreshAllData();
    setMessage(TEXT.ready, "success");
  } catch (error) {
    setMessage(error.message || TEXT.initFail, "error");
  } finally {
    setLoading(false);
  }
});

