const $ = (id) => document.getElementById(id);
const state = { user: null, config: null, jobs: [], alerts: [], filter: 'all', view: 'search', step: 0, register: false, selected: null, provider: null, busy: false, refreshing: false };
const labels = { SCHEDULED: ['Watching · scheduled', 'blue'], MONITORING: ['Watching for seats', 'green'], PREPARING: ['Preparing your booking', 'amber'], AWAITING_PAYMENT: ['Payment required', 'amber'], NEEDS_ATTENTION: ['Needs your attention', 'red'], PAUSED: ['Paused', 'gray'], CONFIRMED: ['Confirmed', 'green'], CANCELLED: ['Closed', 'gray'], EXPIRED: ['Window ended', 'gray'] };
const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const money = (value) => new Intl.NumberFormat('en-BD', { maximumFractionDigits: 2 }).format(Number(value || 0));
const date = (value, options = {}) => value ? new Date(typeof value === 'number' ? value * 1000 : value).toLocaleString('en-GB', { timeZone: 'Asia/Dhaka', day: 'numeric', month: 'short', ...options }) : '—';
const when = (value) => date(value, { hour: '2-digit', minute: '2-digit' });
const localInput = (value) => new Date(value.getTime() + 6 * 3600000).toISOString().slice(0, 16);
function badge(job) { const [label, color] = labels[job.status] || [job.status, 'gray']; return `<span class="badge ${color}">${escape(job.mode === 'demo' && job.status === 'CONFIRMED' ? 'Demo completed' : label)}</span>`; }

async function api(path, body) {
  const response = await fetch(path, { credentials: 'same-origin', cache: 'no-store', ...(body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Ticket-Request': '1' }, body: JSON.stringify(body) }) });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401) { state.user = null; renderAccount(); }
    throw new Error(data.error || 'The request could not be completed.');
  }
  return data;
}

let toastTimer;
function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, 5500); }
function showView(view) {
  state.view = view;
  for (const item of ['search', 'bookings', 'alerts', 'setup']) $(`${item}View`).hidden = item !== view;
  document.querySelectorAll('[data-view]').forEach((button) => button.classList.toggle('active', button.dataset.view === view));
  $('pageName').textContent = { search: 'Search buses', bookings: 'My bookings', alerts: 'WhatsApp alerts', setup: 'Connections' }[view];
}
function renderAccount() { $('accountButton').textContent = state.user ? `${state.user.name} · Sign out` : 'Sign in ↗'; }
function renderConfig() {
  const config = state.config;
  $('modeBadge').textContent = config.mode === 'demo' ? '◌ Demo mode' : '● Live mode';
  $('modeBadge').className = `badge ${config.mode === 'demo' ? 'amber' : 'green'}`;
  $('modeNotice').hidden = false;
  $('modeNotice').textContent = config.mode === 'demo' ? 'Bus searches use live Shohoz availability. Automatic reservations are in demo mode; you can browse and watch real departures without placing a booking.' : (config.whatsapp_configured ? 'Live Shohoz bookings · Payment is always completed by you. Monitor your request for provider verification steps.' : 'Live booking mode · WhatsApp is not connected. Follow booking updates here until the operator connects messaging.');
  $('confirmedNote').textContent = config.mode === 'demo' ? 'simulated journeys' : 'provider confirmed';
  $('whatsappFormNote').textContent = config.mode === 'demo' ? 'In demo mode, messages appear as previews in your alerts. No WhatsApp messages are sent.' : (config.whatsapp_configured ? 'We’ll send booking updates using the connected WhatsApp Business account.' : 'WhatsApp is not connected yet. Alerts will appear here with “Setup required” until it is configured.');
  $('connections').innerHTML = `<article class="connection-card"><span class="badge ${config.mode === 'demo' ? 'amber' : 'green'}">${config.mode === 'demo' ? 'Demo active' : 'Live enabled'}</span><h3>Shohoz bus tickets</h3><p>${config.mode === 'demo' ? 'Explore the complete journey with simulated seats and payment. Live reservations still need provider validation.' : 'Each booking uses a separate browser session. Changed layouts and verification steps are passed to you.'}</p><ol><li>Install the browser on the website server.</li><li>Validate seat selection and the passenger flow with Shohoz.</li><li>The operator enables live booking in the server settings.</li></ol></article><article class="connection-card"><span class="badge ${config.whatsapp_configured ? 'green' : 'amber'}">${config.whatsapp_configured ? 'Configured' : 'Setup required'}</span><h3>WhatsApp Business</h3><p>Receive alerts when matching seats run low, payment is ready, or a payment deadline is approaching.</p><ol><li>Create a Meta WhatsApp Business account and register a sending number.</li><li>Get the booking-update message template approved.</li><li>Configure credentials and the signed delivery webhook on the server.</li></ol><p>“Accepted” means the provider accepted a message. “Delivered” and “Read” come from delivery receipts.</p></article>`;
}

