const busSearchState = { response: null, offer: null, chosen: [], pending: null, loading: false };
const busSearchForm = $('busSearchForm');
busSearchForm.elements.journey_date.value = localInput(new Date(Date.now() + 86400000)).slice(0, 10);
busSearchForm.elements.journey_date.min = localInput(new Date()).slice(0, 10);

function departureMinutes(value) {
  const match = String(value).match(/(\d{1,2}):(\d{2})\s*(AM|PM)?/i);
  if (!match) return 1440;
  let hour = Number(match[1]);
  if (match[3]) hour = hour % 12 + (match[3].toUpperCase() === 'PM' ? 12 : 0);
  return hour * 60 + Number(match[2]);
}
function busType(offer) { return /non[ -]?ac/i.test(offer.service_class) ? 'non_ac' : /\bac\b/i.test(offer.service_class) ? 'ac' : 'other'; }
function departureBucket(offer) { const minutes = departureMinutes(offer.departure); return minutes < 360 ? 'early' : minutes < 720 ? 'morning' : minutes < 1080 ? 'afternoon' : 'evening'; }

async function searchBuses() {
  if (busSearchState.loading || !busSearchForm.reportValidity()) return;
  busSearchState.loading = true;
  $('busSearchError').textContent = ''; $('searchWelcome').hidden = true; $('searchResults').hidden = true; $('searchLoading').hidden = false;
  $('searchBusesButton').disabled = true;
  const query = Object.fromEntries(new FormData(busSearchForm)); query.seat_count = Number(query.seat_count);
  try {
    const result = await api('/api/search', query);
    busSearchState.response = result;
    $('searchResults').hidden = false;
    $('searchRouteTitle').textContent = `${result.query.from_city} → ${result.query.to_city}`;
    $('searchCheckedAt').textContent = `${date(result.query.journey_date + 'T12:00:00+06:00', { weekday:'long', year:'numeric' })} · Checked ${when(result.checked_at)}`;
    const operators = [...new Set(result.offers.map(o => o.operator))].sort();
    $('busOperatorFilter').innerHTML = '<option value="">All operators</option>' + operators.map(o => `<option>${escape(o)}</option>`).join('');
    const points = [...new Set(result.offers.flatMap(o => o.boarding_points || []))].sort();
    $('busBoardingFilter').innerHTML = '<option value="">Any boarding point</option>' + points.map(p => `<option>${escape(p)}</option>`).join('');
    $('busBoardingFilter').disabled = !points.length;
    const max = Math.max(50, ...result.offers.map(o => Number(o.unit_fare)));
    $('busFareFilter').max = String(Math.ceil(max / 50) * 50);
    resetSearchFilters(); renderDateRail(); renderBusResults();
  } catch (error) {
    busSearchState.response = null;
    $('busSearchError').textContent = error.message;
    $('searchWelcome').hidden = false;
  } finally { busSearchState.loading = false; $('searchLoading').hidden = true; $('searchBusesButton').disabled = false; }
}

function resetSearchFilters() {
  document.querySelectorAll('.bus-filters input[type=checkbox]').forEach(el => el.checked = false);
  $('busOperatorFilter').value = ''; $('busBoardingFilter').value = ''; $('busSort').value = 'fare';
  $('busFareFilter').value = $('busFareFilter').max;
  renderBusResults();
}
function renderDateRail() {
  const selected = busSearchState.response.query.journey_date;
  const day = new Date(selected + 'T12:00:00+06:00');
  const today = localInput(new Date()).slice(0, 10);
  $('searchDateRail').innerHTML = Array.from({ length:5 }, (_, i) => {
    const value = new Date(day.getTime() + (i - 1) * 86400000);
    const key = localInput(value).slice(0, 10);
    return `<button type="button" data-search-date="${key}" ${key < today ? 'disabled' : ''} class="${key === selected ? 'selected' : ''}"><span>${date(value.toISOString(), {weekday:'short'})}</span>${key === selected ? '<small>Selected date</small>' : '<small>View departures</small>'}</button>`;
  }).join('');
}

