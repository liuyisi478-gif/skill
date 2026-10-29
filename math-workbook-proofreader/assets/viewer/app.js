(() => {
  "use strict";

  const payload = window.REVIEW_DATA;
  if (!payload || !payload.manifest || !payload.review) {
    document.body.innerHTML = '<p style="padding:24px">校对数据缺失，请重新生成校对稿。</p>';
    return;
  }

  const manifest = payload.manifest;
  const review = payload.review;
  const issues = Array.isArray(review.issues) ? review.issues : [];
  const labels = {
    confirmed: "确定错误",
    suspected: "疑似问题",
    suggestion: "优化建议"
  };
  let activeFilter = "all";
  let activeIssueId = null;

  const title = review.document?.title || manifest.source_name || "校对稿";
  document.title = `${title} · 校对稿`;
  document.getElementById("document-title").textContent = `${title} · 校对稿`;
  document.getElementById("document-meta").textContent = `共 ${manifest.page_count} 页 · ${issues.length} 条批注`;
  document.getElementById("review-notice").textContent = payload.notice || "";

  const counts = Object.fromEntries(
    Object.keys(labels).map(kind => [kind, issues.filter(issue => issue.kind === kind).length])
  );

  function visibleIssues() {
    return activeFilter === "all" ? issues : issues.filter(issue => issue.kind === activeFilter);
  }

  function makeFilters() {
    const host = document.getElementById("kind-filters");
    Object.entries(labels).forEach(([kind, label]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `filter-chip ${kind}`;
      button.dataset.kind = kind;
      button.textContent = `${label} ${counts[kind]}`;
      button.addEventListener("click", () => {
        activeFilter = activeFilter === kind ? "all" : kind;
        refreshFilter();
      });
      host.appendChild(button);
    });
  }

  function makePages() {
    const host = document.getElementById("pages");
    manifest.pages.forEach(page => {
      const pageIssues = issues.filter(issue => issue.page === page.page);
      const section = document.createElement("article");
      section.className = "page-section";
      section.id = `page-${page.page}`;
      section.innerHTML = `
        <div class="page-heading">
          <strong>第 ${page.page} 页</strong>
          <span>${pageIssues.length} 条批注</span>
        </div>
        <div class="page-sheet">
          <img src="${page.image}" alt="第 ${page.page} 页原稿">
          <div class="annotation-layer"></div>
        </div>`;
      const layer = section.querySelector(".annotation-layer");
      pageIssues.filter(issue => issue.bbox).forEach(issue => {
        const box = document.createElement("button");
        box.type = "button";
        box.className = `annotation-box ${issue.kind}`;
        box.dataset.issueId = String(issue.id);
        box.title = issue.title;
        box.style.left = `${issue.bbox.x * 100}%`;
        box.style.top = `${issue.bbox.y * 100}%`;
        box.style.width = `${issue.bbox.width * 100}%`;
        box.style.height = `${issue.bbox.height * 100}%`;
        box.innerHTML = `<span class="annotation-badge">${issue.id}</span>`;
        box.addEventListener("click", event => {
          event.stopPropagation();
          activateIssue(issue.id, false);
        });
        layer.appendChild(box);
      });
      host.appendChild(section);
    });
  }

  function makePageNav() {
    const host = document.getElementById("page-nav");
    manifest.pages.forEach(page => {
      const count = issues.filter(issue => issue.page === page.page).length;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "page-link";
      button.innerHTML = `${page.page}${count ? `<span class="count">${count}</span>` : ""}`;
      button.addEventListener("click", () => {
        document.getElementById(`page-${page.page}`)?.scrollIntoView({ block: "start" });
      });
      host.appendChild(button);
    });
  }

  function makeIssueCard(issue) {
    const card = document.createElement("article");
    card.className = `issue-card ${issue.kind}`;
    card.dataset.issueId = String(issue.id);
    card.tabIndex = 0;
    card.innerHTML = `
      <div class="issue-title-row">
        <span class="issue-number">${issue.id}</span>
        <span class="issue-kind">${labels[issue.kind]}</span>
        <span class="issue-category">${escapeHtml(issue.category)}</span>
        <span class="issue-page">P${issue.page}</span>
      </div>
      <p class="issue-summary">${escapeHtml(issue.title)}</p>
      <div class="issue-detail">
        <div><strong>依据：</strong>${escapeHtml(issue.detail)}</div>
        <div><strong>建议：</strong>${escapeHtml(issue.suggestion)}</div>
      </div>`;
    card.addEventListener("click", () => activateIssue(issue.id, true));
    card.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") activateIssue(issue.id, true);
    });
    return card;
  }

  function renderIssueList() {
    const host = document.getElementById("issue-list");
    host.replaceChildren(...visibleIssues().map(makeIssueCard));
    document.getElementById("visible-count").textContent = `(${visibleIssues().length})`;
    document.getElementById("empty-state").hidden = visibleIssues().length !== 0;
    if (activeIssueId !== null) activateIssue(activeIssueId, false);
  }

  function refreshFilter() {
    document.querySelectorAll(".filter-chip").forEach(button => {
      button.classList.toggle("active", activeFilter !== "all" && button.dataset.kind === activeFilter);
    });
    document.querySelectorAll(".annotation-box").forEach(box => {
      const issue = issues.find(item => item.id === Number(box.dataset.issueId));
      box.classList.toggle("hidden-by-filter", activeFilter !== "all" && issue?.kind !== activeFilter);
    });
    renderIssueList();
  }

  function activateIssue(issueId, scrollPage) {
    activeIssueId = issueId;
    document.querySelectorAll("[data-issue-id]").forEach(element => {
      element.classList.toggle("active", Number(element.dataset.issueId) === issueId);
    });
    const issue = issues.find(item => item.id === issueId);
    if (!issue) return;
    if (scrollPage) {
      const target = document.querySelector(`.annotation-box[data-issue-id="${issueId}"]`) || document.getElementById(`page-${issue.page}`);
      target?.scrollIntoView({ block: "center" });
    }
    const card = document.querySelector(`.issue-card[data-issue-id="${issueId}"]`);
    card?.scrollIntoView({ block: "nearest" });
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

  document.querySelectorAll("[data-view]").forEach(button => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-view]").forEach(item => item.classList.remove("active"));
      button.classList.add("active");
      document.body.classList.toggle("detail-view", button.dataset.view === "detail");
    });
  });

  document.addEventListener("keydown", event => {
    if (!(["j", "k", "J", "K"].includes(event.key))) return;
    const list = visibleIssues();
    if (!list.length) return;
    const current = list.findIndex(issue => issue.id === activeIssueId);
    const delta = event.key.toLowerCase() === "j" ? 1 : -1;
    const next = current < 0 ? 0 : (current + delta + list.length) % list.length;
    activateIssue(list[next].id, true);
  });

  makeFilters();
  makePages();
  makePageNav();
  document.getElementById("coverage-text").textContent = `检查覆盖 ${manifest.page_count}/${manifest.page_count} 页 · 批注 ${issues.length} 条`;
  refreshFilter();
})();
