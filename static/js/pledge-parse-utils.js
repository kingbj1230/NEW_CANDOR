(function attachPledgeParseUtils(globalScope) {
  const scope = globalScope || window;

  const TYPE1_MARKER_RE = /[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]/;
  const SECTION_LABELS = {
    goal: ["목표", "비전", "핵심 목표", "핵심목표", "추진 목표", "추진목표"],
    method: ["이행방법", "이행 방법", "이행방안", "실천방안", "추진전략", "추진 전략", "세부실천", "세부 실행"],
    timeline: ["이행기간", "이행 기간", "추진일정", "추진 일정"],
    finance: [
      "재원조달방안 등",
      "재원 조달 방안 등",
      "재원조달방안",
      "재원 조달 방안",
      "재원조달",
      "재원 대책",
      "재원대책",
      "재정상태",
      "재정 상태",
    ],
  };

  function cleanText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function collapseSpaces(text) {
    return String(text || "").replace(/\s+/g, "").trim();
  }

  function leadingSpaces(text) {
    const m = String(text || "").match(/^\s*/);
    return m ? m[0].length : 0;
  }

  function startsWithCircledNumber(line) {
    return /^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]/.test(String(line || "").trim());
  }

  function detectMarker(line) {
    const trimmed = String(line || "").trim();
    if (!trimmed) return "plain";
    if (/^[□○◯]\s+/.test(trimmed)) return "circle";
    if (startsWithCircledNumber(trimmed)) return "circled";
    if (/^\d+[.)]\s+/.test(trimmed)) return "number";
    if (/^[-·•▪◦*]\s+/.test(trimmed)) return "bullet";
    return "plain";
  }

  function stripMarker(line) {
    let text = String(line || "").trim();
    text = text.replace(/^[□○◯]\s+/, "");
    text = text.replace(/^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]\s*/, "");
    text = text.replace(/^\d+[.)]\s+/, "");
    text = text.replace(/^[-·•▪◦*]\s+/, "");
    return cleanText(text);
  }

  function normalizeSectionHeader(line) {
    const compact = collapseSpaces(line)
      .replace(/^\uFEFF+/, "")
      .replace(/^[□○◯]+/, "")
      .replace(/[\[\]():：\-]/g, "");
    return compact;
  }

  function detectSection(line) {
    const compact = normalizeSectionHeader(line);
    if (!compact) return null;

    const matchLabel = (labels) => labels.some((label) => compact === collapseSpaces(label) || compact.startsWith(collapseSpaces(label)));

    if (matchLabel(SECTION_LABELS.goal)) return "goal";
    if (matchLabel(SECTION_LABELS.method)) return "method";
    if (matchLabel(SECTION_LABELS.timeline)) return "timeline";
    if (matchLabel(SECTION_LABELS.finance)) return "finance";
    return null;
  }

  function detectParseType(text) {
    const body = String(text || "");
    if (TYPE1_MARKER_RE.test(body)) return "type1";
    if (/(^|\n)\s*[□○◯]/m.test(body)) return "type2";
    return "type3";
  }

  function createParseResult(type) {
    return {
      parse_type: type,
      goals: [],
      strategies: [],
      timeline: [],
      finance: [],
      warnings: [],
    };
  }

  function pushMetaLine(bucket, line) {
    const cleaned = stripMarker(line);
    if (cleaned) bucket.push(cleaned);
  }

  function parsePledgeText(text) {
    const raw = String(text || "").replace(/\r\n/g, "\n");
    const lines = raw.split("\n");
    const parseType = detectParseType(raw);
    const result = createParseResult(parseType);

    let currentSection = null;
    let currentStrategy = null;
    let currentStrategyIndent = 0;

    lines.forEach((rawLine) => {
      const trimmed = String(rawLine || "").trim();
      if (!trimmed) return;

      const section = detectSection(trimmed);
      if (section) {
        currentSection = section;
        if (section !== "method") {
          currentStrategy = null;
          currentStrategyIndent = 0;
        }
        return;
      }

      if (!currentSection) {
        currentSection = "method";
      }

      if (currentSection === "goal") {
        const goalText = stripMarker(trimmed);
        if (goalText) result.goals.push(goalText);
        return;
      }

      if (currentSection === "timeline") {
        pushMetaLine(result.timeline, trimmed);
        return;
      }

      if (currentSection === "finance") {
        pushMetaLine(result.finance, trimmed);
        return;
      }

      const indent = leadingSpaces(rawLine);
      const marker = detectMarker(trimmed);
      const content = stripMarker(trimmed);
      if (!content) return;

      const isStrategyByMarker = marker === "circle" || marker === "circled" || marker === "number";
      const isActionByMarker = marker === "bullet";

      if (!currentStrategy) {
        currentStrategy = { title: content, actions: [] };
        currentStrategyIndent = indent;
        result.strategies.push(currentStrategy);
        return;
      }

      if (isStrategyByMarker) {
        currentStrategy = { title: content, actions: [] };
        currentStrategyIndent = indent;
        result.strategies.push(currentStrategy);
        return;
      }

      if (isActionByMarker || indent > currentStrategyIndent) {
        currentStrategy.actions.push(content);
        return;
      }

      if (parseType === "type3") {
        currentStrategy = { title: content, actions: [] };
        currentStrategyIndent = indent;
        result.strategies.push(currentStrategy);
        return;
      }

      currentStrategy.actions.push(content);
    });

    if (!result.goals.length) {
      result.warnings.push("목표 섹션이 비어 있습니다.");
    }
    if (!result.strategies.length) {
      result.warnings.push("이행 방법(strategy) 섹션이 비어 있습니다.");
    }

    return result;
  }

  function toTreeGoals(parsedResult) {
    const parsed = parsedResult || createParseResult("type3");
    const goals = [];

    if ((parsed.goals || []).length) {
      goals.push({
        title: "목표",
        promises: parsed.goals.map((goalLine) => ({ title: goalLine, items: [] })),
      });
    }

    if ((parsed.strategies || []).length) {
      goals.push({
        title: "이행 방법",
        promises: (parsed.strategies || []).map((strategy) => ({
          title: cleanText(strategy?.title || ""),
          items: (strategy?.actions || []).map((action) => ({ detail: cleanText(action || "") })),
        })),
      });
    }

    return goals
      .map((goal) => ({
        title: cleanText(goal.title),
        promises: (goal.promises || [])
          .map((promise) => ({
            title: cleanText(promise.title),
            items: (promise.items || [])
              .map((item) => ({ detail: cleanText(item.detail) }))
              .filter((item) => item.detail),
          }))
          .filter((promise) => promise.title),
      }))
      .filter((goal) => goal.title);
  }

  function parseEditorText(text) {
    const parsed = parsePledgeText(text);
    return toTreeGoals(parsed);
  }

  function serializeTree(goals, options = {}) {
    const indentUnit = String(options.indentUnit || "  ");
    const lines = [];

    (goals || []).forEach((goal) => {
      const goalTitle = cleanText(goal?.title);
      if (!goalTitle) return;
      lines.push(goalTitle);

      (goal.promises || []).forEach((promise) => {
        const promiseTitle = cleanText(promise?.title);
        if (!promiseTitle) return;
        lines.push(`${indentUnit}${promiseTitle}`);

        (promise.items || []).forEach((item) => {
          const detail = cleanText(item?.detail);
          if (!detail) return;
          lines.push(`${indentUnit}${indentUnit}${detail}`);
        });
      });
    });

    return lines.join("\n");
  }

  function getParsedModel(text) {
    const parsed = parsePledgeText(text);
    const goals = toTreeGoals(parsed);
    const normalizedText = serializeTree(goals).trim();

    return {
      parsed,
      goals,
      normalizedText,
      parse_type: parsed.parse_type,
      timeline_text: (parsed.timeline || []).join("\n").trim(),
      finance_text: (parsed.finance || []).join("\n").trim(),
      structure_version: 2,
    };
  }

  scope.PledgeParseUtils = {
    cleanText,
    collapseSpaces,
    leadingSpaces,
    detectMarker,
    stripMarker,
    detectSection,
    detectParseType,
    parsePledgeText,
    parseEditorText,
    serializeTree,
    toTreeGoals,
    getParsedModel,
  };
})(window);