function renderBusResults() {
  if (!busSearchState.response) return;
  const { offers, query } = busSearchState.response;
  const types = [...document.querySelectorAll('[name=bus_type]:checked')].map(el => el.value);
  const times = [...document.querySelectorAll('[name=departure_bucket]:checked')].map(el => el.value);
  const operator = $('busOperatorFilter').value, boarding = $('busBoardingFilter').value;
  const limit = Number($('busFareFilter').value);
  $('busFareLabel').textContent = `৳ ${money(limit)} per seat`;
  const filtered = offers.filter(o => (!types.length || types.includes(busType(o))) && (!times.length || times.includes(departureBucket(o))) && (!operator || o.operator === operator) && (!boarding || o.boarding_points.includes(boarding)) && Number(o.unit_fare) <= limit);
  const sort = $('busSort').value;
  filtered.sort((a,b) => sort === 'departure' ? departureMinutes(a.departure) - departureMinutes(b.departure) : sort === 'seats' ? b.seats_available - a.seats_available : (Number(a.unit_fare) - Number(b.unit_fare)) * (sort === 'fare_desc' ? -1 : 1));
  $('busResultCount').textContent = `${filtered.length} of ${offers.length} departures`;
  if (!filtered.length) {
    $('busResultList').innerHTML = `<div class="empty-state"><div class="empty-icon">⌕</div><h3>${offers.length ? 'No buses match these filters.' : 'No available departures were returned.'}</h3><p>${offers.length ? 'Try another departure time, operator, or fare limit.' : 'Try another date or route. Live availability can change.'}</p>${offers.length ? '<button class="button secondary" data-reset-search>Reset filters</button>' : ''}</div>`;
    return;
  }
  $('busResultList').innerHTML = filtered.map(o => {
    const enough = o.seats_available >= query.seat_count;
    const type = busType(o) === 'non_ac' ? 'Non AC' : busType(o) === 'ac' ? 'AC' : 'Bus';
    return `<article class="bus-card"><div class="bus-card-main"><div class="bus-operator"><div class="operator-initial">${escape(o.operator.charAt(0))}</div><div><h3>${escape(o.operator)}</h3><p>${escape(o.service_class)}</p><span class="bus-type-tag">${type}</span></div></div><div class="bus-times"><div><strong>${escape(o.departure)}</strong><small>${escape(query.from_city)}</small></div><div class="duration-line"><span>${escape(o.duration || 'Direct search')}</span><i>→</i></div><div><strong>${escape(o.arrival || '—')}</strong><small>${escape(query.to_city)}</small></div></div><div class="bus-fare"><small>from / seat</small><strong>৳ ${money(o.unit_fare)}</strong><span>${query.seat_count > 1 ? `৳ ${money(Number(o.unit_fare) * query.seat_count)} for ${query.seat_count} seats` : 'BDT · before provider fees'}</span></div></div><div class="bus-card-bottom"><div><span class="seat-availability ${o.seats_available <= 5 ? 'low' : ''}">◉ ${o.seats_available} seats available</span>${!enough ? `<small class="error">Not enough for ${query.seat_count} passengers</small>` : ''}</div><div class="bus-card-actions"><button type="button" class="text-button" data-bus-details="${escape(o.id)}">Route & stops ⌄</button><button type="button" class="button secondary" data-watch-bus="${escape(o.id)}">Watch bus</button><button type="button" class="button primary" data-view-seats="${escape(o.id)}" ${!enough || o.provider_note ? 'disabled' : ''}>Select seats →</button></div></div>${o.provider_note ? `<p class="bus-provider-note">${escape(o.provider_note)}</p>` : ''}<div class="bus-expanded-details" id="bus-details-${escape(o.id)}" hidden><p><strong>Route</strong> ${escape(o.route)}</p><p><strong>Boarding</strong> ${escape((o.boarding_points || []).join(' · ') || 'See the provider seat map for current stops.')}</p><p><strong>Dropping</strong> ${escape((o.dropping_points || []).join(' · ') || query.to_city)}</p></div></article>`;
  }).join('');
}