function renderJobs() {
  const jobs = state.jobs;
  $('navCount').textContent = jobs.length;
  $('journeyCount').textContent = jobs.length;
  $('watchingMetric').textContent = jobs.filter(j => ['SCHEDULED', 'MONITORING', 'PREPARING'].includes(j.status)).length;
  $('paymentMetric').textContent = jobs.filter(j => j.status === 'AWAITING_PAYMENT').length;
  $('confirmedMetric').textContent = jobs.filter(j => j.status === 'CONFIRMED').length;
  const filtered = jobs.filter(j => state.filter === 'all' || (state.filter === 'active' ? !['CONFIRMED', 'CANCELLED', 'EXPIRED'].includes(j.status) : ['CONFIRMED', 'CANCELLED', 'EXPIRED'].includes(j.status)));
  if (!filtered.length) {
    $('journeyList').innerHTML = `<div class="empty-state"><div class="empty-icon">↗</div><h3>${state.user ? 'Your next journey starts here.' : 'A calmer way to get your next seat.'}</h3><p>${state.user ? 'Create a request and leave the refreshing to us.' : 'Sign in to save your trips and keep an eye on availability.'}</p><button class="button secondary" data-new>${state.user ? '＋ Plan your first journey' : 'Create your travel desk →'}</button></div>`;
    return;
  }
  $('journeyList').innerHTML = filtered.map(job => {
    const r = job.request, d = job.data;
    return `<article class="journey-card"><div class="card-top"><div><div class="route-label">${escape(r.from_city)}<span>→</span>${escape(r.to_city)}</div><div class="card-subtitle">${date(r.journey_date + 'T12:00:00+06:00', { weekday:'short', year:'numeric' })} · ${r.seat_count} passenger${r.seat_count > 1 ? 's' : ''} · ${job.mode === 'demo' ? 'Demo journey' : 'Shohoz'}</div></div>${badge(job)}</div><div class="card-grid"><div><label>Departure preference</label><strong>${escape(r.departure_start.slice(0, 5))} – ${escape(r.departure_end.slice(0, 5))}</strong></div><div><label>Buying window · Dhaka</label><strong>${when(r.buy_after)} → ${when(r.buy_before)}</strong></div><div><label>Total budget</label><strong>৳ ${money(r.max_total)} <span class="muted">BDT</span></strong></div><div><label>${d.total ? 'Prepared total' : 'WhatsApp updates'}</label><strong>${d.total ? `৳ ${money(d.total)} BDT` : r.whatsapp_opt_in ? (job.mode === 'demo' ? 'Preview mode' : 'Requested') : 'Not requested'}</strong></div></div><div class="card-bottom"><p>${escape(d.message || 'Your request is queued for monitoring.')}</p><button class="button ${job.status === 'AWAITING_PAYMENT' ? 'primary' : 'secondary'}" data-detail="${job.id}">${job.status === 'AWAITING_PAYMENT' ? 'Review & pay →' : 'View journey ↗'}</button></div></article>`;
  }).join('');
}
function renderAlerts() {
  if (!state.alerts.length) { $('alertsList').innerHTML = '<div class="empty-state"><div class="empty-icon">◉</div><h3>No alerts yet.</h3><p>Your booking updates will appear here, together with their delivery status.</p></div>'; return; }
  const names = { preview: 'Demo preview · not sent', not_requested: 'Website only', setup_required: 'Setup required', queued: 'Queued', sending: 'Sending', accepted: 'Accepted by WhatsApp', sent: 'Sent', delivered: 'Delivered', read: 'Read', failed: 'Delivery failed', unknown: 'Delivery unknown', retrying: 'Retry scheduled' };
  $('alertsList').innerHTML = state.alerts.map(alert => `<article class="alert-card"><header><strong>${escape(alert.kind.replaceAll('_', ' '))}</strong><span class="badge ${['delivered','read'].includes(alert.status) ? 'green' : 'amber'}">${escape(names[alert.status] || alert.status)}</span></header><p>${escape(alert.body)}</p>${alert.error ? `<p class="error">${escape(alert.error)}</p>` : ''}<small>${when(alert.created)}</small> <button class="text-button" data-detail="${alert.job_id}">View journey ↗</button></article>`).join('');
}

