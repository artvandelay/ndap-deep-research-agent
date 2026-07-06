(function () {
  "use strict";

  window.FC = window.FC || {};

  let lastClaims = [];
  let lastResults = [];

  function escapeHtml(v) {
    return String(v != null ? v : "").replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[c];
    });
  }

  function statusDot(status) {
    return '<span class="fc-dot fc-dot-' + escapeHtml(status) + '"></span>';
  }

  function renderParse(container, claims) {
    lastClaims = claims.slice();
    container.innerHTML = "";
    if (!claims.length) {
      container.innerHTML = '<p class="fc-muted">No checkable claims were extracted from this article.</p>';
      return;
    }
    const list = document.createElement("div");
    list.className = "fc-parse-list";
    for (const claim of claims) {
      const card = document.createElement("div");
      card.className = "fc-parse-card";
      card.setAttribute("data-claim", claim.id);
      card.innerHTML =
        '<div class="fc-parse-head">'
        + statusDot("pending")
        + '<strong>' + escapeHtml(claim.id) + '</strong>'
        + '<span class="fc-tag">' + escapeHtml(claim.type || "claim") + '</span>'
        + '</div>'
        + '<div class="fc-parse-quote">"' + escapeHtml(claim.quote) + '"</div>'
        + '<div class="fc-parse-meta">'
        + '<span><b>Metric:</b> ' + escapeHtml(claim.metric || "—") + '</span>'
        + '<span><b>Place:</b> ' + escapeHtml(claim.place || "—") + '</span>'
        + '<span><b>Year:</b> ' + escapeHtml(claim.year || "—") + '</span>'
        + '<span><b>Value:</b> ' + escapeHtml(claim.value || "—") + (claim.unit ? " " + escapeHtml(claim.unit) : "") + '</span>'
        + '</div>'
        + '<div class="fc-parse-statement">' + escapeHtml(claim.statement) + '</div>';
      list.appendChild(card);
    }
    container.appendChild(list);
  }

  function updateParseStatus(claimId, status) {
    const card = document.querySelector('.fc-parse-card[data-claim="' + claimId + '"]');
    if (!card) return;
    const dot = card.querySelector(".fc-dot");
    if (dot) dot.className = "fc-dot fc-dot-" + status;
  }

  function renderSummary(container, results) {
    const counts = { verified: 0, unverified: 0, contradicted: 0 };
    for (const r of results) counts[r.status] = (counts[r.status] || 0) + 1;
    container.innerHTML =
      '<div class="fc-summary">'
      + '<span class="fc-chip fc-verified">Verified <b>' + counts.verified + '</b></span>'
      + '<span class="fc-chip fc-unverified">Unverified <b>' + counts.unverified + '</b></span>'
      + '<span class="fc-chip fc-contradicted">Contradicted <b>' + counts.contradicted + '</b></span>'
      + '</div>'
      + '<p class="fc-legend">Green = NDAP supports the claim. Yellow = no NDAP data (not false). Red = NDAP disagrees.</p>';
  }

  function renderHighlights(container, articleText, claims, results) {
    lastResults = results.slice();
    const statusById = new Map();
    for (const r of results) statusById.set(r.claimId, r.status);

    for (const r of results) updateParseStatus(r.claimId, r.status);

    const spans = [];
    const unlocatable = [];
    for (const claim of claims) {
      const quote = claim.quote || "";
      if (!quote) continue;
      const start = articleText.indexOf(quote);
      if (start < 0) {
        unlocatable.push(claim);
        continue;
      }
      spans.push({
        start: start,
        end: start + quote.length,
        claimId: claim.id,
        status: statusById.get(claim.id) || "unverified",
        quote: quote,
      });
    }

    spans.sort(function (a, b) { return a.start - b.start; });
    const kept = [];
    let cursor = 0;
    for (const span of spans) {
      if (span.start < cursor) continue;
      kept.push(span);
      cursor = span.end;
    }

    let html = "";
    let pos = 0;
    for (const span of kept) {
      html += escapeHtml(articleText.slice(pos, span.start));
      html += '<mark class="fc fc-' + escapeHtml(span.status) + '" data-claim="' + escapeHtml(span.claimId) + '">'
        + escapeHtml(span.quote) + "</mark>";
      pos = span.end;
    }
    html += escapeHtml(articleText.slice(pos));

    container.innerHTML = "";
    const article = document.createElement("div");
    article.className = "fc-article";
    article.innerHTML = html;
    container.appendChild(article);

    if (unlocatable.length) {
      const note = document.createElement("div");
      note.className = "fc-unlocatable";
      note.innerHTML = "<strong>Could not locate in text:</strong> "
        + unlocatable.map(function (c) { return escapeHtml(c.id); }).join(", ");
      container.appendChild(note);
    }

    container.onclick = function (e) {
      const mark = e.target.closest("mark.fc[data-claim]");
      if (!mark) return;
      const claimId = mark.getAttribute("data-claim");
      const claim = claims.find(function (c) { return c.id === claimId; });
      const result = results.find(function (r) { return r.claimId === claimId; });
      if (claim && result) showEvidence(claim, result);
    };
  }

  function showEvidence(claim, result) {
    const panel = document.getElementById("evidence");
    if (!panel) return;
    panel.classList.remove("hidden");
    const dsLink = result.datasetUrl
      ? '<a href="' + escapeHtml(result.datasetUrl) + '" target="_blank" rel="noopener">Dataset ' + escapeHtml(result.datasetId) + "</a>"
      : "—";
    panel.innerHTML =
      '<h3>Evidence — ' + escapeHtml(claim.id) + '</h3>'
      + '<p class="fc-ev-status fc-ev-' + escapeHtml(result.status) + '"><strong>Status:</strong> ' + escapeHtml(result.status) + '</p>'
      + '<p><strong>Article claim:</strong> ' + escapeHtml(claim.value || claim.statement)
      + (claim.unit ? " " + escapeHtml(claim.unit) : "")
      + (claim.year ? " (" + escapeHtml(claim.year) + ")" : "") + "</p>"
      + '<p><strong>NDAP value:</strong> ' + escapeHtml(result.ndapValue || "—")
      + (result.unit ? " " + escapeHtml(result.unit) : "")
      + (result.year ? " (" + escapeHtml(result.year) + ")" : "") + "</p>"
      + "<p><strong>Dataset:</strong> " + dsLink + "</p>"
      + "<p><strong>Note:</strong> " + escapeHtml(result.note || "—") + "</p>"
      + (result.evidenceCsv
        ? "<pre class=\"fc-ev-csv\">" + escapeHtml(result.evidenceCsv) + "</pre>"
        : "");
  }

  FC.render = {
    renderParse: renderParse,
    renderHighlights: renderHighlights,
    renderSummary: renderSummary,
    showEvidence: showEvidence,
  };
})();
