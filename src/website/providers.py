"""Shohoz browser integration. Automated actions stop at the payment review page.

Selectors were inspected in Shohoz's public Angular application on 2026-10-01.
Unknown layouts or ambiguous totals require attention; they never trigger guessed clicks.
"""
import hashlib
import re
import shutil
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode, urlparse

from src.monitoring.availability_parser import parse_offer_texts
from src.website.domain import BookingRequest, BusOffer, NeedsAttention, utcnow


class DemoProvider:
    """Deterministic simulation; never connects to Shohoz or sends messages."""
    def __init__(self, config):
        self.config = config

    async def search(self, request):
        return [BusOffer(id='demo-morning', operator='Demo Paribahan',
                         route=f'{request.from_city} → {request.to_city}', departure='08:30 AM',
                         arrival='02:30 PM', unit_fare=Decimal('650'), seats_available=4,
                         service_class='Non AC · simulated')]

    async def seat_map(self, offer_id):
        return {'seats': [{'label': f'A{i+1}', 'available': True, 'female_only': False, 'x': i*45, 'y': 0} for i in range(4)]}

    async def preflight(self, request, offer):
        return await self.seat_map(offer.id)

    async def prepare(self, request, offer):
        return {'offer': offer.model_dump(mode='json'), 'total': str(offer.total(request)),
                'seats': request.preferred_seats or [f'A{i+1}' for i in range(request.seat_count)],
                'expires_at': (utcnow() + timedelta(minutes=10)).isoformat(),
                'message': 'Demo booking prepared. No real seats are held and no payment is charged.'}

    async def inspect(self):
        return None

    async def close(self):
        pass