async function refresh() {
  if (state.refreshing || !state.user) return;
  state.refreshing = true;
  try {
    const data = await api('/api/jobs'); state.jobs = data.jobs; state.alerts = data.alerts;
    renderJobs(); renderAlerts(); $('connectionState').textContent = '● Updates connected';
    if ($('detailDialog').open && state.selected) await loadDetail(state.selected, false);
  } catch (error) { $('connectionState').textContent = 'Updates interrupted · retrying'; }
  finally { state.refreshing = false; }
}
function openAuth(register = false) {
  state.register = register; $('authTitle').textContent = register ? 'Your travel desk awaits' : 'Welcome back';
  $('nameLabel').hidden = !register; $('authForm').elements.name.required = register;
  $('authForm').elements.password.autocomplete = register ? 'new-password' : 'current-password';
  $('authSubmit').textContent = register ? 'Create account →' : 'Sign in';
  $('authToggle').textContent = register ? 'Already have an account? Sign in' : 'New here? Create an account';
  $('authError').textContent = ''; if (!$('authDialog').open) $('authDialog').showModal();
}
$('authToggle').addEventListener('click', () => openAuth(!state.register));
$('authForm').addEventListener('submit', async (event) => {
  event.preventDefault(); $('authSubmit').disabled = true; $('authError').textContent = '';
  try {
    const data = Object.fromEntries(new FormData(event.target));
    const response = await api(`/api/auth/${state.register ? 'register' : 'login'}`, data);
    state.user = response.user; $('authDialog').close(); event.target.reset(); renderAccount(); await refresh();
    toast(`Welcome, ${state.user.name}. Your travel desk is ready.`);
    document.dispatchEvent(new Event('seatwatch:signed-in'));
  } catch (error) { $('authError').textContent = error.message; }
  finally { $('authSubmit').disabled = false; }
});
$('accountButton').addEventListener('click', async () => {
  if (!state.user) return openAuth();
  try { await api('/api/auth/logout', {}); state.user = null; state.jobs = []; state.alerts = []; renderAccount(); renderJobs(); renderAlerts(); } catch (error) { toast(error.message); }
});

