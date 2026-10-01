import asyncio
from datetime import datetime, timedelta
import logging
import time

from src.website.domain import BookingRequest, MONITORED, NeedsAttention, ProviderBusy, utcnow
from src.website.providers import provider_for
from src.website.runtime import SessionVault

logger = logging.getLogger(__name__)


class BookingWorker:
    def __init__(self, store, config, whatsapp, factory=provider_for):
        self.store, self.config, self.whatsapp, self.factory = store, config, whatsapp, factory
        self.providers, self.locks, self.tasks, self.touched = {}, {}, {}, {}
        self.stop_event = asyncio.Event()
        self.vault = SessionVault(config.website_database)

    def lock(self, jid):
        return self.locks.setdefault(jid, asyncio.Lock())

    def touch(self, jid):
        self.touched[jid] = time.monotonic()

    async def get_provider(self, job, restore=True):
        jid = job['id']
        if jid not in self.providers:
            provider = self.factory(job['mode'], self.config)
            self.providers[jid] = provider
            if restore and job['mode'] == 'live' and hasattr(provider, 'restore_session'):
                state = self.vault.load(jid)
                if state:
                    await provider.restore_session(state, navigate=False)
            self.touch(jid)
        return self.providers[jid]

    async def checkpoint(self, jid):
        provider = self.providers.get(jid)
        if not provider or not hasattr(provider, 'export_session'):
            return
        try:
            state = await asyncio.wait_for(provider.export_session(), timeout=10)
            if state:
                self.vault.save(jid, state)
        except Exception:
            # Do not replace a known booking state if checkpointing fails.
            self.store.event(jid, 'checkpoint_failed', 'Provider session could not be saved. Keep this server running until payment is resolved.')

    async def run(self):
        self.store.recover()
        while not self.stop_event.is_set():
            self.store.heartbeat('worker')
            for jid, task in list(self.tasks.items()):
                if task.done():
                    self.tasks.pop(jid)
                    if not task.cancelled() and task.exception():
                        logger.error('Booking task failed; see request activity. No provider inputs logged.')
            for job in self.store.due():
                if len(self.tasks) >= self.config.website_worker_concurrency:
                    break
                if job['id'] not in self.tasks and not self.lock(job['id']).locked():
                    self.tasks[job['id']] = asyncio.create_task(self.process(job))
            await self.sweep_sessions()
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

    async def sweep_sessions(self):
        for jid in list(self.providers):
            if self.lock(jid).locked():
                continue
            if time.monotonic() - self.touched.get(jid, 0) < self.config.website_session_idle_minutes * 60:
                continue
            async with self.lock(jid):
                job = self.store.job(jid)
                if job and job['status'] == 'AWAITING_PAYMENT':
                    self.store.update(jid, 'NEEDS_ATTENTION', {**job['data'], 'recovery_required':True,
                        'message':'The idle browser was closed to free capacity. Reconnect your saved provider session to check payment; no new reservation will be attempted.'})
                    self.alert(job, 'attention', 'Your idle provider session needs reconnecting. Check payment status before creating another booking.')
                await self.release(jid)

    async def process(self, job):
        jid = job['id']
        async with self.lock(jid):
            job = self.store.job(jid)
            if job['status'] not in MONITORED | {'AWAITING_PAYMENT'}:
                return
            req = BookingRequest.model_validate(job['request'])
            data = job['data']
            interval = 5 if job['mode'] == 'demo' else self.config.website_poll_seconds
            if job['status'] in MONITORED and utcnow() >= req.buy_before:
                await self.expire(job, data, 'Your time window ended. No further booking attempts will be made.')
                return
            preparing = False
            previous_errors = data.get('errors', 0)
            try:
                provider = await self.get_provider(job)
                if job['status'] == 'AWAITING_PAYMENT':
                    await self.inspect_payment(job, provider, interval)
                    return
                offers = await asyncio.wait_for(provider.search(req), timeout=self.config.website_provider_timeout)
                related = [o for o in offers if o.relevant(req)]
                data.update({'last_checked':utcnow().isoformat(), 'errors':0})
                for offer in related:
                    if offer.seats_available <= req.low_seat_threshold:
                        self.alert(job, 'low_seats', f'Only {offer.seats_available} seats are listed on {offer.operator}, departing {offer.departure}.', offer.id)
                    if offer.seats_available < req.seat_count:
                        self.alert(job, 'insufficient_seats', f'{offer.operator} now lists {offer.seats_available} seats; you need {req.seat_count}. We will keep watching within your window.', offer.id)
                    if offer.total(req) > req.max_total:
                        self.alert(job, 'over_budget', f'The listed total for {offer.operator} is now BDT {offer.total(req)}, above your limit. No booking will be prepared at this fare.', offer.id)
                if req.selected_offer_id and not related and data.get('departure_seen'):
                    self.alert(job, 'departure_unlisted', 'Your selected departure is no longer listed in the current search. This is not confirmation that it is sold out. We will keep checking.', req.selected_offer_id)
                if related:
                    data['departure_seen'] = True
                    data['observed_seats'] = {o.id:o.seats_available for o in related[:20]}
                now = utcnow()
                if now >= req.buy_before:
                    await self.expire(job, data, 'Your time window ended during the search.')
                    return
                matches = sorted((o for o in related if o.matches(req) and o.departure_at(req) and
                    now < o.departure_at(req) - timedelta(minutes=self.config.website_departure_buffer_minutes)),
                    key=lambda o:(o.total(req), -o.seats_available))
                data['offers'] = [{**o.model_dump(mode='json'),'total':str(o.total(req))} for o in matches[:10]]
                if related and all(o.departure_at(req) and now >= o.departure_at(req) - timedelta(minutes=self.config.website_departure_buffer_minutes) for o in related):
                    if req.selected_offer_id or req.departure_start == req.departure_end:
                        await self.expire(job, data, 'The departure cutoff was reached. No reservation was attempted.')
                        return
                if not matches:
                    data['message'] = 'Watching for enough seats within your budget and departure cutoff.'
                    data.pop('confirmed_offer', None)
                    self.store.update(jid, 'MONITORING' if now >= req.buy_after else 'SCHEDULED', data, interval)
                    return
                best = matches[0]
                if req.preferred_seats:
                    seat_map = await asyncio.wait_for(provider.preflight(req, best), timeout=self.config.website_provider_timeout)
                    eligible = {s['label'] for s in seat_map['seats'] if s['available'] and not s.get('female_only')}
                    missing = [label for label in req.preferred_seats if label not in eligible]
                    data['preferred_seats_status'] = 'unavailable' if missing else 'available'
                    data['missing_seats'] = missing
                    if missing:
                        self.alert(job, 'preferred_seats_unavailable', f'Your preferred seats {", ".join(missing)} are not currently eligible. ' + ('Alternative eligible seats may be used, as you requested.' if req.seat_fallback == 'any' else 'We will wait for your chosen seats; no alternatives will be selected.'), best.id)
                        if req.seat_fallback == 'wait':
                            data['message'] = 'Waiting for your exact seat choices: ' + ', '.join(missing) + '.'
                            data.pop('confirmed_offer', None)
                            self.store.update(jid, 'MONITORING' if now >= req.buy_after else 'SCHEDULED', data, interval)
                            return
                    else:
                        self.alert(job, 'preferred_seats_available', 'Your selected seats are currently available: ' + ', '.join(req.preferred_seats) + '. Availability can change until a reservation succeeds.', best.id)
                if utcnow() < req.buy_after:
                    data['message'] = 'Watching availability. Your booking window has not opened; no seats will be reserved.' if not req.monitor_only else 'Watching availability; this request will never reserve seats.'
                    self.store.update(jid, 'SCHEDULED', data, interval)
                    return
                if req.monitor_only:
                    data['message'] = f'{best.operator} at {best.departure}: {best.seats_available} seats listed. Watching only; no reservation will be placed.'
                    self.store.update(jid, 'MONITORING', data, interval)
                    self.alert(job, 'bus_available', f'{best.operator} at {best.departure} has {best.seats_available} seats listed. Fare from BDT {best.total(req)}.', best.id)
                    return
                identity = f'{best.id}:{best.unit_fare}'
                if data.get('confirmed_offer') != identity:
                    data.update({'confirmed_offer':identity, 'message':'A departure matches. Checking a second fresh observation before preparing.'})
                    self.store.update(jid, 'MONITORING', data, interval)
                    return
                if hasattr(provider, 'preflight') and not req.preferred_seats:
                    await asyncio.wait_for(provider.preflight(req, best), timeout=self.config.website_provider_timeout)
                deadline = min(req.buy_before, best.departure_at(req) - timedelta(minutes=self.config.website_departure_buffer_minutes))
                if utcnow() >= deadline:
                    await self.expire(job, data, 'The booking cutoff was reached during verification.')
                    return
                # Persist the uncertainty boundary BEFORE any operation that can hold seats.
                data.update({'message':'Selecting seats and preparing passenger details.', 'offer':best.model_dump(mode='json'), 'reservation_attempted':True})
                if not self.store.update(jid, 'PREPARING', data, expected=job['status']):
                    return
                preparing = True
                await self.checkpoint(jid)
                self.store.event(jid, 'preparing', f'Preparing {req.seat_count} seat(s) on {best.operator}.')
                prepared = await asyncio.wait_for(provider.prepare(req, best), timeout=min(self.config.website_provider_timeout, max(.1, (deadline - utcnow()).total_seconds())))
                data.update(prepared)
                self.store.update(jid, 'AWAITING_PAYMENT', data, interval)
                self.touch(jid)
                await self.checkpoint(jid)
                self.store.event(jid, 'payment_ready', data['message'])
                self.alert(job, 'payment_ready', f"Ready for your payment. Total: BDT {data['total']}. " + ('Expires: ' + data['expires_at'] if data.get('expires_at') else 'Check the provider for the exact payment deadline.'))
            except ProviderBusy:
                self.store.update(jid, job['status'], {**data,'message':'Waiting for browser capacity. Your request remains queued.'}, 10)
            except asyncio.CancelledError:
                if preparing:
                    self.attention(job, data, 'Server stopped during preparation. Reconcile with Shohoz before any new attempt.', recovery=True)
                    await self.checkpoint(jid)
                raise
            except Exception as exc:
                message = str(exc) if isinstance(exc, NeedsAttention) else 'Provider could not complete this step. Check the request activity or reconnect its session.'
                if preparing or isinstance(exc, NeedsAttention):
                    self.attention(job, data, message, recovery=preparing)
                    self.touch(jid)
                    await self.checkpoint(jid)
                else:
                    errors = previous_errors + 1
                    data.update({'errors':errors,'message':message})
                    if errors >= 3:
                        self.attention(job, data, message)
                    else:
                        self.store.update(jid, job['status'], data, interval * min(errors, 5))
            finally:
                current = self.store.job(jid)
                # Monitoring does not retain a Chrome process between observations.
                if current and current['status'] in MONITORED | {'EXPIRED','CANCELLED'}:
                    await self.release(jid, preserve=current['status'] in MONITORED)

    def attention(self, job, data, message, recovery=False):
        self.store.update(job['id'], 'NEEDS_ATTENTION', {**data,'message':message,'recovery_required':recovery or data.get('reservation_attempted',False)})
        self.store.event(job['id'], 'attention', message)
        self.alert(job, 'attention', message)

    async def expire(self, job, data, message):
        self.store.update(job['id'], 'EXPIRED', {**data,'message':message})
        self.store.event(job['id'], 'expired', message)
        self.alert(job, 'expired', message)
        await self.release(job['id'], preserve=False)

    async def inspect_payment(self, job, provider, interval):
        jid, data = job['id'], job['data']
        result = await asyncio.wait_for(provider.inspect(), timeout=30)
        # A later expired/login page cannot undo an already observed confirmation.
        if job['status'] == 'CONFIRMED' and not (result and result.get('confirmed')):
            return
        if result and result.get('confirmed'):
            if getattr(provider, 'ticket_bytes', None):
                self.save_ticket(jid, provider.ticket_bytes)
                result['ticket_available'] = True
            self.store.update(jid, 'CONFIRMED', {**data,**result,'message':'Shohoz confirmed your booking.','recovery_required':False})
            self.store.event(jid, 'confirmed', 'Provider confirmation received.')
            self.alert(job, 'confirmed', f"Your booking is confirmed. Reference: {result['reference']}.")
            await self.checkpoint(jid)
            self.touch(jid)
            return
        expiry = data.get('expires_at')
        seconds = (datetime.fromisoformat(expiry) - utcnow()).total_seconds() if expiry else None
        if (result and result.get('expired')) or (seconds is not None and seconds <= 0):
            # A deadline passing does not prove a payment failed. Keep a checkpoint for reconciliation.
            if job['mode'] == 'live':
                self.attention(job, data, 'The payment deadline passed. Reconnect and check with Shohoz before making another request.', recovery=True)
                await self.checkpoint(jid)
                self.touch(jid)
            else:
                await self.expire(job, data, 'The demo payment window expired.')
            self.alert(job, 'payment_expired', 'The payment deadline passed. Check the provider for any completed payment; no new booking was attempted.')
            return
        if seconds is not None and seconds <= 180:
            self.alert(job, 'payment_expiring', 'Your reservation expires in less than 3 minutes. Complete payment now.')
        if job['status'] == 'AWAITING_PAYMENT':
            self.store.update(jid, 'AWAITING_PAYMENT', data, min(interval, 15))

    async def reconnect(self, job):
        """Explicit user action: restore only and inspect; never prepare another booking."""
        jid = job['id']
        if job['mode'] != 'live':
            raise ValueError('Only live provider sessions can be reconnected')
        provider = self.providers.get(jid)
        if provider is None:
            state = self.vault.load(jid)
            if not state:
                raise NeedsAttention('No recoverable provider session remains. Check the booking directly with Shohoz.')
            provider = await self.get_provider(job, restore=False)
            try:
                await asyncio.wait_for(provider.restore_session(state, navigate=True), timeout=self.config.website_provider_timeout)
            except BaseException:
                await self.release(jid)
                raise
        self.touch(jid)
        await self.inspect_payment(job, provider, 10)
        current = self.store.job(jid)
        # An unconfirmed restored session must be reviewed manually, especially after partial preparation.
        if current['status'] != 'CONFIRMED':
            self.attention(job, current['data'], 'Provider session reopened. Review its current status; no reservation or payment was replayed.', recovery=bool(job['data'].get('reservation_attempted')))
        self.store.event(jid, 'reconnected', 'Saved provider session reopened for manual review.')

    def alert(self, job, kind, message, identity=''):
        path = f"/#/journeys?job={job['id']}" + ('&pay=1' if kind in {'payment_ready','payment_expiring'} else '')
        body = f"{job['request']['from_city']} to {job['request']['to_city']} on {job['request']['journey_date']}. {message} Open {self.config.website_public_url.rstrip('/')}{path}"
        self.store.alert(job, kind, body, identity)

    async def release(self, jid, preserve=True):
        if preserve:
            await self.checkpoint(jid)
        provider = self.providers.pop(jid, None)
        self.touched.pop(jid, None)
        if provider:
            await provider.close()
        if not preserve:
            self.vault.delete(jid)

    def save_ticket(self, jid, content):
        directory = self.config.website_database.parent / 'tickets'
        directory.mkdir(mode=0o700, exist_ok=True)
        path = directory / f'{jid}.pdf'
        path.write_bytes(content)
        path.chmod(0o600)

    async def close(self):
        self.stop_event.set()
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.tasks.clear()
        await asyncio.gather(*(self.release(jid) for jid in list(self.providers)), return_exceptions=True)
