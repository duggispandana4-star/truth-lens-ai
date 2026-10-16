const form = document.querySelector("#analysis-form");
const claimInput = document.querySelector("#claim-input");
const urlClaimInput = document.querySelector("#url-claim-input");
const articleUrlInput = document.querySelector("#article-url");
const analyzeButton = document.querySelector("#analyze-button");
const resultSection = document.querySelector("#results-section");
const resultCard = document.querySelector("#result-card");
const historyList = document.querySelector("#history-list");
const toast = document.querySelector("#toast");
let activeTab = "claim";
let toastTimer;

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function icon(name) {
  return `<i data-lucide="${name}" aria-hidden="true"></i>`;
}

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons();
}

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 3600);
}

function verdictIcon(verdict) {
  return {
    supported: "badge-check",
    contradicted: "circle-x",
    mixed: "scale",
    inconclusive: "circle-help",
  }[verdict] || "circle-help";
}

function renderResult(item, scroll = true) {
  const sourceHtml = item.sources.length
    ? item.sources.map(source => `
      <article class="source-item">
        <a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.title)}</a>
        <span class="source-meta">${esc(source.publisher)} · ${source.source_type === "news" ? "News article" : "Fact-check review"}</span>
        <div class="source-rating">${source.source_type === "news" ? "Search result: " : "Publisher rating: "}<b>${esc(source.rating)}</b>${source.review_date ? `<time>${esc(source.review_date)}</time>` : ""}</div>
      </article>`).join("")
    : `<div class="empty-evidence">${item.mode === "news_search"
      ? "No news articles matched this search. No fact-check verdict was made."
      : item.mode === "demo"
      ? "Demo mode: no external review search was performed, so there are no sources to cite."
      : "No published fact-check reviews were returned. This is not evidence for or against the claim."}</div>`;
  const keywordHtml = item.keywords?.length
    ? `<div class="result-keywords" aria-label="Keywords">${item.keywords.map(word => `<span class="keyword">${esc(word)}</span>`).join("")}</div>`
    : "";
  resultCard.innerHTML = `
    <div class="result-top">
      <div><div class="eyebrow">${item.mode === "news_search" ? "Free news search · not a fact-check" : item.mode === "demo" ? "Demo analysis · not verified" : "Published fact-check reviews"}</div><p class="result-claim">${esc(item.claim)}</p></div>
      <span class="verdict verdict-${esc(item.verdict)}">${icon(verdictIcon(item.verdict))}${esc(item.verdict_label)}</span>
    </div>
    <div class="result-content">
      <p class="result-summary">${esc(item.summary)}</p>
      <h3 class="evidence-title">${item.mode === "news_search" ? "Related news articles" : "Fact-check reviews and sources"}</h3>
      <div class="source-list">${sourceHtml}</div>
      ${keywordHtml}
      <div class="result-footnote">${item.mode === "news_search" ? "These are related news-search results, not fact-checks or independent evidence that the claim is true. Open each article and assess its reporting and context." : "Ratings belong to the named publishers. Read the linked review in full and consider its date and context."}</div>
    </div>`;
  resultSection.classList.remove("hidden");
  refreshIcons();
  if (scroll) resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error("The server returned an unreadable response. Please try again.");
  }
  if (!response.ok) {
    const detail = typeof data.detail === "string"
      ? data.detail
      : Array.isArray(data.detail)
        ? data.detail.map(issue => issue.msg).filter(Boolean).join(" ")
        : "The request could not be completed.";
    throw new Error(detail);
  }
  return data;
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