function openBooking() {
  if (!state.user) return openAuth(true);
  state.selectedBus = null; $('selectedBusSummary').hidden = true;
  const form = $('bookingForm'); form.reset();
  const now = new Date(); form.elements.journey_date.value = localInput(new Date(now.getTime() + 86400000)).slice(0, 10);
  form.elements.journey_date.min = localInput(now).slice(0, 10);
  form.elements.buy_after.value = localInput(new Date(now.getTime() - 60000));
  form.elements.buy_before.value = localInput(new Date(now.getTime() + 3600000));
  form.elements.contact_email.value = state.user.email;
  if (state.config.mode === 'demo') { form.elements.contact_phone.value = '+8801700000000'; form.elements.whatsapp_phone.value = '+8801700000000'; }
  $('bookingError').textContent = ''; $('passengerFields').innerHTML = ''; renderPassengers(); setStep(0); $('bookingDialog').showModal();
}
function renderPassengers() {
  const count = Number($('bookingForm').elements.seat_count.value);
  const existing = [...document.querySelectorAll('.passenger-row')].map(row => [...row.querySelectorAll('input,select')].map(input => input.value));
  $('passengerFields').innerHTML = Array.from({ length: count }, (_, i) => {
    const name = state.config.mode === 'demo' ? ['Sample', `Rider ${i+1}`] : [state.user.name.split(' ')[0], state.user.name.split(' ').slice(1).join(' ')];
    const previous = existing[i] || [i === 0 || state.config.mode === 'demo' ? name[0] : '', i === 0 || state.config.mode === 'demo' ? name[1] : '', ''];
    return `<div class="passenger-row"><h3>Passenger ${i + 1}</h3><div class="form-grid"><label>First name<input data-first value="${escape(previous[0])}" required maxlength="60"></label><label>Last name<input data-last value="${escape(previous[1])}" required maxlength="60"></label><label>Gender<select data-gender required><option value="">Choose</option><option value="male" ${previous[2] === 'male' ? 'selected' : ''}>Male</option><option value="female" ${previous[2] === 'female' ? 'selected' : ''}>Female</option></select></label></div></div>`;
  }).join('');
}
function setStep(step) {
  state.step = step;
  document.querySelectorAll('[data-step]').forEach(el => el.hidden = Number(el.dataset.step) !== step);
  document.querySelectorAll('[data-step-label]').forEach(el => el.classList.toggle('current', Number(el.dataset.stepLabel) === step));
  $('backStep').hidden = step === 0; $('nextStep').hidden = step === 2; $('createBooking').hidden = step !== 2;
  $('createBooking').textContent = state.selectedBus && state.config.mode !== 'live' ? 'Watch this live bus →' : 'Start watching →';
  $('stepNote').textContent = `Step ${step + 1} of 3`; $('bookingError').textContent = '';
}
function validStep() {
  const fields = document.querySelector(`[data-step="${state.step}"]`).querySelectorAll('input,select');
  for (const field of fields) if (!field.reportValidity()) return false;
  return true;
}
$('bookingForm').elements.seat_count.addEventListener('change', renderPassengers);
$('nextStep').addEventListener('click', () => { if (validStep()) setStep(state.step + 1); });
$('backStep').addEventListener('click', () => setStep(state.step - 1));
$('bookingForm').addEventListener('submit', async (event) => {
  event.preventDefault(); if (state.step !== 2) { if (validStep()) setStep(state.step + 1); return; }
  if (!validStep()) return;
  $('createBooking').disabled = true; $('bookingError').textContent = '';
  try {
    const data = Object.fromEntries(new FormData(event.target));
    data.seat_count = Number(data.seat_count); data.low_seat_threshold = Number(data.low_seat_threshold);
    data.whatsapp_opt_in = event.target.elements.whatsapp_opt_in.checked;
    data.buy_after += ':00+06:00'; data.buy_before += ':00+06:00';
    data.operators = data.operators.split(',').map(s => s.trim()).filter(Boolean);
    data.passengers = [...document.querySelectorAll('.passenger-row')].map(row => ({ first_name: row.querySelector('[data-first]').value.trim(), last_name: row.querySelector('[data-last]').value.trim(), gender: row.querySelector('[data-gender]').value }));
    if (state.selectedBus) { data.selected_offer_id = state.selectedBus.id; data.preferred_seats = state.selectedBus.seats || []; data.monitor_only = state.config.mode !== 'live'; }
    await api('/api/jobs', data); $('bookingDialog').close(); showView('bookings'); state.filter = 'all';
    document.querySelectorAll('[data-filter]').forEach(el => el.classList.toggle('selected', el.dataset.filter === 'all'));
    await refresh(); toast('Your journey is saved. We’ll take it from here.');
  } catch (error) { $('bookingError').textContent = error.message; }
  finally { $('createBooking').disabled = false; }
});

