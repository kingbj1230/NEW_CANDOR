(function attachPoliticianDetailTreeUtils(globalScope) {
  const scope = globalScope || window;

  function clampLevel(level) {
    const numeric = Number(level);
    if (!Number.isFinite(numeric)) return 1;
    return Math.max(1, Math.min(6, Math.floor(numeric)));
  }

  function readNodeText(node) {
    const candidates = [node?.text, node?.content, node?.title, node?.detail, node?.name];
    for (const candidate of candidates) {
      const text = String(candidate || "").trim();
      if (text) return text;
    }
    return "";
  }

  function readNodeChildren(node) {
    const children = [];
    if (Array.isArray(node?.children) && node.children.length) {
      children.push(...node.children);
    } else if (Array.isArray(node?.promises) && node.promises.length) {
      children.push(...node.promises);
    } else if (Array.isArray(node?.items) && node.items.length) {
      children.push(...node.items);
    }
    return children;
  }

  function countTreeNodes(nodes) {
    if (!Array.isArray(nodes) || !nodes.length) return 0;
    let count = 0;
    const stack = [...nodes];
    while (stack.length) {
      const node = stack.pop();
      if (!node || typeof node !== "object") continue;
      count += 1;
      const children = readNodeChildren(node);
      if (children.length) stack.push(...children);
    }
    return count;
  }

  function isExecutionMethodGoal(goalText) {
    const normalized = String(goalText || "").replace(/\s+/g, "").toLowerCase();
    return normalized.includes("이행방법") || normalized.includes("시행방법") || normalized.includes("executionmethod");
  }

  function collectLeafDescendants(node) {
    const children = readNodeChildren(node);
    if (!children.length) return [node];
    const leaves = [];
    children.forEach((child) => {
      leaves.push(...collectLeafDescendants(child));
    });
    return leaves;
  }

  function collectExecutionProgressTargetIds(goals) {
    const targetIds = new Set();
    (goals || []).forEach((goal) => {
      const goalTitle = readNodeText(goal);
      if (!isExecutionMethodGoal(goalTitle)) return;
      const promiseNodes = readNodeChildren(goal);
      promiseNodes.forEach((promiseNode) => {
        const leafNodes = collectLeafDescendants(promiseNode);
        leafNodes.forEach((leafNode) => {
          const nodeId = leafNode?.id;
          if (nodeId !== undefined && nodeId !== null && String(nodeId).trim()) {
            targetIds.add(String(nodeId));
          }
        });
      });
    });
    return targetIds;
  }

  function renderTreeNode(node, context, siblingIndex, level, pathParts) {
    const displayLevel = clampLevel(level);
    const nodeText = readNodeText(node) || `레벨 ${displayLevel} 항목`;
    const marker = displayLevel <= 2 ? "·" : "-";
    const nextPathParts = [...pathParts, nodeText];
    const nodePath = nextPathParts.join(" > ");
    const children = readNodeChildren(node);
    const hasChildren = children.length > 0;
    const nodeId = node?.id !== undefined && node?.id !== null ? String(node.id) : "";
    const scoreBadge = context.showScoreBadge && nodeId && context.scoreTargetIds.has(nodeId)
      ? context.renderScoreBadge(node, { nodePath })
      : "";

    const childMarkup = hasChildren
      ? `<div class="level-children">${children
          .map((childNode, childIndex) => renderTreeNode(childNode, context, childIndex + 1, displayLevel + 1, nextPathParts))
          .join("")}</div>`
      : "";

    return `
      <article class="level-node level-${displayLevel}${hasChildren ? " has-children" : " is-leaf"}">
        <p class="level-line">
          <span class="node-number">${context.escapeHtml(marker)}</span>
          <span class="level-text">${context.escapeHtml(nodeText)}</span>
          ${scoreBadge}
        </p>
        ${childMarkup}
      </article>
    `;
  }

  function renderGoalSection(goal, context) {
    const goalText = readNodeText(goal) || "세부 항목";
    const children = readNodeChildren(goal);
    return `
      <section class="top-goal-accordion is-static">
        <h4 class="top-goal-summary">
          <span class="level-text">${context.escapeHtml(goalText)}</span>
        </h4>
        <div class="top-goal-body">
          ${children.length
            ? `<div class="level-children">${children
                .map((childNode, childIndex) => renderTreeNode(childNode, context, childIndex + 1, 2, [goalText]))
                .join("")}</div>`
            : '<p class="empty">하위 항목이 없습니다.</p>'}
        </div>
      </section>
    `;
  }

  function renderPledgeTreeMarkup(pledge, options = {}) {
    const goals = Array.isArray(pledge?.goals) ? pledge.goals : [];
    const escapeHtml = typeof options.escapeHtmlFn === "function" ? options.escapeHtmlFn : (value) => String(value ?? "");
    if (!goals.length) {
      const fallback = String(pledge?.raw_text || "").trim();
      return fallback
        ? `<p class="promise-summary">${escapeHtml(fallback)}</p>`
        : '<p class="empty">세부 공약이 등록되지 않았습니다.</p>';
    }
    const context = {
      escapeHtml,
      renderScoreBadge: typeof options.renderScoreBadgeFn === "function" ? options.renderScoreBadgeFn : () => "",
      scoreTargetIds: collectExecutionProgressTargetIds(goals),
      showScoreBadge: Boolean(options.showScoreBadge),
    };
    return `
      <div class="pledge-tree">
        ${goals.map((goal) => renderGoalSection(goal, context)).join("")}
      </div>
    `;
  }

  function bindGoalAccordions(_rootElement) {
    // Static section layout: no accordion behavior required.
  }

  scope.PoliticianDetailTreeUtils = {
    clampLevel,
    readNodeText,
    readNodeChildren,
    countTreeNodes,
    isExecutionMethodGoal,
    collectExecutionProgressTargetIds,
    renderPledgeTreeMarkup,
    bindGoalAccordions,
  };
})(window);
