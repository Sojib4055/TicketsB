const statePill = document.getElementById("statePill");
const decisionTitle = document.getElementById("decisionTitle");
const updatedAt = document.getElementById("updatedAt");
const offersScanned = document.getElementById("offersScanned");
const validOffers = document.getElementById("validOffers");
const blockedOffers = document.getElementById("blockedOffers");
const bestFare = document.getElementById("bestFare");
const priceCap = document.getElementById("priceCap");
const targetLabel = document.getElementById("targetLabel");
const offersTable = document.getElementById("offersTable");
const decisionKind = document.getElementById("decisionKind");
const decisionMessage = document.getElementById("decisionMessage");
const statusLine = document.getElementById("statusLine");
const confidenceLine = document.getElementById("confidenceLine");
const handoffLine = document.getElementById("handoffLine");
const changesList = document.getElementById("changesList");
const screenshotBox = document.getElementById("screenshotBox");
const screenshotMeta = document.getElementById("screenshotMeta");
const screenshotLink = document.getElementById("screenshotLink");
const eventList = document.getElementById("eventList");
const targetRoute = document.getElementById("targetRoute");
const targetUrl = document.getElementById("targetUrl");
const beliefScore = document.getElementById("beliefScore");
const bestOfferCard = document.getElementById("bestOfferCard");
const signalChips = document.getElementById("signalChips");
const warningLine = document.getElementById("warningLine");
const policyList = document.getElementById("policyList");

async function loadState() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    const state = await response.json();
    render(state);
  } catch (error) {
    decisionTitle.textContent = "Dashboard waiting for monitor";
    statusLine.textContent = "UI server is running, state file not ready";
  }
}

function render(state) {
  const decision = state.decision || {};
  const summary = state.summary || {};
  const status = state.status || {};
  const target = state.target || {};

  decisionTitle.textContent = decision.message || decision.kind || "Monitoring";
  statePill.textContent = state.state || "UNKNOWN";
  statePill.className = `pill ${pillClass(decision.kind || state.state)}`;
  updatedAt.textContent = formatDate(state.updated_at);

  offersScanned.textContent = summary.offers_scanned ?? 0;
  validOffers.textContent = summary.valid_offers ?? 0;
  blockedOffers.textContent = summary.blocked_offers ?? 0;
  bestFare.textContent = fareSummary(summary);
  priceCap.textContent = summary.max_total_price == null
    ? "-"
    : `${summary.max_total_price} ${summary.currency || ""}`;

  targetLabel.textContent = target.label || target.route_or_event || target.url || "";
  decisionKind.textContent = decision.kind || "UNKNOWN";
  decisionMessage.textContent = decision.message || "";
  statusLine.textContent = `${status.state || "unknown"} (${(status.signals || []).join(", ") || "no signals"})`;
  confidenceLine.textContent = `${Math.round((status.confidence || 0) * 100)}%`;
  handoffLine.textContent = state.handoff ? state.handoff.reason || "Required" : "None";
  targetRoute.textContent = routeLabel(target);
  targetUrl.textContent = target.url || "-";
  beliefScore.textContent = target.belief_score == null ? "-" : `${Math.round(target.belief_score * 100)}%`;

  renderInsights(state);
  renderOffers(state.top_offers || []);
  renderPolicyDetails(state.top_offers || []);
  renderChanges(state.price_changes || []);
  renderScreenshot(state.screenshot_path);
  renderEvents(state.events || []);
}

function renderInsights(state) {
  const status = state.status || {};
  const items = state.top_offers || [];
  const best = items[0];

  signalChips.innerHTML = (status.signals || []).length
    ? status.signals.map((signal) => `<span class="chip">${escapeHtml(signal)}</span>`).join("")
    : `<span class="chip">no signals</span>`;

  warningLine.textContent = (status.warnings || []).length
    ? `Warnings: ${(status.warnings || []).join(", ")}`
    : "No parser warnings";

  if (!best) {
    bestOfferCard.textContent = "Waiting for ranked offers";
    return;
  }

  const offer = best.offer || {};
  const decision = best.decision || {};
  const time = [offer.departure_time, offer.arrival_time].filter(Boolean).join(" -> ") || "-";
  bestOfferCard.innerHTML = `
    <div class="bestOfferTitle">${escapeHtml(offer.title || "-")}</div>
    <p class="muted">${escapeHtml(offer.section || "-")}</p>
    <div class="bestOfferMeta">
      <div class="miniMetric"><span>Fare</span><strong>${offer.total_usd ?? "-"} ${escapeHtml(offer.currency || "")}</strong></div>
      <div class="miniMetric"><span>Seats</span><strong>${offer.available_seats ?? "-"}</strong></div>
      <div class="miniMetric"><span>Score</span><strong>${decision.score ?? 0}/100</strong></div>
    </div>
    <p class="muted">${escapeHtml(time)}${offer.duration ? ` · ${escapeHtml(offer.duration)}` : ""}</p>
  `;
}