async function loadHistory() {
  try {
    const items = await requestJson("/api/history?limit=12");
    historyList.innerHTML = items.length ? items.map(item => `
      <article class="history-row">
        <button type="button" data-history-id="${item.id}" aria-label="View analysis: ${esc(item.claim)}">${esc(item.claim)}</button>
        <span class="history-date">${esc(formatDate(item.created_at))}</span>
        <span class="verdict verdict-${esc(item.verdict)}">${icon(verdictIcon(item.verdict))}${esc(item.verdict_label)}</span>
      </article>`).join("") : `
      <div class="empty-state"><span class="empty-icon">${icon("inbox")}</span><b>No checks yet</b><p>Your analyses will show up here on this device.</p></div>`;
    refreshIcons();
  } catch (error) {
    historyList.innerHTML = `<div class="empty-state"><b>History is unavailable</b><p>${esc(error.message)}</p></div>`;
  }
}

document.querySelectorAll(".input-tab").forEach(button => {
  button.addEventListener("click", () => {
    activeTab = button.id === "claim-tab" ? "claim" : "article";
    document.querySelector("#claim-tab").classList.toggle("active", activeTab === "claim");
    document.querySelector("#article-tab").classList.toggle("active", activeTab === "article");
    document.querySelector("#claim-tab").setAttribute("aria-selected", String(activeTab === "claim"));
    document.querySelector("#article-tab").setAttribute("aria-selected", String(activeTab === "article"));
    document.querySelector("#claim-panel").classList.toggle("hidden", activeTab !== "claim");
    document.querySelector("#article-panel").classList.toggle("hidden", activeTab !== "article");
  });
});

claimInput.addEventListener("input", () => {
  document.querySelector("#char-count").textContent = claimInput.value.length;
});

document.querySelectorAll(".example-chip").forEach(button => {
  button.addEventListener("click", () => {
    activeTab = "claim";
    document.querySelector("#claim-tab").click();
    claimInput.value = button.dataset.claim;
    document.querySelector("#char-count").textContent = claimInput.value.length;
    claimInput.focus();
  });
});

form.addEventListener("submit", async event => {
  event.preventDefault();
  const claim = activeTab === "article" ? urlClaimInput.value.trim() : claimInput.value.trim();
  const article_url = activeTab === "article" ? articleUrlInput.value.trim() : "";
  if (!claim && !article_url) {
    showToast("Enter a claim or provide an article URL.", true);
    (activeTab === "article" ? articleUrlInput : claimInput).focus();
    return;
  }
  if (claim.length > 6000) {
    showToast("Claims must be 6,000 characters or fewer.", true);
    return;
  }

  analyzeButton.disabled = true;
  analyzeButton.innerHTML = '<span class="loading-spinner" aria-hidden="true"></span> Checking...';
  try {
    const result = await requestJson("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ claim: claim || null, article_url: article_url || null }),
    });
    renderResult(result);
    await loadHistory();
    showToast(result.mode === "news_search" ? "Free news search complete — results are not fact-check verdicts." : "Published reviews retrieved and saved.");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    analyzeButton.disabled = false;
    analyzeButton.innerHTML = `Analyze claim ${icon("scan-search")}`;
    refreshIcons();
  }
});

historyList.addEventListener("click", async event => {
  const button = event.target.closest("[data-history-id]");
  if (!button) return;
  try {
    const item = await requestJson(`/api/history/${encodeURIComponent(button.dataset.historyId)}`);
    renderResult(item);
  } catch (error) {
    showToast(error.message, true);
  }
});

document.querySelector("#new-check").addEventListener("click", () => {
  resultSection.classList.add("hidden");
  document.querySelector("#analyzer").scrollIntoView({ behavior: "smooth" });
  (activeTab === "article" ? articleUrlInput : claimInput).focus({ preventScroll: true });
});
document.querySelector("#refresh-history").addEventListener("click", loadHistory);

const menuToggle = document.querySelector("#menu-toggle");
const mainNav = document.querySelector("#main-nav");
menuToggle.addEventListener("click", () => {
  const open = mainNav.classList.toggle("open");
  menuToggle.setAttribute("aria-expanded", String(open));
  menuToggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
});
mainNav.querySelectorAll("a").forEach(link => link.addEventListener("click", () => {
  mainNav.classList.remove("open");
  menuToggle.setAttribute("aria-expanded", "false");
}));

refreshIcons();
loadHistory();
