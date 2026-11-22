(() => {
  "use strict";

  const payload = window.REVIEW_DATA;
  if (!payload?.manifest?.documents || !payload?.review) {
    document.body.innerHTML = '<p style="padding:24px">校对数据缺失，请重新生成校对稿。</p>';
    return;
  }

  const manifest = payload.manifest;
  const documents = manifest.documents;
  const documentMap = Object.fromEntries(documents.map(doc => [doc.id, doc]));
  const review = payload.review;
  const issues = Array.isArray(review.issues) ? review.issues : [];
  const kindLabels = {
    confirmed: "确定错误",
    suspected: "待人工复核",
    suggestion: "优化建议"
  };
  const scopeLabels = { all: "全部", body: "正文", answer: "答案", cross: "题答对照" };
  let activeKind = "all";
  let activeScope = "all";
  let activeIssueId = null;

  const title = review.document?.title || documents[0]?.source_name || "校对稿";
  const pageSummary = documents.map(doc => `${doc.label} ${doc.page_count} 页`).join(" · ");
  document.title = `${title} · 校对稿`;
  document.getElementById("document-title").textContent = `${title} · 校对稿`;
  document.getElementById("document-meta").textContent = `${pageSummary} · ${issues.length} 条批注`;
  document.getElementById("review-notice").textContent = payload.notice || "";

  function issueScope(issue) {
    const targetDocuments = new Set(issue.targets.map(target => target.document));
    if (targetDocuments.size > 1) return "cross";
    return issue.targets[0]?.document || "body";
  }

  function visibleIssues() {
    return issues.filter(issue => {
      const kindMatches = activeKind === "all" || issue.kind === activeKind;
      const scopeMatches = activeScope === "all" || issueScope(issue) === activeScope;
      return kindMatches && scopeMatches;
    });
  }

  function issueIsVisible(issue) {
    return visibleIssues().some(item => item.id === issue.id);
  }

  function makeScopeFilters() {
    const host = document.getElementById("scope-filters");
    const availableScopes = ["all", ...documents.map(doc => doc.id), "cross"];
    [...new Set(availableScopes)].forEach(scope => {
      if (scope !== "all" && scope !== "cross" && !documentMap[scope]) return;
      const count = scope === "all" ? issues.length : issues.filter(issue => issueScope(issue) === scope).length;
      const label = scopeLabels[scope] || documentMap[scope]?.label || scope;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "scope-chip";
      button.dataset.scope = scope;
      button.textContent = `${label} ${count}`;
      button.addEventListener("click", () => {
        activeScope = scope;
        refreshFilters();
      });
      host.appendChild(button);
    });
  }

  function makeKindFilters() {
    const host = document.getElementById("kind-filters");
    Object.entries(kindLabels).forEach(([kind, label]) => {
      const count = issues.filter(issue => issue.kind === kind).length;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `filter-chip ${kind}`;
      button.dataset.kind = kind;
      button.textContent = `${label} ${count}`;
      button.addEventListener("click", () => {
        activeKind = activeKind === kind ? "all" : kind;
        refreshFilters();
      });
      host.appendChild(button);
    });
  }

  function targetsOnPage(documentId, pageNumber) {
    const result = [];
    issues.forEach(issue => {
      issue.targets.forEach((target, targetIndex) => {
        if (target.document === documentId && target.page === pageNumber) {
          result.push({ issue, target, targetIndex });
        }
      });
    });
    return result;
  }

  function makePages() {
    const host = document.getElementById("pages");
    documents.forEach(doc => {
      doc.pages.forEach(page => {
        const pageTargets = targetsOnPage(doc.id, page.page);
        const section = document.createElement("article");
        section.className = "page-section";
        section.id = `${doc.id}-page-${page.page}`;
        section.dataset.document = doc.id;
        section.innerHTML = `
          <div class="page-heading">
            <strong>${escapeHtml(doc.label)} · 第 ${page.page} 页</strong>
            <span>${new Set(pageTargets.map(item => item.issue.id)).size} 条批注</span>
          </div>
          <div class="page-sheet">
            <img src="${page.image}" alt="${escapeHtml(doc.label)}第 ${page.page} 页原稿">
            <div class="annotation-layer"></div>
          </div>`;
        const layer = section.querySelector(".annotation-layer");
        pageTargets.filter(item => item.target.bbox).forEach(({ issue, target, targetIndex }) => {
          const box = document.createElement("button");
          box.type = "button";
          box.className = `annotation-box ${issue.kind}`;
          box.dataset.issueId = String(issue.id);
          box.dataset.targetIndex = String(targetIndex);
          box.title = issue.title;
          box.style.left = `${target.bbox.x * 100}%`;
          box.style.top = `${target.bbox.y * 100}%`;
          box.style.width = `${target.bbox.width * 100}%`;
          box.style.height = `${target.bbox.height * 100}%`;
          box.innerHTML = `<span class="annotation-badge">${issue.id}</span>`;
          box.addEventListener("click", event => {
            event.stopPropagation();
            activateIssue(issue.id, targetIndex, false);
          });
          layer.appendChild(box);
        });
        host.appendChild(section);
      });
    });
  }

  function makePageNav() {
    const host = document.getElementById("page-nav");
    documents.forEach(doc => {
      const group = document.createElement("div");
      group.className = "page-nav-group";
      group.innerHTML = `<span class="page-nav-label">${escapeHtml(doc.label)}</span>`;
      doc.pages.forEach(page => {
        const count = new Set(targetsOnPage(doc.id, page.page).map(item => item.issue.id)).size;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "page-link";
        button.innerHTML = `${page.page}${count ? `<span class="count">${count}</span>` : ""}`;
        button.addEventListener("click", () => {
          document.getElementById(`${doc.id}-page-${page.page}`)?.scrollIntoView({ block: "start" });
        });
        group.appendChild(button);
      });
      host.appendChild(group);
    });
  }

  function targetLabel(target) {
    const label = documentMap[target.document]?.label || target.document;
    return `${label} P${target.page}`;
  }

  function makeIssueCard(issue) {
    const card = document.createElement("article");
    card.className = `issue-card ${issue.kind}`;
    card.dataset.issueId = String(issue.id);
    card.tabIndex = 0;
    const allTargetLabels = issue.targets.map(targetLabel);
    const targetLabels = allTargetLabels.length > 2
      ? `${allTargetLabels.slice(0, 2).join(" ↔ ")} 等${allTargetLabels.length}处`
      : allTargetLabels.join(" ↔ ");
    const targetButtons = issue.targets.map((target, index) =>
      `<button type="button" class="target-link" data-target-index="${index}">${escapeHtml(targetLabel(target))}</button>`
    ).join("");
    card.innerHTML = `
      <div class="issue-title-row">
        <span class="issue-number">${issue.id}</span>
        <span class="issue-kind">${kindLabels[issue.kind]}</span>
        <span class="issue-category">${escapeHtml(issue.category)}</span>
        <span class="issue-page" title="${escapeHtml(allTargetLabels.join(" ↔ "))}">${escapeHtml(targetLabels)}</span>
      </div>
      <p class="issue-summary">${escapeHtml(issue.title)}</p>
      ${issue.questionId ? `<p class="issue-question">${escapeHtml(issue.questionId)}</p>` : ""}
      <div class="issue-targets">${targetButtons}</div>
      <div class="issue-detail">
        <div><strong>依据：</strong>${escapeHtml(issue.detail)}</div>
        <div><strong>建议：</strong>${escapeHtml(issue.suggestion)}</div>
      </div>`;
    card.addEventListener("click", event => {
      if (event.target.closest(".target-link")) return;
      activateIssue(issue.id, 0, true);
    });
    card.querySelectorAll(".target-link").forEach(button => {
      button.addEventListener("click", event => {
        event.stopPropagation();
        activateIssue(issue.id, Number(button.dataset.targetIndex), true);
      });
    });
    card.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") activateIssue(issue.id, 0, true);
    });
    return card;
  }

  function renderIssueList() {
    const host = document.getElementById("issue-list");
    host.replaceChildren(...visibleIssues().map(makeIssueCard));
    document.getElementById("visible-count").textContent = `(${visibleIssues().length})`;
    document.getElementById("empty-state").hidden = visibleIssues().length !== 0;
  }

  function refreshFilters() {
    document.querySelectorAll(".scope-chip").forEach(button => {
      button.classList.toggle("active", button.dataset.scope === activeScope);
    });
    document.querySelectorAll(".filter-chip").forEach(button => {
      button.classList.toggle("active", activeKind !== "all" && button.dataset.kind === activeKind);
    });
    document.querySelectorAll(".annotation-box").forEach(box => {
      const issue = issues.find(item => item.id === Number(box.dataset.issueId));
      box.classList.toggle("hidden-by-filter", !issue || !issueIsVisible(issue));
    });
    renderIssueList();
    if (activeIssueId !== null && visibleIssues().some(issue => issue.id === activeIssueId)) {
      activateIssue(activeIssueId, 0, false);
    }
  }

  function activateIssue(issueId, targetIndex, scrollPage) {
    if (document.body.classList.contains("answers-view")) setSidebarView("detail");
    activeIssueId = issueId;
    document.querySelectorAll("[data-issue-id]").forEach(element => {
      element.classList.toggle("active", Number(element.dataset.issueId) === issueId);
    });
    const issue = issues.find(item => item.id === issueId);
    const target = issue?.targets[targetIndex] || issue?.targets[0];
    if (!issue || !target) return;
    if (scrollPage) {
      const selector = `.annotation-box[data-issue-id="${issueId}"][data-target-index="${targetIndex}"]`;
      const destination = document.querySelector(selector) || document.getElementById(`${target.document}-page-${target.page}`);
      destination?.scrollIntoView({ block: "center" });
    }
    // Keep the selected card visible without scrolling the document back away
    // from the page or annotation that was just selected.
    const list = document.getElementById("issue-list");
    const card = list?.querySelector(`.issue-card[data-issue-id="${issueId}"]`);
    if (list && card) {
      const listRect = list.getBoundingClientRect();
      const cardRect = card.getBoundingClientRect();
      if (cardRect.top < listRect.top) list.scrollTop += cardRect.top - listRect.top;
      else if (cardRect.bottom > listRect.bottom) list.scrollTop += cardRect.bottom - listRect.bottom;
    }
  }

  function escapeHtml(value) {
    const node = document.createElement("span");
    node.textContent = String(value ?? "");
    return node.innerHTML;
  }

  document.querySelectorAll(".zoom-button").forEach(button => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".zoom-button").forEach(item => item.classList.remove("active"));
      button.classList.add("active");
      const zoom = button.dataset.zoom;
      document.documentElement.style.setProperty(
        "--page-width",
        zoom === "fit" ? "min(100%, 860px)" : `${860 * Number(zoom)}px`
      );
    });
  });

  function setSidebarView(view) {
    document.querySelectorAll("[data-view]").forEach(button => {
      const selected = button.dataset.view === view;
      button.classList.toggle("active", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    document.body.classList.toggle("detail-view", view === "detail");
    document.body.classList.toggle("answers-view", view === "answers");
  }
  document.querySelectorAll("[data-view]").forEach(button => {
    button.addEventListener("click", () => setSidebarView(button.dataset.view));
  });

  document.addEventListener("keydown", event => {
    if (!["j", "k", "J", "K"].includes(event.key)) return;
    const list = visibleIssues();
    if (!list.length) return;
    const current = list.findIndex(issue => issue.id === activeIssueId);
    const delta = event.key.toLowerCase() === "j" ? 1 : -1;
    const next = current < 0 ? 0 : (current + delta + list.length) % list.length;
    activateIssue(list[next].id, 0, true);
  });

  const topbar = document.querySelector(".topbar");
  if (topbar && typeof ResizeObserver !== "undefined") {
    new ResizeObserver(() => {
      document.documentElement.style.setProperty("--sidebar-top", `${topbar.getBoundingClientRect().height + 14}px`);
    }).observe(topbar);
  }

  makeScopeFilters();
  makeKindFilters();
  makePages();
  makePageNav();
  const coverage = payload.coverage;
  document.getElementById("coverage-text").textContent = coverage
    ? `逐题检查 ${coverage.processed}/${coverage.total} · 待人工 ${coverage.records.filter(r => r.manual_review).length} · 批注 ${issues.length} 条`
    : `共 ${manifest.page_count} 页 · 未提供逐题执行记录，检查覆盖未知`;
  const auditHost = document.getElementById("audit-results");
  if (auditHost && coverage) {
    const concise = document.createElement("details");
    concise.open = true;
    concise.className = "concise-answers";
    const conciseTitle = document.createElement("summary");
    conciseTitle.textContent = "正文精简答案";
    concise.appendChild(conciseTitle);
    const conciseScroll = document.createElement("div");
    conciseScroll.className = "concise-scroll";
    const conciseTable = document.createElement("table");
    (payload.concise_answers || []).forEach(row => {
      const tr = document.createElement("tr");
      const name = document.createElement("td");
      const jump = document.createElement("button");
      jump.type = "button";
      jump.className = "answer-jump";
      jump.textContent = row.id;
      jump.addEventListener("click", () => {
        const target = row.targets?.[0];
        if (!target) return;
        const page = document.getElementById(`${target.document}-page-${target.page}`);
        document.querySelectorAll(".answer-focus").forEach(node => node.remove());
        const sheet = page?.querySelector(".page-sheet");
        if (sheet && target.bbox) {
          const focus = document.createElement("div");
          focus.className = "answer-focus";
          const b = target.bbox;
          Object.assign(focus.style, { left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.width * 100}%`, height: `${b.height * 100}%` });
          sheet.appendChild(focus);
          focus.scrollIntoView({ block: "center" });
        } else page?.scrollIntoView({ block: "center" });
      });
      name.appendChild(jump);
      const value = document.createElement("td");
      value.textContent = (row.answer || []).map(a => `${a.value}${a.unit || ""}`).join("；") || "待求解";
      if (row.status !== "ready" || row.corrected) {
        const status = document.createElement("small");
        status.className = row.status === "ready" ? "answer-corrected" : "answer-pending";
        status.textContent = row.status === "missing" ? "未完成" : row.status === "pending" ? "待复核" : "已更正";
        value.appendChild(status);
      }
      tr.append(name, value); conciseTable.appendChild(tr);
    });
    if (!(payload.concise_answers || []).length) {
      const empty = document.createElement("p");
      empty.textContent = "尚无独立解答记录";
      conciseScroll.appendChild(empty);
    }
    conciseScroll.appendChild(conciseTable);
    concise.appendChild(conciseScroll); auditHost.appendChild(concise);
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "详细解题记录与逐题状态";
    details.appendChild(summary);
    const historyNote = document.createElement("p");
    historyNote.textContent = "以下保留初次独立解答；如有更正，以精简答案中的更正值为准。";
    details.appendChild(historyNote);
    const answers = Object.fromEntries((payload.independent_answers || []).map(r => [r.id, r]));
    const table = document.createElement("table");
    const head = document.createElement("tr");
    ["题号 / 状态", "独立答案及简要过程"].forEach(text => { const th = document.createElement("th"); th.textContent = text; head.appendChild(th); });
    table.appendChild(head);
    coverage.records.forEach(row => {
      const tr = document.createElement("tr");
      const name = document.createElement("td");
      name.textContent = `${row.id} · ${!row.complete ? "未完成" : row.manual_review ? "待人工" : "已检查"}`;
      name.title = JSON.stringify(row, null, 2);
      const answer = document.createElement("td");
      const a = answers[row.id];
      answer.textContent = a ? `${(a.answer || []).map(v => `${v.value}${v.unit || ""}`).join("；") || "无法可靠求解"}。${a.reasoning}` : "未完成独立解题";
      tr.append(name, answer); table.appendChild(tr);
    });
    details.appendChild(table); auditHost.appendChild(details);
  }
  refreshFilters();
})();