async function openSeatMap(offerId) {
  busSearchState.offer = busSearchState.response.offers.find(o => o.id === offerId);
  const offer = busSearchState.offer;
  if (!offer) return;
  busSearchState.chosen = [];
  $('seatBusTitle').textContent = offer.operator;
  $('seatBusMeta').textContent = `${offer.departure} · ${offer.service_class} · ৳ ${money(offer.unit_fare)} per seat`;
  $('nativeSeatMap').innerHTML = '';
  $('seatMapStatus').textContent = 'Loading the live seat map from Shohoz…'; $('seatMapError').textContent = '';
  const query = busSearchState.response.query;
  const day = new Date(query.journey_date + 'T12:00:00+06:00');
  const doj = `${String(day.getUTCDate()).padStart(2,'0')}-${day.toLocaleString('en-US',{month:'short',timeZone:'Asia/Dhaka'})}-${day.getUTCFullYear()}`;
  $('openShohozSearch').href = 'https://www.shohoz.com/bus-tickets/booking/bus/search?' + new URLSearchParams({fromcity:query.from_city,tocity:query.to_city,doj,dor:''});
  $('openShohozSearch').hidden = true;
  updateSeatSelection(); $('seatDialog').showModal();
  const searchId = busSearchState.response.search_id;
  try {
    const map = await api(`/api/search/${encodeURIComponent(searchId)}/offers/${encodeURIComponent(offerId)}/seats`);
    if (busSearchState.offer.id !== offerId) return;
    $('seatMapStatus').textContent = map.message;
    const groupPositions = values => values.sort((a,b) => a-b).reduce((groups, value) => { if (!groups.length || value - groups[groups.length-1] > 12) groups.push(value); return groups; }, []);
    const xs = groupPositions(map.seats.map(s => s.x)), ys = groupPositions(map.seats.map(s => s.y));
    const grid = $('nativeSeatMap'); grid.style.gridTemplateColumns = `repeat(${Math.max(4, xs.length)}, minmax(36px, 1fr))`;
    grid.innerHTML = map.seats.map(seat => `<button type="button" class="native-seat ${seat.female_only ? 'restricted' : seat.available ? 'available' : 'booked'}" data-seat-label="${escape(seat.label)}" aria-label="Seat ${escape(seat.label)}${seat.available ? '' : ', unavailable'}${seat.female_only ? ', restricted' : ''}" aria-pressed="false" ${!seat.available || seat.female_only ? 'disabled' : ''}>${escape(seat.label)}</button>`).join('');
    [...grid.children].forEach((button, i) => {
      const seat = map.seats[i];
      button.style.gridColumn = String(xs.findIndex(x => Math.abs(x-seat.x) <= 12) + 1);
      button.style.gridRow = String(ys.findIndex(y => Math.abs(y-seat.y) <= 12) + 1);
    });
  } catch (error) { $('seatMapStatus').textContent = ''; $('seatMapError').textContent = error.message; $('openShohozSearch').hidden = false; }
}
function updateSeatSelection() {
  const { chosen, offer, response } = busSearchState;
  $('selectedSeatNames').textContent = chosen.length ? chosen.join(', ') : 'No seats selected';
  $('selectedSeatTotal').textContent = `৳ ${money(chosen.length * Number(offer.unit_fare))}`;
  $('continueSelectedBus').disabled = chosen.length !== response.query.seat_count;
  $('continueSelectedBus').textContent = state.config?.mode === 'live' ? 'Continue to booking →' : 'Watch this bus →';
  document.querySelectorAll('[data-seat-label]').forEach(button => { const selected = chosen.includes(button.dataset.seatLabel); button.classList.toggle('chosen', selected); button.setAttribute('aria-pressed', String(selected)); });
}
function planSelectedBus(offer, seats = [], query = busSearchState.response.query) {
  if (!state.user) { busSearchState.pending = { offer, seats, query }; if ($('seatDialog').open) $('seatDialog').close(); openAuth(true); return; }
  if ($('seatDialog').open) $('seatDialog').close();
  openBooking();
  state.selectedBus = { ...offer, seats };
  const form = $('bookingForm');
  for (const field of ['from_city','to_city','journey_date','seat_count']) form.elements[field].value = query[field];
  const minutes = departureMinutes(offer.departure);
  const time = `${String(Math.floor(minutes / 60)).padStart(2,'0')}:${String(minutes % 60).padStart(2,'0')}`;
  form.elements.departure_start.value = time; form.elements.departure_end.value = time;
  form.elements.operators.value = offer.operator;
  form.elements.max_total.value = Math.ceil(Number(offer.unit_fare) * query.seat_count * 1.1);
  form.elements.boarding_point.value = $('busBoardingFilter').value;
  $('selectedBusSummary').hidden = false;
  $('selectedBusSummary').innerHTML = `<strong>${escape(offer.operator)} · ${escape(offer.departure)}</strong><p>${escape(query.from_city)} → ${escape(query.to_city)} · ${escape(query.journey_date)}${seats.length ? ` · Seats ${seats.map(escape).join(', ')}` : ''}</p><p>${state.config.mode === 'live' ? 'This request targets this exact departure. The fare and seats will be checked again before preparation.' : 'This creates a live availability watch. Real reservations are not enabled yet, so no seats will be held or purchased.'}</p>`;
  renderPassengers(); setStep(1);
  $('createBooking').textContent = state.config.mode === 'live' ? 'Schedule this booking →' : 'Watch this live bus →';
}