async function loadDetail(id, open = true) {
  try {
    const { job, events, session_available } = await api(`/api/jobs/${id}`);
    state.selected = id;
    const r = job.request, d = job.data;
    $('detailTitle').textContent = `${r.from_city} → ${r.to_city}`;
    const active = ['MONITORING','SCHEDULED'].includes(job.status);
    $('detailContent').innerHTML = `${badge(job)} <span class="muted">${job.mode === 'demo' ? 'Simulated journey · no real ticket' : 'Shohoz · private booking'}</span><p class="muted">${escape(d.message || 'Your request is waiting to be checked.')}</p><dl class="detail-grid"><div><dt>Journey</dt><dd>${date(r.journey_date + 'T12:00:00+06:00', {year:'numeric'})} · ${r.seat_count} seat(s)</dd></div><div><dt>Buying window · Bangladesh</dt><dd>${when(r.buy_after)} → ${when(r.buy_before)}</dd></div><div><dt>Total budget</dt><dd>৳ ${money(r.max_total)} BDT</dd></div><div><dt>Passenger(s)</dt><dd>${r.passengers.map(p => escape(p.first_name + ' ' + p.last_name)).join(', ')}</dd></div>${d.seats ? `<div><dt>Selected seats</dt><dd>${d.seats.map(escape).join(', ')}</dd></div>` : ''}${d.reference ? `<div><dt>${job.mode === 'demo' ? 'Demo reference' : 'Provider reference'}</dt><dd>${escape(d.reference)}</dd></div>` : ''}</dl>${job.status === 'AWAITING_PAYMENT' ? `<div class="payment-box"><h3>${job.mode === 'demo' ? 'Try the manual payment step' : 'Your next step: complete payment'}</h3><p>Total: <strong>৳ ${money(d.total)} BDT</strong> · ${d.expires_at ? `<span class="countdown" data-expires="${escape(d.expires_at)}"></span>` : 'Check Shohoz for the payment deadline.'}</p><p>${job.mode === 'demo' ? 'This button simulates you completing payment. It does not charge you or purchase a ticket.' : 'Open your provider session to pay. The website waits for Shohoz’s confirmation.'}</p>${job.mode === 'demo' ? `<button class="button primary" data-action="demo_pay">Simulate my payment →</button>` : ''}</div>` : ''}<div class="detail-actions">${active ? '<button class="button secondary" data-action="pause">Pause monitoring</button>' : ''}${job.status === 'PAUSED' ? '<button class="button primary" data-action="resume">Resume monitoring</button>' : ''}${active || job.status === 'PAUSED' ? '<button class="button danger" data-action="cancel">Cancel request</button>' : ''}${session_available ? '<button class="button primary" id="openProvider">Open provider session ↗</button>' : ''}${d.ticket_available ? `<a class="button primary" href="/api/jobs/${job.id}/ticket">Download ticket PDF ↓</a>` : ''}${['NEEDS_ATTENTION','AWAITING_PAYMENT','CONFIRMED'].includes(job.status) ? '<button class="button secondary" data-action="close">Close request / session</button>' : ''}</div>${['NEEDS_ATTENTION','AWAITING_PAYMENT'].includes(job.status) ? '<p class="muted">Closing this request does not cancel a reservation with Shohoz. Check the provider before creating another booking.</p>' : ''}${(d.offers || []).length ? `<h3>Matching departures</h3>${d.offers.map(o => `<div class="offer-row"><div><strong>${escape(o.operator)}</strong><small>${escape(o.departure)} · ${o.seats_available} seats listed</small></div><strong>৳ ${money(o.total)} BDT total</strong></div>`).join('')}` : ''}<h3>Activity</h3><ol class="timeline">${events.map(e => `<li>${escape(e.message)}<small>${when(e.created)}</small></li>`).join('')}</ol>`;
    updateCountdowns(); if (open && !$('detailDialog').open) $('detailDialog').showModal();
  } catch (error) { if (open) toast(error.message); }
}
function updateCountdowns() {
  document.querySelectorAll('[data-expires]').forEach(el => { const seconds = Math.max(0, Math.floor((new Date(el.dataset.expires).getTime() - Date.now()) / 1000)); el.textContent = seconds ? `${Math.floor(seconds/60)}m ${String(seconds%60).padStart(2,'0')}s left to pay` : 'Payment time ended'; });
}
async function jobAction(action) {
  if (state.busy) return; state.busy = true;
  try { await api(`/api/jobs/${state.selected}/action`, { action }); await loadDetail(state.selected, false); await refresh(); toast(action === 'demo_pay' ? 'Demo payment completed. No real payment was made.' : 'Request updated.'); }
  catch (error) { toast(error.message); } finally { state.busy = false; }
}