class ShohozProvider:
    def __init__(self, config):
        self.config = config
        self.playwright = self.browser = self.context = self.page = None
        self.cards = {}
        self.ticket_bytes = None
        self.budget = getattr(config, "_browser_budget", None)
        self.budget_held = False
        self.storage = None

    async def open(self):
        if self.page is not None:
            return
        if self.budget:
            self.budget.acquire()
            self.budget_held = True
        try:
            from playwright.async_api import async_playwright
            self.playwright = await async_playwright().start()
            options = {'headless': True}
            executable = self.config.browser_executable or shutil.which('google-chrome') or shutil.which('chromium')
            if not executable and Path('/opt/google/chrome/chrome').is_file():
                executable = '/opt/google/chrome/chrome'
            if executable:
                options['executable_path'] = executable
            self.browser = await self.playwright.chromium.launch(**options)
            self.context = await self.browser.new_context(viewport={'width': 1200, 'height': 850},
                                                           locale='en-US', timezone_id='Asia/Dhaka', storage_state=self.storage)
            self.page = await self.context.new_page()
            self.page.set_default_timeout(15000)
        except BaseException:
            await self.close()
            raise

    async def checkpoint(self):
        text = await self.page.locator('body').inner_text()
        if re.search(r'(?i)verify you are human|complete the captcha|verify your identity|enter.*OTP|one.time password', text):
            raise NeedsAttention('Shohoz requires verification. Open the provider session to complete it yourself.')
        return text

    async def search(self, request):
        await self.open()
        url = 'https://www.shohoz.com/bus-tickets/booking/bus/search?' + urlencode({
            'fromcity': request.from_city, 'tocity': request.to_city,
            'doj': request.journey_date.strftime('%d-%b-%Y'), 'dor': ''})
        async with self.page.expect_response(lambda response: '/booking/bus/search-trips' in response.url, timeout=45000) as search_response:
            await self.page.goto(url, wait_until='domcontentloaded', timeout=45000)
        response = await search_response.value
        if not response.ok:
            raise NeedsAttention('Shohoz could not return live departures. Please try again shortly.')
        inventory = (await response.json()).get('data', {}).get('trips', {}).get('list', [])
        self.cards.clear()
        if not inventory:
            return []
        await self.page.wait_for_function("""() => document.querySelector('app-trip') ||
            /no (?:bus|trip|ticket)|sold out|verify you are human/i.test(document.body.innerText)""", timeout=30000)
        await self.checkpoint()
        self.cards.clear()
        offers = []
        cards = self.page.locator('app-trip')
        # Read all cards in one browser round-trip instead of hundreds of RPCs.
        card_data = await cards.evaluate_all('''els => els.map(el => ({text:el.innerText,
            trip:el.querySelector('[tripid]')?.getAttribute('tripid'),
            destination:el.querySelector('.arrival-station')?.innerText?.trim()}))''')
        for index, entry in enumerate(card_data):
            text = entry['text']
            card = cards.nth(index)
            parsed = parse_offer_texts(text)
            if len(parsed) != 1:
                continue
            item = parsed[0]
            if not item.departure_time or item.available_seats is None:
                continue
            matching = [trip for trip in inventory if str(trip.get('trip_id')) == entry['trip']
                        and str(trip.get('destination_city_name', '')).casefold() == str(entry.get('destination') or request.to_city).casefold()]
            metadata = matching[0] if len(matching) == 1 else {}
            identity = (f"{metadata['trip_id']}:{metadata['trip_route_id']}" if metadata else
                        '|'.join((entry['trip'] or '', item.title, item.section, item.departure_time, item.arrival_time or '', entry.get('destination') or '', item.service_class or '')))
            identity = hashlib.sha256(identity.encode()).hexdigest()[:24]
            if identity in self.cards:
                # A duplicate cannot safely identify one provider departure.
                continue
            self.cards[identity] = card
            offers.append(BusOffer(id=identity, operator=item.title, route=item.section,
                departure=item.departure_time, arrival=item.arrival_time or '',
                unit_fare=Decimal(str(item.total_usd)), seats_available=item.available_seats,
                service_class=item.service_class or '', currency=item.currency,
                duration=item.duration or '',
                boarding_points=[p['location_name'] for p in metadata.get('boarding_points', []) if p.get('location_name')],
                dropping_points=[p['location_name'] for p in metadata.get('dropping_points', []) if p.get('location_name')],
                provider_note=next((line.strip() for line in text.splitlines() if line.strip().startswith('Dear traveler')), '')))
        return offers

    async def seat_map(self, offer_id):
        card = self.cards.get(offer_id)
        if card is None:
            raise NeedsAttention('Search again to refresh this departure.')
        # Dismiss a previous map before opening another bus. No seats are selected here.
        await self.page.keyboard.press('Escape')
        modal = self.page.locator('app-booking-modal')
        close = modal.locator('button[aria-label="Close"], button.close, .modal-close, .close-button, button.absolute.right-3.top-3').filter(visible=True)
        if await close.count():
            await close.first.click()
        async with self.page.expect_response(lambda response: '/booking/bus/seat-layout' in response.url, timeout=25000) as layout_response:
            await card.get_by_role('button', name=re.compile(r'^book ticket$', re.I)).click()
        response = await layout_response.value
        if response.status in {401, 403}:
            raise NeedsAttention('Shohoz requires sign-in to view this seat map. You can still watch this bus here, or open Shohoz to sign in and choose seats there.')
        if not response.ok:
            raise NeedsAttention('Shohoz could not load this seat map. Please refresh the search or try another bus.')
        await self.page.locator('app-booking-modal [title].seat-available, app-booking-modal [title].seat-booked').first.wait_for(timeout=20000)
        seats = await modal.locator('[title].seat-available, [title].seat-booked, [title].seat-female').evaluate_all('''els => {
            const seen = new Set();
            return els.filter(el => el.getBoundingClientRect().width && !seen.has(el.title) && seen.add(el.title)).map(el => {
                const box = el.getBoundingClientRect();
                return {label:el.title, available:el.classList.contains('seat-available') && !el.disabled && !el.classList.contains('seat-booked') && !el.classList.contains('seat-disabled'),
                    female_only:el.classList.contains('seat-female'), x:Math.round(box.x), y:Math.round(box.y)};
            });
        }''')
        if not seats:
            raise NeedsAttention('The provider did not return a readable seat map. Please try another departure.')
        return {'seats': seats, 'message': 'Live seat availability. Selecting here records your preference; seats are not held until booking preparation.'}

    async def export_session(self):
        if not self.context or not self.page:
            return None
        return {'url': self.page.url, 'storage': await self.context.storage_state()}

    async def restore_session(self, state, navigate=False):
        from src.website.runtime import SessionVault
        if not SessionVault.allowed_url(state['url']):
            raise NeedsAttention('The saved provider URL is not valid.')
        self.storage = state['storage']
        if navigate:
            # Resume an existing session only. Never invoke search/prepare or select seats here.
            await self.open()
            await self.page.goto(state['url'], wait_until='domcontentloaded', timeout=45000)
            await self.page.wait_for_timeout(1500)

    async def preflight(self, request, offer):
        try:
            return await self.seat_map(offer.id)
        except NeedsAttention as exc:
            if 'sign-in' in str(exc):
                raise NeedsAttention('Shohoz requires sign-in. Open your private provider session, finish verification, then resume monitoring. No seats have been selected.')
            raise

    def ensure_deadline(self, request, offer):
        departure = offer.departure_at(request)
        cutoff = departure - timedelta(minutes=self.config.website_departure_buffer_minutes) if departure else request.buy_before
        if utcnow() >= min(request.buy_before, cutoff):
            raise NeedsAttention('The booking cutoff was reached. No further automated actions will be made; check any held seats with Shohoz.')

    async def prepare(self, request: BookingRequest, offer: BusOffer):
        if not offer.matches(request):
            raise NeedsAttention('This offer no longer satisfies the request.')
        if offer.provider_note:
            raise NeedsAttention(offer.provider_note)
        card = self.cards.get(offer.id)
        if card is None:
            raise NeedsAttention('The selected departure is no longer on the current page.')
        # Re-read the exact card just before any hold is attempted.
        fresh = parse_offer_texts(await card.inner_text())
        if len(fresh) != 1 or Decimal(str(fresh[0].total_usd)) != offer.unit_fare or (fresh[0].available_seats or 0) < request.seat_count:
            raise NeedsAttention('The fare or seat availability changed. Review the provider session.')
        self.ensure_deadline(request, offer)
        if not await self.page.locator('app-booking-modal .seat-available:visible').count():
            await self.preflight(request, offer)
        await self.page.locator('.seat-available:visible').first.wait_for()
        await self.checkpoint()
        seats = self.page.locator('.seat-available:visible:not(.seat-booked):not(.seat-disabled):not(.seat-selected):not(.seat-female):not([disabled])')
        candidates = []
        for i in range(await seats.count()):
            seat = seats.nth(i)
            label, box = await seat.get_attribute('title'), await seat.bounding_box()
            if label and box:
                candidates.append((seat, label, box))
        if request.seat_preference in {'window', 'aisle'}:
            # Without a verified layout map, guessing an edge is unsafe (double-deck/sleeper).
            raise NeedsAttention('Window/aisle selection needs a verified seat map. Choose the seats in the provider session.')
        candidates.sort(key=lambda item: (item[2]['y'], item[2]['x']))
        if request.preferred_seats:
            by_label = {item[1]: item for item in candidates}
            if all(label in by_label for label in request.preferred_seats):
                candidates = [by_label[label] for label in request.preferred_seats]
            elif request.seat_fallback != 'any':
                raise NeedsAttention('One of your selected seats is no longer available. Review the seat map.')
        if request.seat_preference == 'middle' and candidates:
            mid = (candidates[0][2]['y'] + candidates[-1][2]['y']) / 2
            candidates.sort(key=lambda item: abs(item[2]['y'] - mid))
        if len(candidates) < request.seat_count:
            raise NeedsAttention('There are not enough eligible seats. Review seat restrictions on Shohoz.')
        selected = []
        for seat, label, _ in candidates[:request.seat_count]:
            self.ensure_deadline(request, offer)
            await seat.click()
            await self.page.wait_for_function("""label => [...document.querySelectorAll('.seat-selected')]
                .some(el => el.getAttribute('title') === label)""", arg=label)
            selected.append(label)
        modal = self.page.locator('app-booking-modal')
        self.ensure_deadline(request, offer)
        await modal.get_by_role('button', name=re.compile('continue', re.I)).filter(visible=True).first.click()
        points = self.page.locator('#select-boarding-point-step .boarding-point-item:visible')
        if request.boarding_point:
            points = points.filter(has_text=request.boarding_point)
        if not await points.count():
            raise NeedsAttention('Choose a boarding point in the provider session.')
        await points.first.click(position={'x': 10, 'y': 10})
        self.ensure_deadline(request, offer)
        await modal.get_by_role('button', name=re.compile('^continue$', re.I)).filter(visible=True).first.click()
        await self.page.wait_for_url('**/trip-info**')
        await self.checkpoint()
        forms = self.page.locator('app-passenger-form')
        if await forms.count() != request.seat_count:
            raise NeedsAttention('Shohoz requested a different number of passenger forms.')
        for index, passenger in enumerate(request.passengers):
            form = forms.nth(index)
            await form.locator('[formcontrolname="first_name"]').fill(passenger.first_name)
            await form.locator('[formcontrolname="last_name"]').fill(passenger.last_name)
            await form.get_by_role('button', name=passenger.gender.capitalize(), exact=True).click()
        phone = request.contact_phone
        if not phone.startswith('+880'):
            raise NeedsAttention('This Shohoz contact form needs a Bangladesh phone number.')
        await self.page.locator('#mobile').fill('0' + phone[4:])
        await self.page.locator('#email').fill(request.contact_email)
        # This button only moves from passenger details to review; no payment method is selected.
        if '/trip-info' not in urlparse(self.page.url).path:
            raise NeedsAttention('Unexpected provider page before payment review.')
        self.ensure_deadline(request, offer)
        await self.page.get_by_role('button', name='PROCEED TO PAYMENT', exact=True).click()
        await self.page.wait_for_url('**/bus/pay**')
        text = await self.checkpoint()
        total = self.review_total(text)
        if total is None:
            raise NeedsAttention('Payment review is open, but the complete total could not be verified. Check it manually.')
        if total > request.max_total:
            raise NeedsAttention(f'The final total including fees is BDT {total}, above your BDT {request.max_total} limit. No payment was submitted.')
        return {'offer': offer.model_dump(mode='json'), 'total': str(total), 'seats': selected,
                'expires_at': self.expiry(text), 'provider_url': self.page.url,
                'message': 'Seats and passenger details prepared. Complete payment in your private provider session. A ticket is confirmed only after Shohoz confirms it.'}

    @staticmethod
    def review_total(text):
        matches = re.findall(r'(?i)(?:grand total|total payable|payable amount|total amount)\s*[:\n]?\s*(?:BDT|Tk\.?|৳)?\s*([\d,]+(?:\.\d{1,2})?)', text)
        return max((Decimal(m.replace(',', '')) for m in matches), default=None)

    @staticmethod
    def expiry(text):
        match = re.search(r'(?i)(?:time left|expires in|remaining time)\s*:?\s*(\d{1,2}):(\d{2})', text)
        if match:
            return (utcnow() + timedelta(minutes=int(match[1]), seconds=int(match[2]))).isoformat()
        return None

    async def inspect(self):
        if self.page is None:
            return None
        text = await self.page.locator('body').inner_text()
        if re.search(r'(?i)reservation expired|session expired|booking expired', text):
            return {'expired': True}
        reference = re.search(r'(?i)(?:PNR(?:\s+number)?|booking reference|ticket number)\s*[:#]?\s*([A-Z0-9-]{5,30})', text)
        current = urlparse(self.page.url)
        if current.scheme == 'https' and current.hostname == 'www.shohoz.com' and '/bus-tickets/booking/bus/confirmed' in current.path and reference:
            await self.download_ticket()
            return {'confirmed': True, 'reference': reference[1], 'provider_url': self.page.url}
        return None

    async def download_ticket(self):
        """Capture a provider-supplied PDF only after provider confirmation."""
        if self.ticket_bytes is not None:
            return
        control = self.page.get_by_role('link', name=re.compile(r'download.*ticket|download.*pdf', re.I))
        if not await control.count():
            control = self.page.get_by_role('button', name=re.compile(r'download.*ticket|download.*pdf', re.I))
        if await control.count() != 1:
            return
        try:
            async with self.page.expect_download(timeout=10000) as download:
                await control.click()
            file = await download.value
            path = await file.path()
            if path and Path(path).stat().st_size <= 10 * 1024 * 1024:
                data = Path(path).read_bytes()
                if data.startswith(b'%PDF-'):
                    self.ticket_bytes = data
        except Exception:
            # Download failure must not turn a paid booking into an unconfirmed one.
            return

    async def screenshot(self):
        if self.page is None:
            raise NeedsAttention('This provider session is not open.')
        return await self.page.screenshot(type='png')

    async def verification_gesture(self, action):
        """Only gestures confined to Shohoz's login iframe are safe to resume after."""
        if self.page is None:
            return False
        frame = self.page.locator('iframe[src^="https://www.shohoz.com/login"]:visible')
        if await frame.count() != 1:
            return False
        if action.get('kind') == 'click':
            box = await frame.bounding_box()
            x, y = float(action.get('x', -1)), float(action.get('y', -1))
            return bool(box and box['x'] <= x <= box['x'] + box['width'] and box['y'] <= y <= box['y'] + box['height'])
        if action.get('kind') in {'type','key','scroll'}:
            return await frame.evaluate('(el) => document.activeElement === el')
        return False

    async def manual_action(self, action):
        """Only explicit user gestures reach this method; payment is never automated."""
        if self.page is None:
            raise NeedsAttention('This provider session is not open.')
        kind = action.get('kind')
        if kind == 'click':
            x, y = float(action['x']), float(action['y'])
            if not (0 <= x <= 1200 and 0 <= y <= 850):
                raise ValueError('Click is outside the viewport')
            await self.page.mouse.click(x, y)
        elif kind == 'type':
            value = str(action.get('text', ''))
            if len(value) > 500:
                raise ValueError('Input is too long')
            await self.page.keyboard.insert_text(value)
        elif kind == 'key' and action.get('key') in {'Tab', 'Enter', 'Backspace', 'Escape', 'Control+A'}:
            await self.page.keyboard.press(action['key'])
        elif kind == 'scroll':
            await self.page.mouse.wheel(0, max(-700, min(700, int(action.get('dy', 0)))))
        else:
            raise ValueError('Unsupported browser action')

    async def close(self):
        try:
            if self.browser:
                await self.browser.close()
        finally:
            try:
                if self.playwright:
                    await self.playwright.stop()
            finally:
                self.playwright = self.browser = self.context = self.page = None
                if self.budget and self.budget_held:
                    self.budget.release()
                    self.budget_held = False


def provider_for(mode, config):
    return DemoProvider(config) if mode == 'demo' else ShohozProvider(config)