busSearchForm.addEventListener('submit', event => { event.preventDefault(); searchBuses(); });
$('swapCities').addEventListener('click', () => { const a = busSearchForm.elements.from_city, b = busSearchForm.elements.to_city; [a.value,b.value] = [b.value,a.value]; });
$('resetBusFilters').addEventListener('click', resetSearchFilters);
document.querySelectorAll('.bus-filters input, .bus-filters select, #busSort').forEach(el => el.addEventListener('input', renderBusResults));
$('continueSelectedBus').addEventListener('click', () => planSelectedBus(busSearchState.offer, busSearchState.chosen));
$('watchBusWithoutSeats').addEventListener('click', () => planSelectedBus(busSearchState.offer));
document.addEventListener('seatwatch:signed-in', () => { if (busSearchState.pending) { const pending = busSearchState.pending; busSearchState.pending = null; planSelectedBus(pending.offer,pending.seats,pending.query); } });
document.addEventListener('click', event => {
  const button = event.target.closest('button'); if (!button) return;
  if (button.hasAttribute('data-reset-search')) resetSearchFilters();
  if (button.dataset.popular) { busSearchForm.elements.from_city.value = 'Dhaka'; busSearchForm.elements.to_city.value = button.dataset.popular; searchBuses(); }
  if (button.dataset.searchDate) { busSearchForm.elements.journey_date.value = button.dataset.searchDate; searchBuses(); }
  if (button.dataset.viewSeats) openSeatMap(button.dataset.viewSeats);
  if (button.dataset.watchBus) planSelectedBus(busSearchState.response.offers.find(o => o.id === button.dataset.watchBus));
  if (button.dataset.busDetails) { const panel = $(`bus-details-${button.dataset.busDetails}`); panel.hidden = !panel.hidden; }
  if (button.dataset.seatLabel) {
    const label = button.dataset.seatLabel, chosen = busSearchState.chosen;
    if (chosen.includes(label)) busSearchState.chosen = chosen.filter(s => s !== label);
    else if (chosen.length < busSearchState.response.query.seat_count) chosen.push(label);
    else toast(`Choose up to ${busSearchState.response.query.seat_count} seats, or change the seat count in your search.`);
    updateSeatSelection();
  }
});
