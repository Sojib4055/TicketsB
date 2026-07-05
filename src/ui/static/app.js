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
const tripForm = document.getElementById("tripForm");
const saveTripButton = document.getElementById("saveTripButton");
const tripScheduleLine = document.getElementById("tripScheduleLine");
const printReportButton = document.getElementById("printReportButton");
const ticketOutputLine = document.getElementById("ticketOutputLine");
const offerNotification = document.getElementById("offerNotification");
const offerNotificationBody = document.getElementById("offerNotificationBody");
const dismissOfferNotification = document.getElementById("dismissOfferNotification");
const OFFER_NOTIFICATION_DISMISS_KEY = "ticketBotDismissedOfferNotification";
let currentOfferNotificationKey = "";

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

async function loadTrip() {
  try {
    const response = await fetch("/api/trip", { cache: "no-store" });
    const payload = await response.json();
    if (payload.trip) fillTripForm(payload.trip);
    renderTripSchedule(payload.schedule);
  } catch (error) {
    tripScheduleLine.textContent = "Trip setup API is not ready yet.";
  }
}

async function saveTrip(event) {
  event.preventDefault();
  saveTripButton.disabled = true;
  saveTripButton.textContent = "Saving";
  try {
    const payload = tripFormPayload();
    const response = await fetch("/api/trip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!result.ok) throw new Error(result.error || "Unable to save trip");
    fillTripForm(result.trip);
    renderTripSchedule(result.schedule);
    decisionTitle.textContent = "Trip saved. Restart monitor if it is already running.";
  } catch (error) {
    tripScheduleLine.textContent = `Save failed: ${error.message}`;
  } finally {
    saveTripButton.disabled = false;
    saveTripButton.textContent = "Save Trip";
  }
}

async function openOfferInBrowser(rank) {
  if (!rank || Number.isNaN(rank)) return;
  decisionTitle.textContent = `Opening offer rank ${rank} in browser`;
  try {
    const response = await fetch("/api/offers/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rank }),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      throw new Error(result.error || result.message || "Unable to open offer");
    }
    decisionTitle.textContent = result.message || "Offer opened in browser";
    await loadState();
  } catch (error) {
    decisionTitle.textContent = `Offer action failed: ${error.message}`;
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
  renderTicketOutput(state);
  renderOfferNotification(state.offer_notification);
  if (state.trip) {
    fillTripForm(state.trip);
  }
  if (state.trip_schedule) {
    renderTripSchedule(state.trip_schedule);
  }
}

function renderOfferNotification(notification) {
  if (!offerNotification || !offerNotificationBody) return;
  if (!notification || !notification.best_offer) {
    offerNotification.classList.add("hidden");
    currentOfferNotificationKey = "";
    return;
  }

  const best = notification.best_offer || {};
  const nearby = notification.nearby_offers || [];
  const key = `${notification.title || ""}|${best.link_url || ""}|${best.fare || ""}`;
  currentOfferNotificationKey = key;
  if (sessionStorage.getItem(OFFER_NOTIFICATION_DISMISS_KEY) === key) {
    offerNotification.classList.add("hidden");
    return;
  }

  offerNotificationBody.innerHTML = `
    <div class="notificationBest">
      <div>
        <strong>${escapeHtml(best.operator || "-")}</strong>
        <p class="muted">${escapeHtml(best.route || "-")} · ${escapeHtml(best.departure_time || "time unknown")}${best.duration ? ` · ${escapeHtml(best.duration)}` : ""}</p>
      </div>
      <div class="notificationFare">${best.fare ?? "-"} ${escapeHtml(best.currency || "")}</div>
    </div>
    <p class="notificationMessage">${escapeHtml(notification.message || "")}</p>
    <div class="offerActionRow">${offerActionMarkup(best, best.open_action_label || "Open seat selection", "offerActionPrimary")}</div>
    ${best.direct_payment ? "" : `<p class="notificationNote">${escapeHtml(best.link_note || "")}</p>`}
    ${nearby.length ? `
      <div class="nearbyLinks">
        <h3>Nearest best-priced links</h3>
        ${nearby.map(renderNearbyNotificationOffer).join("")}
      </div>
    ` : ""}
  `;
  offerNotification.classList.remove("hidden");
}

function renderNearbyNotificationOffer(item) {
  return `
    <div class="nearbyLinkRow">
      <span>
        <strong>${escapeHtml(item.operator || "-")}</strong>
        <small>${escapeHtml(item.departure_time || "time unknown")} · ${item.fare ?? "-"} ${escapeHtml(item.currency || "")}</small>
      </span>
      ${offerActionMarkup(item, item.open_action_label || "Open seat selection", "offerActionSmall")}
    </div>
  `;
}

function renderTicketOutput(state) {
  if (state.ticket_path) {
    ticketOutputLine.innerHTML = `<a href="/file/${encodeURI(state.ticket_path)}" target="_blank" rel="noreferrer">Open downloaded ticket</a>`;
    return;
  }

  if (state.offer_action_result) {
    const result = state.offer_action_result;
    const screenshot = result.screenshot_path
      ? ` · <a href="/file/${encodeURI(result.screenshot_path)}" target="_blank" rel="noreferrer">open action screenshot</a>`
      : "";
    const currentUrl = result.current_url ? ` · <a href="${escapeHtml(safeUrl(result.current_url))}" target="_blank" rel="noreferrer">current provider page</a>` : "";
    ticketOutputLine.innerHTML = `Offer action: ${escapeHtml(result.message || result.error || "completed")}${currentUrl}${screenshot}`;
    return;
  }

  const bestItem = (state.top_offers || [])[0];
  if (bestItem?.offer) {
    ticketOutputLine.innerHTML = `Best offer action: ${offerActionForRank(bestItem.offer, 1, "Open seat selection", "offerActionSmall")}`;
    return;
  }

  ticketOutputLine.textContent = "Ticket PDF will appear here only after a confirmed booking is available.";
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
    <div class="offerActionBlock">${offerActionForRank(offer, 1, "Open seat selection", "offerActionPrimary")}</div>
  `;
}

function renderOffers(items) {
  if (!items.length) {
    offersTable.innerHTML = `<tr><td colspan="9" class="empty">Waiting for offers</td></tr>`;
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
        <td>${offerActionForRank(offer, index + 1, "Open seat selection", "offerActionSmall")}</td>
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

function tripFormPayload() {
  const data = new FormData(tripForm);
  return {
    from_city: String(data.get("from_city") || "").trim(),
    to_city: String(data.get("to_city") || "").trim(),
    journey_date: String(data.get("journey_date") || "").trim(),
    preferred_departure_start: String(data.get("preferred_departure_start") || "").trim(),
    preferred_departure_end: String(data.get("preferred_departure_end") || "").trim(),
    max_total_price: Number(data.get("max_total_price") || 2000),
    currency: "BDT",
    seat_count: Number(data.get("seat_count") || 1),
    preferred_operators: String(data.get("preferred_operators") || "").trim(),
    avoid_operators: String(data.get("avoid_operators") || "").trim(),
    avoid_night_buses: Boolean(data.get("avoid_night_buses")),
    auto_purchase_requested: Boolean(data.get("auto_purchase_requested")),
    monitor_days_before: Number(data.get("monitor_days_before") || 10),
    seat_preference: String(data.get("seat_preference") || "").trim(),
  };
}

function fillTripForm(trip) {
  if (!trip) return;
  setField("from_city", trip.from_city);
  setField("to_city", trip.to_city);
  setField("journey_date", trip.journey_date);
  setField("preferred_departure_start", trip.preferred_departure_start);
  setField("preferred_departure_end", trip.preferred_departure_end);
  setField("max_total_price", trip.max_total_price);
  setField("seat_count", trip.seat_count);
  setField("preferred_operators", (trip.preferred_operators || []).join(", "));
  setField("avoid_operators", (trip.avoid_operators || []).join(", "));
  setField("monitor_days_before", trip.monitor_days_before);
  setField("seat_preference", trip.seat_preference || "");
  setChecked("avoid_night_buses", trip.avoid_night_buses);
  setChecked("auto_purchase_requested", trip.auto_purchase_requested);
}

function renderTripSchedule(schedule) {
  if (!schedule) {
    tripScheduleLine.textContent = "Set route, date, time frame, and booking preferences.";
    return;
  }
  tripScheduleLine.textContent = `${schedule.message} Monitoring starts ${schedule.monitoring_start_date}; journey date ${schedule.journey_date}.`;
}

function setField(name, value) {
  const field = tripForm.elements.namedItem(name);
  if (field && value !== undefined && value !== null) field.value = value;
}

function setChecked(name, value) {
  const field = tripForm.elements.namedItem(name);
  if (field) field.checked = Boolean(value);
}

function offerActionMarkup(item, label, className = "offerActionSmall") {
  if (item.can_open_in_browser || item.booking_ref) {
    return offerOpenButton(item.rank || 1, label || item.open_action_label || "Open seat selection", className);
  }
  if (item.link_url) return offerLink(item.link_url, item.link_label || label || "Open", className);
  return `<span class="muted">No link</span>`;
}

function offerActionForRank(offer, rank, label, className = "offerActionSmall") {
  const linkUrl = offer.payment_url || offer.booking_url;
  if (offer.booking_ref || linkUrl) {
    return offerOpenButton(rank, label || "Open seat selection", className);
  }
  return `<span class="muted">No booking link found</span>`;
}

function offerOpenButton(rank, label, className = "offerActionSmall") {
  return `<button class="${className} offerOpenButton" type="button" data-offer-rank="${Number(rank) || 1}">${escapeHtml(label || "Open seat selection")}</button>`;
}

function offerLink(url, label, className = "offerActionSmall") {
  const safe = safeUrl(url);
  if (!safe) return `<span class="muted">No safe link</span>`;
  return `<a class="${className}" href="${escapeHtml(safe)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
}

function safeUrl(value) {
  if (!value) return "";
  try {
    const url = new URL(String(value), window.location.origin);
    if (url.protocol === "http:" || url.protocol === "https:") return url.href;
  } catch (error) {
    return "";
  }
  return "";
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
loadTrip();
setInterval(loadState, 1000);
tripForm.addEventListener("submit", saveTrip);
printReportButton.addEventListener("click", () => window.print());
if (dismissOfferNotification) {
  dismissOfferNotification.addEventListener("click", () => {
    if (currentOfferNotificationKey) {
      sessionStorage.setItem(OFFER_NOTIFICATION_DISMISS_KEY, currentOfferNotificationKey);
    }
    if (offerNotification) offerNotification.classList.add("hidden");
  });
}

document.addEventListener("click", (event) => {
  const button = event.target.closest(".offerOpenButton");
  if (!button) return;
  const rank = Number(button.dataset.offerRank || 1);
  openOfferInBrowser(rank);
});