let imageUrl, sessionBusy = false;
async function loadProvider() {
  if (!state.provider || !$('providerDialog').open || sessionBusy) return;
  try {
    const response = await fetch(`/api/jobs/${state.provider}/session`, { cache:'no-store' });
    if (!response.ok) { const data = await response.json(); throw new Error(data.error); }
    const url = URL.createObjectURL(await response.blob()); $('providerImage').src = url;
    if (imageUrl) URL.revokeObjectURL(imageUrl); imageUrl = url; $('providerError').textContent = '';
  } catch (error) { $('providerError').textContent = error.message; }
}
async function providerAction(data) {
  if (sessionBusy) return; sessionBusy = true;
  try { await api(`/api/jobs/${state.provider}/session`, data); $('providerError').textContent = ''; }
  catch (error) { $('providerError').textContent = error.message; }
  finally { sessionBusy = false; await loadProvider(); }
}
$('providerImage').addEventListener('click', event => { const rect = event.target.getBoundingClientRect(); providerAction({ kind:'click', x:(event.clientX - rect.left) * 1200 / rect.width, y:(event.clientY - rect.top) * 850 / rect.height }); });
$('providerInput').addEventListener('submit', event => { event.preventDefault(); const text = event.target.elements.text.value; event.target.reset(); providerAction({ kind:'type', text }); });
document.addEventListener('click', event => {
  const el = event.target.closest('button'); if (!el) return;
  if (el.dataset.view) showView(el.dataset.view);
  if (el.hasAttribute('data-new')) openBooking();
  if (el.dataset.close) $(el.dataset.close).close();
  if (el.dataset.filter) { state.filter = el.dataset.filter; document.querySelectorAll('[data-filter]').forEach(b => b.classList.toggle('selected', b === el)); renderJobs(); }
  if (el.dataset.detail) loadDetail(el.dataset.detail);
  if (el.dataset.action) jobAction(el.dataset.action);
  if (el.id === 'openProvider') { state.provider = state.selected; $('providerDialog').showModal(); loadProvider(); }
  if (el.dataset.key) providerAction({ kind:'key', key:el.dataset.key });
  if (el.dataset.scroll) providerAction({ kind:'scroll', dy:Number(el.dataset.scroll) });
});
async function init() {
  try { const [config, account] = await Promise.all([api('/api/status'), api('/api/auth/me')]); state.config = config; state.user = account.user; renderConfig(); renderAccount(); renderJobs(); renderAlerts(); await refresh(); $('connectionState').textContent = '● Website connected'; const requested = new URLSearchParams(location.search).get('job'); if (requested && state.user) await loadDetail(requested); }
  catch (error) { $('connectionState').textContent = 'Connection unavailable'; toast(error.message); }
}
setInterval(refresh, 5000); setInterval(updateCountdowns, 1000); setInterval(loadProvider, 2500); init();