function renderOffers(items) {
  if (!items.length) {
    offersTable.innerHTML = `<tr><td colspan="8" class="empty">Waiting for offers</td></tr>`;
    return;
  }

  offersTable.innerHTML = items.map((item, index) => {
    const offer = item.offer || {};
    const decision = item.decision || {};
    const allowed = decision.allowed;
    const policyClass = allowed ? "policyOk" : "policyBlocked";
    const policyText = allowed ? "Allowed" : "Blocked";
    const time = [offer.departure_time, offer.arrival_time].filter(Boolean).join(" -> ") || "-";
    return `
      <tr>
        <td>${index + 1}</td>
        <td><strong>${escapeHtml(offer.title || "-")}</strong><br><span class="muted">${escapeHtml(offer.service_class || "")}</span></td>
        <td>${escapeHtml(offer.section || "-")}<br><span class="muted">${escapeHtml(offer.duration || "")}</span></td>
        <td>${escapeHtml(time)}</td>
        <td>${offer.available_seats ?? "-"}</td>
        <td>${offer.total_usd ?? "-"} ${escapeHtml(offer.currency || "")}</td>
        <td class="score">${decision.score ?? 0}</td>
        <td><span class="${policyClass}">${policyText}</span><br><span class="muted">${escapeHtml(decision.reason || "")}</span></td>
      </tr>
    `;
  }).join("");
}

function renderPolicyDetails(items) {
  if (!items.length) {
    policyList.innerHTML = "<li>Waiting for policy evaluation</li>";
    return;
  }

  const decision = items[0].decision || {};
  const lines = [];
  lines.push(`<li><strong>${decision.allowed ? "Allowed" : "Blocked"}:</strong> ${escapeHtml(decision.reason || "")}</li>`);
  lines.push(`<li><strong>Rank reason:</strong> ${escapeHtml(decision.rank_reason || "-")}</li>`);
  lines.push(`<li><strong>Expiry risk:</strong> ${escapeHtml(decision.expiry_risk || "unknown")}</li>`);

  for (const block of decision.hard_blocks || []) {
    lines.push(`<li><strong>Hard block:</strong> ${escapeHtml(block)}</li>`);
  }
  for (const penalty of decision.soft_penalties || []) {
    lines.push(`<li><strong>Penalty:</strong> ${escapeHtml(penalty)}</li>`);
  }
  for (const match of decision.preference_matches || []) {
    lines.push(`<li><strong>Match:</strong> ${escapeHtml(match)}</li>`);
  }

  policyList.innerHTML = lines.join("");
}

function renderChanges(changes) {
  if (!changes.length) {
    changesList.innerHTML = "<li>No previous report comparison yet</li>";
    return;
  }
  changesList.innerHTML = changes.map((change) => `<li>${escapeHtml(change.message || "")}</li>`).join("");
}

function renderScreenshot(path) {
  if (!path) {
    screenshotBox.textContent = "No screenshot yet";
    screenshotMeta.textContent = "No screenshot captured yet";
    screenshotLink.className = "buttonLink disabled";
    screenshotLink.href = "#";
    return;
  }

  const fileUrl = `/file/${encodeURI(path)}`;
  screenshotLink.className = "buttonLink";
  screenshotLink.href = fileUrl;
  screenshotMeta.textContent = `Captured: ${path}`;
  screenshotBox.className = "screenshotBox";
  screenshotBox.innerHTML = "";

  const image = new Image();
  image.alt = "Latest monitoring screenshot";
  image.onload = () => {
    const dimensions = `${image.naturalWidth} x ${image.naturalHeight}`;
    if (image.naturalWidth < 600 || image.naturalHeight < 400) {
      screenshotBox.className = "screenshotBox isTiny";
      screenshotMeta.textContent = `${dimensions}. This old capture is too narrow; rerun the monitor to generate a sharper viewport screenshot.`;
    } else {
      screenshotMeta.textContent = `${dimensions}. Click Open Full Resolution for inspection.`;
    }
  };
  image.onerror = () => {
    screenshotBox.textContent = "Screenshot file could not be loaded";
    screenshotMeta.textContent = `Missing or unreadable: ${path}`;
  };
  image.src = fileUrl;
  screenshotBox.appendChild(image);
}

function renderEvents(events) {
  eventList.innerHTML = events.slice(-40).reverse().map((event) => {
    const text = [formatDate(event.ts), event.message].filter(Boolean).join(" - ");
    return `<li>${escapeHtml(text)}</li>`;
  }).join("");
}

function pillClass(value) {
  const text = String(value || "").toLowerCase();
  if (text.includes("allowed") || text.includes("payment") || text.includes("review")) return "review";
  if (text.includes("blocked") || text.includes("aborted") || text.includes("error")) return "blocked";
  if (text.includes("available") || text.includes("monitoring")) return "ok";
  return "";
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function fareSummary(summary) {
  if (summary.best_allowed_fare != null) {
    return `${summary.best_allowed_fare} ${summary.currency || ""}`;
  }
  if (summary.lowest_seen_fare != null) {
    return `Blocked: ${summary.lowest_seen_fare} ${summary.currency || ""}`;
  }
  return "-";
}

function routeLabel(target) {
  const url = target.url || "";
  try {
    const parsed = new URL(url);
    const from = parsed.searchParams.get("fromcity");
    const to = parsed.searchParams.get("tocity");
    const date = parsed.searchParams.get("doj");
    if (from && to) return `${from} -> ${to}${date ? ` · ${date}` : ""}`;
  } catch (error) {
    return target.route_or_event || target.label || "-";
  }
  return target.route_or_event || target.label || "-";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

loadState();
setInterval(loadState, 1000);
