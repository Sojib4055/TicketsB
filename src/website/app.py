import asyncio
from contextlib import asynccontextmanager
import hmac
import json
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlparse

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from src.website.config import WebSettings, web_settings
from src.website.domain import BookingRequest, BusSearch, MONITORED, NeedsAttention, ProviderBusy, utcnow
from src.website.runtime import BrowserBudget, WorkerLease
from src.website.operations import backup_loop
from src.website.search import BusSearchService
from src.website.store import Store
from src.website.whatsapp import WhatsApp
from src.website.worker import BookingWorker

STATIC = Path(__file__).with_name('static')
FRONTEND = STATIC / 'react'
COOKIE = 'ticket_session'


def create_app(config: WebSettings | None = None, *, start_worker=True, provider_factory=None, search_factory=None):
    config = config or web_settings
    config._browser_budget = BrowserBudget(config.website_browser_limit)
    store = Store(config.website_database)
    whatsapp = WhatsApp(store, config)
    worker = BookingWorker(store, config, whatsapp, **({'factory': provider_factory} if provider_factory else {}))
    search_service = BusSearchService(config, **({'factory': search_factory} if search_factory else {}))

    @asynccontextmanager
    async def lifespan(app):
        lease = WorkerLease(config.website_database)
        if start_worker:
            lease.acquire()
        tasks = [asyncio.create_task(search_service.sweep())]
        if start_worker:
            tasks += [asyncio.create_task(worker.run()), asyncio.create_task(whatsapp.run()),
                      asyncio.create_task(backup_loop(store, config))]
        try:
            yield
        finally:
            worker.stop_event.set()
            whatsapp.stop_event.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            try:
                await worker.close()
                await search_service.close()
            finally:
                lease.close()

    def user(request):
        result = store.session_user(request.cookies.get(COOKIE, ''))
        if not result:
            raise HTTPException(401, 'Please sign in.')
        return result

    def owned(request):
        result = store.job(request.path_params['jid'], user(request)['id'])
        if not result:
            raise HTTPException(404, 'Booking request not found.')
        return result

    async def payload(request):
        if 'application/json' not in request.headers.get('content-type', ''):
            raise HTTPException(415, 'Send JSON data.')
        try:
            value = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(400, 'Invalid JSON data.')
        if not isinstance(value, dict):
            raise HTTPException(400, 'Expected a JSON object.')
        return value

    def session_response(account):
        response = JSONResponse({'user': account})
        response.set_cookie(COOKIE, store.create_session(account['id']), max_age=7 * 86400,
                            httponly=True, secure=config.website_secure_cookies, samesite='strict')
        return response

    async def home(request):
        return FileResponse(FRONTEND / 'index.html' if (FRONTEND / 'index.html').is_file() else STATIC / 'index.html')

    async def favicon(request):
        return FileResponse(FRONTEND / 'favicon.svg' if (FRONTEND / 'favicon.svg').is_file() else STATIC / 'mark.svg')

    async def status(request):
        return JSONResponse({'mode': config.booking_mode, 'timezone': 'Asia/Dhaka',
                             'departure_buffer_minutes':config.website_departure_buffer_minutes,
                             'whatsapp_configured': config.whatsapp_ready,
                             'provider': 'Shohoz', 'payment': 'manual', 'search_source': 'live',
                             'live_validation': 'required' if config.booking_mode == 'demo' else 'operator_managed'})

    async def health(request):
        try:
            runtime = store.metrics()['runtime']
            checks = {name: (not start_worker or time.time() - runtime.get(name, {}).get('heartbeat', 0) < 120)
                      for name in ('worker','notifications')}
            ok = all(checks.values())
            return JSONResponse({'status':'ok' if ok else 'degraded', 'database':True, **checks}, status_code=200 if ok else 503)
        except sqlite3.Error:
            return JSONResponse({'status':'degraded','database':False}, status_code=503)

    async def me(request):
        return JSONResponse({'user': store.session_user(request.cookies.get(COOKIE, ''))})

    async def auth(request):
        key = (request.client.host if request.client else 'unknown') + ':' + request.url.path
        if not store.throttle(key):
            raise HTTPException(429, 'Too many attempts. Try again in 15 minutes.')
        data = await payload(request)
        email = str(data.get('email', '')).strip().lower()
        password = str(data.get('password', ''))
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or len(email) > 120 or not 12 <= len(password) <= 200:
            raise HTTPException(400, 'Use a valid email and a password of 12–200 characters.')
        if request.url.path.endswith('/register'):
            name = str(data.get('name', '')).strip()
            if not 1 <= len(name) <= 80:
                raise HTTPException(400, 'Enter your name (up to 80 characters).')
            try:
                account = await asyncio.to_thread(store.register, name, email, password)
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'An account already exists for this email. Sign in instead.')
        else:
            account = await asyncio.to_thread(store.authenticate, email, password)
            if not account:
                raise HTTPException(401, 'The email or password is incorrect.')
        return session_response(account)

    async def logout(request):
        store.logout(request.cookies.get(COOKIE, ''))
        response = JSONResponse({'ok': True})
        response.delete_cookie(COOKIE)
        return response

    async def recovery_code(request):
        account = user(request)
        key = 'recovery-code:' + account['id']
        if not store.throttle(key):
            raise HTTPException(429, 'Too many attempts. Try again in 15 minutes.')
        body = await payload(request)
        password = str(body.get('password', ''))
        if not 12 <= len(password) <= 200 or not await asyncio.to_thread(store.authenticate, account['email'], password):
            raise HTTPException(400, 'Your current password is incorrect.')
        return JSONResponse({'code':store.recovery_code(account['id']),
                             'message':'Save this code offline. It replaces your previous code and can be used once to reset your password.'})

    async def recover_account(request):
        key = 'account-reset:' + (request.client.host if request.client else 'unknown')
        if not store.throttle(key):
            raise HTTPException(429, 'Too many attempts. Try again in 15 minutes.')
        body = await payload(request)
        email, code = (str(body.get(key, '')).strip() for key in ('email','code'))
        password = str(body.get('password', ''))
        if not 12 <= len(password) <= 200 or not 20 <= len(code) <= 100 or len(email) > 120:
            raise HTTPException(400, 'Use your email, saved recovery code, and a new password of 12–200 characters.')
        if not await asyncio.to_thread(store.reset_password, email.lower(), code, password):
            raise HTTPException(400, 'The recovery details are invalid or the code was already used.')
        return JSONResponse({'ok':True,'message':'Password reset. All previous sessions are signed out. Sign in and generate a new recovery code.'})

    async def jobs(request):
        account = user(request)
        if request.method == 'GET':
            return JSONResponse({'jobs': store.jobs(account['id']), 'alerts': store.alerts(account['id'])})
        raw = await payload(request)
        try:
            booking = BookingRequest.model_validate(raw)
            booking.validate_new()
            if booking.departure_start == booking.departure_end:
                from datetime import datetime, timedelta
                from src.website.domain import DHAKA
                cutoff = datetime.combine(booking.journey_date, booking.departure_start, DHAKA) - timedelta(minutes=config.website_departure_buffer_minutes)
                if booking.buy_before > cutoff:
                    raise ValueError(f'End your window at least {config.website_departure_buffer_minutes} minutes before departure.')
            if booking.selected_offer_id and config.booking_mode != 'live' and not booking.monitor_only:
                raise ValueError('Live reservations are not enabled. You can watch this bus and receive availability alerts.')
            mode = 'live' if booking.monitor_only or booking.selected_offer_id else config.booking_mode
            result = store.create_job(account['id'], booking, mode)
        except ValidationError as exc:
            message = '; '.join('.'.join(str(p) for p in e['loc']) + ': ' + e['msg'] for e in exc.errors(include_input=False, include_url=False))
            raise HTTPException(400, message)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return JSONResponse({'job': result}, status_code=201)

    async def search_buses(request):
        key = 'bus-search:' + (request.client.host if request.client else 'unknown')
        if not store.throttle(key):
            raise HTTPException(429, 'Too many searches. Please wait a few minutes before searching again.')
        try:
            query = BusSearch.model_validate(await payload(request))
        except ValidationError as exc:
            raise HTTPException(400, '; '.join(e['msg'] for e in exc.errors(include_input=False, include_url=False)))
        try:
            return JSONResponse(await search_service.search(query))
        except NeedsAttention as exc:
            raise HTTPException(503, str(exc))
        except ProviderBusy as exc:
            raise HTTPException(503, str(exc))
        except Exception:
            raise HTTPException(502, 'Shohoz could not return live buses right now. Please try again. No sample fares have been substituted.')

    async def search_seats(request):
        try:
            return JSONResponse(await search_service.seats(request.path_params['sid'], request.path_params['oid']))
        except NeedsAttention as exc:
            raise HTTPException(410, str(exc))
        except ValueError as exc:
            raise HTTPException(404, str(exc))
        except Exception:
            raise HTTPException(502, 'The provider seat map could not be loaded. Refresh the search and try again.')

    async def job_detail(request):
        job = owned(request)
        recoverable = job['mode'] == 'live' and worker.vault.path(job['id']).is_file()
        return JSONResponse({'job': job, 'events': store.events(job['id']),
                             'session_available': job['id'] in worker.providers and job['mode'] == 'live' and job['status'] not in MONITORED,
                             'session_recoverable':recoverable,
                             'can_resume':job['status'] in {'PAUSED','NEEDS_ATTENTION'} and not (job['data'].get('reservation_attempted') or job['data'].get('offer'))})

    async def action(request):
        job = owned(request)
        data = await payload(request)
        jid = job['id']
        if worker.lock(jid).locked():
            raise HTTPException(409, 'A provider operation is in progress. Try again after it finishes.')
        async with worker.lock(jid):
            job = store.job(jid, job['user_id'])
            kind, state = data.get('action'), job['status']
            if kind == 'pause' and state in MONITORED:
                store.update(jid, 'PAUSED', {**job['data'], 'message': 'Monitoring paused.'})
                await worker.release(jid)
            elif kind == 'resume' and state in {'PAUSED','NEEDS_ATTENTION'}:
                if job['data'].get('reservation_attempted') or job['data'].get('offer'):
                    raise HTTPException(409, 'A reservation may already exist. Reconnect and reconcile with Shohoz; automatic preparation cannot be repeated.')
                BookingRequest.model_validate(job['request']).validate_new()
                updated = {**job['data'], 'message': 'Monitoring resumed.', 'errors': 0}
                updated.pop('confirmed_offer', None)
                updated['recovery_required'] = False
                store.update(jid, 'SCHEDULED', updated)
                await worker.release(jid)
            elif kind == 'reconnect' and state in {'NEEDS_ATTENTION','AWAITING_PAYMENT','CONFIRMED'}:
                await worker.reconnect(job)
            elif kind == 'cancel' and state in MONITORED | {'PAUSED'}:
                store.update(jid, 'CANCELLED', {**job['data'], 'message': 'Booking request cancelled.'})
                await worker.release(jid, preserve=False)
            elif kind == 'demo_pay' and job['mode'] == 'demo' and state == 'AWAITING_PAYMENT':
                expiry = job['data'].get('expires_at')
                from datetime import datetime
                if expiry and datetime.fromisoformat(expiry) <= utcnow():
                    raise HTTPException(409, 'The demo payment window expired.')
                updated = {**job['data'], 'reference': 'DEMO-' + jid[:8].upper(),
                           'message': 'Demo completed. This is a simulation, not a valid ticket.'}
                store.update(jid, 'CONFIRMED', updated)
                worker.alert(job, 'confirmed', 'Demo payment completed. No real ticket was purchased.')
                await worker.release(jid)
            elif kind == 'close' and state in {'NEEDS_ATTENTION', 'AWAITING_PAYMENT', 'CONFIRMED'}:
                # Closing our session does not claim to cancel a provider hold or payment.
                if state != 'CONFIRMED':
                    store.update(jid, 'CANCELLED', {**job['data'], 'message': 'Request closed. This does not cancel any Shohoz reservation; verify its status with Shohoz.'})
                await worker.release(jid, preserve=False)
            else:
                raise HTTPException(409, 'This action is not available in the current booking state.')
            store.event(jid, kind, f'Request action: {kind.replace("_", " ")}.')
        return JSONResponse({'job': store.job(jid, job['user_id'])})

    async def browser(request):
        job = owned(request)
        if job['status'] not in {'NEEDS_ATTENTION', 'AWAITING_PAYMENT', 'CONFIRMED'}:
            raise HTTPException(409, 'The provider session is not ready for manual use.')
        provider = worker.providers.get(job['id'])
        if job['mode'] != 'live' or provider is None:
            raise HTTPException(409, 'No live provider session is available.')
        async with worker.lock(job['id']):
            job = store.job(job['id'], job['user_id'])
            provider = worker.providers.get(job['id'])
            if job['status'] not in {'NEEDS_ATTENTION','AWAITING_PAYMENT','CONFIRMED'} or provider is None:
                raise HTTPException(409, 'The provider session changed. Refresh the journey before continuing.')
            worker.touch(job['id'])
            if request.method == 'POST':
                gesture = await payload(request)
                # Manual interaction outside the login form may have selected a seat,
                # even if the network response is lost. Never automatically replay it.
                if not job['data'].get('reservation_attempted'):
                    verification_only = hasattr(provider, 'verification_gesture') and await provider.verification_gesture(gesture)
                    if not verification_only:
                        store.update(job['id'], job['status'], {**job['data'], 'reservation_attempted':True})
                        job = store.job(job['id'], job['user_id'])
                await provider.manual_action(gesture)
                await worker.checkpoint(job['id'])
                result = await provider.inspect()
                if result and result.get('confirmed'):
                    if getattr(provider, 'ticket_bytes', None):
                        worker.save_ticket(job['id'], provider.ticket_bytes)
                        result['ticket_available'] = True
                    store.update(job['id'], 'CONFIRMED', {**job['data'], **result, 'message': 'Shohoz confirmed your booking.', 'recovery_required':False})
                    store.event(job['id'], 'confirmed', 'Provider confirmation received.')
                    worker.alert(job, 'confirmed', f"Your booking is confirmed. Reference: {result['reference']}.")
                return JSONResponse({'ok': True})
            return Response(await provider.screenshot(), media_type='image/png')

    async def ticket(request):
        job = owned(request)
        path = config.website_database.parent / 'tickets' / f"{job['id']}.pdf"
        if job['status'] != 'CONFIRMED' or job['mode'] != 'live' or not job['data'].get('ticket_available') or not path.is_file():
            raise HTTPException(404, 'The provider has not supplied a downloadable ticket yet.')
        return FileResponse(path, media_type='application/pdf', filename='Shohoz-ticket.pdf')

    async def webhook(request):
        if request.method == 'GET':
            query = request.query_params
            if config.whatsapp_verify_token and query.get('hub.mode') == 'subscribe' and hmac.compare_digest(query.get('hub.verify_token', ''), config.whatsapp_verify_token):
                return PlainTextResponse(query.get('hub.challenge', ''))
            raise HTTPException(403, 'Verification failed.')
        body = await request.body()
        if not whatsapp.verify_signature(body, request.headers.get('x-hub-signature-256', '')):
            raise HTTPException(403, 'Invalid webhook signature.')
        try:
            whatsapp.receipt(json.loads(body))
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(400, 'Invalid webhook payload.')
        return JSONResponse({'ok': True})

    async def errors(request, exc):
        if isinstance(exc, ProviderBusy):
            return JSONResponse({'error':str(exc)}, status_code=503)
        if isinstance(exc, HTTPException):
            return JSONResponse({'error': exc.detail}, status_code=exc.status_code)
        if isinstance(exc, (ValueError, NeedsAttention)):
            return JSONResponse({'error': str(exc)}, status_code=400)
        return JSONResponse({'error': 'The request could not be completed. Please try again.'}, status_code=500)

    app = Starlette(lifespan=lifespan, routes=[
        Route('/', home), Route('/favicon.svg', favicon), Route('/api/status', status), Route('/api/health', health), Route('/api/auth/me', me),
        Route('/api/search', search_buses, methods=['POST']),
        Route('/api/search/{sid}/offers/{oid}/seats', search_seats),
        Route('/api/auth/register', auth, methods=['POST']), Route('/api/auth/login', auth, methods=['POST']),
        Route('/api/auth/recovery-code', recovery_code, methods=['POST']), Route('/api/auth/recover', recover_account, methods=['POST']),
        Route('/api/auth/logout', logout, methods=['POST']), Route('/api/jobs', jobs, methods=['GET', 'POST']),
        Route('/api/jobs/{jid}', job_detail), Route('/api/jobs/{jid}/action', action, methods=['POST']),
        Route('/api/jobs/{jid}/ticket', ticket),
        Route('/api/jobs/{jid}/session', browser, methods=['GET', 'POST']),
        Route('/webhooks/whatsapp', webhook, methods=['GET', 'POST']),
        Mount('/bundles', app=StaticFiles(directory=FRONTEND / 'bundles', check_dir=False), name='frontend'),
        Mount('/assets', app=StaticFiles(directory=STATIC), name='assets')],
        exception_handlers={HTTPException: errors, ValueError: errors, NeedsAttention: errors, ProviderBusy: errors, Exception: errors})
    app.state.store, app.state.worker, app.state.config = store, worker, config
    app.state.search = search_service
    app.add_middleware(WebsiteSecurity)
    host = urlparse(config.website_public_url).hostname
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list({host, '127.0.0.1', 'localhost', 'testserver'} - {None}))
    return app


class WebsiteSecurity(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method in {'POST', 'PUT', 'DELETE', 'PATCH'}:
            if request.url.path != '/webhooks/whatsapp' and request.headers.get('x-ticket-request') != '1':
                return JSONResponse({'error': 'Missing request verification header.'}, status_code=403)
            content_length = request.headers.get('content-length', '0')
            if not content_length.isdigit() or int(content_length) > 65536:
                return JSONResponse({'error': 'Request is too large.'}, status_code=413)
            body = await request.body()
            if len(body) > 65536:
                return JSONResponse({'error': 'Request is too large.'}, status_code=413)
        response = await call_next(request)
        # Vite bundles have content hashes. Account and booking responses stay private.
        response.headers['Cache-Control'] = ('public, max-age=31536000, immutable'
            if request.url.path.startswith('/bundles/') and response.status_code == 200 else 'no-store')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response


def main():
    import uvicorn
    uvicorn.run(create_app(), host=web_settings.website_host, port=web_settings.website_port, access_log=False)


if __name__ == '__main__':
    main()
