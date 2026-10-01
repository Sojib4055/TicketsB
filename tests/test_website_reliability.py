"""Failure-path tests use isolated storage and providers; no live reservations."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import time
import zipfile

import httpx
import pytest
from starlette.testclient import TestClient

from test_website import config, create_worker, post, register, request_payload
from src.website.app import create_app
from src.website.domain import BookingRequest, NeedsAttention, ProviderBusy, utcnow
from src.website.manage import restore
from src.website.operations import backup
from src.website.providers import DemoProvider
from src.website.runtime import BrowserBudget, SessionVault, WorkerLease
from src.website.store import Store
from src.website.whatsapp import WhatsApp


def test_idempotent_submission_is_atomic_and_scoped(config):
    store = Store(config.website_database)
    req = BookingRequest.model_validate(request_payload(request_key='same-submit'))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: store.create_job('owner', req, 'demo'), range(4)))
    assert len({job['id'] for job in results}) == 1
    assert len(store.jobs('owner')) == 1
    assert store.create_job('other', req, 'demo')['id'] != results[0]['id']
    changed = req.model_copy(update={'seat_preference':'front'})
    with pytest.raises(ValueError, match='different request'):
        store.create_job('owner', changed, 'demo')


def test_general_watch_uses_live_provider_even_in_demo_mode(config):
    with TestClient(create_app(config, start_worker=False)) as client:
        register(client)
        result = post(client, '/api/jobs', request_payload(monitor_only=True))
        assert result.status_code == 201
        assert result.json()['job']['mode'] == 'live'


def test_shortage_and_budget_alerts_do_not_disappear_when_offer_stops_matching(config):
    class Shortage(DemoProvider):
        async def search(self, request):
            offers = await super().search(request)
            offers[0].seats_available = 1
            return offers
        async def prepare(self, *_):
            pytest.fail('Insufficient seats must not be prepared')
    store, _, worker = create_worker(config, lambda *_: Shortage(config))
    req = BookingRequest.model_validate(request_payload(seat_count=2, max_total='1000',
        passengers=[{'first_name':'A','last_name':'B','gender':'male'}] * 2))
    job = store.create_job('owner', req, 'live')
    asyncio.run(worker.process(job))
    assert store.job(job['id'])['status'] == 'MONITORING'
    assert {a['kind'] for a in store.alerts('owner')} == {'low_seats','insufficient_seats','over_budget'}


@pytest.mark.parametrize('fallback,expected', [('wait','MONITORING'), ('any','AWAITING_PAYMENT')])
def test_exact_seat_wait_and_explicit_fallback(config, fallback, expected):
    calls = []
    class Seats(DemoProvider):
        async def seat_map(self, _):
            return {'seats':[{'label':'A1','available':False}, {'label':'A2','available':True}]}
        async def prepare(self, request, offer):
            calls.append(1)
            return {**await super().prepare(request, offer), 'seats':['A2']}
    store, _, worker = create_worker(config, lambda *_: Seats(config))
    req = BookingRequest.model_validate(request_payload(selected_offer_id='demo-morning', preferred_seats=['A1'], seat_fallback=fallback))
    job = store.create_job('owner', req, 'live')
    async def run():
        await worker.process(job)
        await worker.process(job)
        await worker.close()
    asyncio.run(run())
    result = store.job(job['id'])
    assert result['status'] == expected
    assert result['data']['missing_seats'] == ['A1']
    assert len(calls) == (1 if fallback == 'any' else 0)


def test_preparation_stops_if_window_expires_during_preflight(config, monkeypatch):
    calls = []
    now = utcnow()
    class SlowVerification(DemoProvider):
        async def preflight(self, request, offer):
            monkeypatch.setattr('src.website.worker.utcnow', lambda: now + timedelta(hours=2))
            return await super().preflight(request, offer)
        async def prepare(self, *_):
            calls.append(1)
    store, _, worker = create_worker(config, lambda *_: SlowVerification(config))
    job = store.create_job('owner', BookingRequest.model_validate(request_payload()), 'demo')
    async def run():
        await worker.process(job)
        await worker.process(job)
    asyncio.run(run())
    assert store.job(job['id'])['status'] == 'EXPIRED'
    assert not calls


def test_three_preflight_failures_stop_instead_of_retrying_forever(config):
    class BrokenMap(DemoProvider):
        async def preflight(self, *_):
            raise RuntimeError('Temporary unavailable seat map')
    store, _, worker = create_worker(config, lambda *_: BrokenMap(config))
    job = store.create_job('owner', BookingRequest.model_validate(request_payload(
        selected_offer_id='demo-morning', preferred_seats=['A1'])), 'live')
    async def run():
        for _ in range(3): await worker.process(job)
        await worker.close()
    asyncio.run(run())
    assert store.job(job['id'])['status'] == 'NEEDS_ATTENTION'
    assert store.job(job['id'])['data']['errors'] == 3


def test_capacity_wait_is_not_a_provider_failure(config):
    class Busy(DemoProvider):
        async def search(self, _):
            raise ProviderBusy('Busy')
    store, _, worker = create_worker(config, lambda *_: Busy(config))
    job = store.create_job('owner', BookingRequest.model_validate(request_payload()), 'live')
    asyncio.run(worker.process(job))
    result = store.job(job['id'])
    assert result['status'] == 'SCHEDULED'
    assert not result['data'].get('errors')
    budget = BrowserBudget(2)
    budget.acquire(); budget.acquire()
    with pytest.raises(ProviderBusy): budget.acquire()
    budget.release(); budget.acquire()
    assert budget.used == 2


def test_single_worker_lease(config):
    first, second = WorkerLease(config.website_database), WorkerLease(config.website_database)
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match='Another SeatWatch worker'): second.acquire()
    finally:
        first.close()
    second.acquire(); second.close()


def test_recovery_code_is_one_use_and_revokes_existing_sessions(config):
    app = create_app(config, start_worker=False)
    with TestClient(app) as client:
        uid = register(client).json()['user']['id']
        assert post(client, '/api/auth/recovery-code', {'password':'wrong-password'}).status_code == 400
        code = post(client, '/api/auth/recovery-code', {'password':'a-long-test-password'}).json()['code']
        with app.state.store.connect() as db:
            assert code not in db.execute('SELECT digest FROM recovery_codes WHERE user_id=?',(uid,)).fetchone()[0]
        body = {'email':'rider@example.com','code':code,'password':' new-test-password '}
        assert post(client, '/api/auth/recover', {**body, 'code':'x'*32}).status_code == 400
        assert post(client, '/api/auth/recover', body).status_code == 200
        assert client.get('/api/jobs').status_code == 401
        assert post(client, '/api/auth/recover', body).status_code == 400
        assert post(client, '/api/auth/login', {'email':body['email'],'password':body['password']}).status_code == 200


def test_uncertain_hold_cannot_resume_but_verification_can(config):
    app = create_app(config, start_worker=False)
    with TestClient(app) as client:
        register(client)
        job = post(client, '/api/jobs', request_payload(monitor_only=True)).json()['job']
        path = f"/api/jobs/{job['id']}"
        app.state.store.update(job['id'], 'NEEDS_ATTENTION', {'reservation_attempted':True})
        assert not client.get(path).json()['can_resume']
        assert post(client, path+'/action', {'action':'resume'}).status_code == 409
        app.state.store.update(job['id'], 'NEEDS_ATTENTION', {'message':'Sign in required'})
        assert client.get(path).json()['can_resume']
        assert post(client, path+'/action', {'action':'resume'}).status_code == 200


def saved_state():
    return {'url':'https://www.shohoz.com/bus-tickets/booking/bus/pay',
            'storage':{'cookies':[{'name':'test','value':'private-cookie'}], 'origins':[]}}


def test_session_checkpoint_is_encrypted_and_expires(config, monkeypatch):
    vault = SessionVault(config.website_database)
    jid = 'a'*32
    vault.save(jid, saved_state())
    assert b'private-cookie' not in vault.path(jid).read_bytes()
    assert vault.path(jid).stat().st_mode & 0o777 == 0o600
    assert vault.load(jid)['storage'] == saved_state()['storage']
    with pytest.raises(ValueError): vault.save(jid, {**saved_state(),'url':'https://example.com/pay'})
    original_time = time.time()
    monkeypatch.setattr('src.website.runtime.time.time', lambda: original_time + 86401)
    assert vault.load(jid) is None
    assert not vault.path(jid).exists()


def test_backup_restore_preserves_data_and_forces_reconciliation(config, tmp_path):
    store = Store(config.website_database)
    user = store.register('Rider', 'a@example.test', 'a-long-test-password')
    code = store.recovery_code(user['id'])
    job = store.create_job(user['id'], BookingRequest.model_validate(request_payload()), 'live')
    store.update(job['id'], 'AWAITING_PAYMENT', {'total':'650'})
    vault = SessionVault(config.website_database)
    vault.save(job['id'], saved_state())
    archive = backup(store)
    assert archive.stat().st_mode & 0o777 == 0o600
    destination = tmp_path / 'restored'
    restore(archive, destination)
    restored = Store(destination / 'tickets.sqlite3')
    assert restored.job(job['id'])['status'] == 'NEEDS_ATTENTION'
    assert restored.job(job['id'])['data']['reservation_attempted']
    assert SessionVault(destination / 'tickets.sqlite3').load(job['id'])['storage'] == saved_state()['storage']
    assert restored.reset_password('a@example.test', code, 'another-long-password')
    with pytest.raises(ValueError, match='new directory'): restore(archive, destination)
    with pytest.raises(FileExistsError): backup(store, archive)
    malicious = tmp_path / 'malicious.zip'
    with zipfile.ZipFile(malicious, 'w') as out: out.writestr('../outside', 'unsafe')
    with pytest.raises(ValueError): restore(malicious, tmp_path / 'rejected')
    assert not (tmp_path / 'outside').exists()


def test_reconnect_never_replays_preparation(config):
    calls = []
    class Restorable(DemoProvider):
        async def restore_session(self, state, navigate=False): calls.append(('restore',navigate))
        async def prepare(self, *_): pytest.fail('Restore must not prepare a reservation')
        async def inspect(self): return {'confirmed':True, 'reference':'FIXTURE-123'}
    store, _, worker = create_worker(config, lambda *_: Restorable(config))
    job = store.create_job('owner', BookingRequest.model_validate(request_payload()), 'live')
    store.update(job['id'], 'NEEDS_ATTENTION', {'reservation_attempted':True})
    worker.vault.save(job['id'], saved_state())
    async def run():
        await worker.reconnect(store.job(job['id']))
        await worker.close()
    asyncio.run(run())
    assert calls == [('restore',True)]
    assert store.job(job['id'])['status'] == 'CONFIRMED'


def test_expired_payment_alerts_are_not_delivered(config):
    store, whatsapp, _ = create_worker(config)
    job = store.create_job('owner', BookingRequest.model_validate(request_payload()), 'live')
    store.alert(job, 'payment_ready', 'Old payment notice')
    store.alert(job, 'low_seats', 'Old seat notice')
    with store.connect() as db:
        db.execute('UPDATE notifications SET created=?', (time.time()-901,))
    asyncio.run(whatsapp.dispatch())
    assert {a['status'] for a in store.alerts('owner')} == {'expired'}


def test_reconnecting_expired_session_does_not_erase_confirmed_ticket(config):
    class ExpiredSession(DemoProvider):
        async def restore_session(self, state, navigate=False): pass
        async def inspect(self): return {'expired':True}
    store, _, worker = create_worker(config, lambda *_: ExpiredSession(config))
    job = store.create_job('owner', BookingRequest.model_validate(request_payload()), 'live')
    store.update(job['id'], 'CONFIRMED', {'reference':'FIXTURE-123', 'ticket_available':True})
    worker.vault.save(job['id'], saved_state())
    async def run():
        await worker.reconnect(store.job(job['id']))
        await worker.close()
    asyncio.run(run())
    current = store.job(job['id'])
    assert current['status'] == 'CONFIRMED'
    assert current['data']['reference'] == 'FIXTURE-123'
    assert current['data']['ticket_available']


def test_concurrent_dispatch_claims_message_once(config):
    config.whatsapp_access_token = 'test'
    config.whatsapp_phone_number_id = '123'
    config.whatsapp_api_version = 'v23.0'
    store, _, _ = create_worker(config)
    job = store.create_job('owner', BookingRequest.model_validate(request_payload()), 'live')
    store.alert(job, 'low_seats', 'Only 2 seats')
    calls = []
    async def handler(request):
        calls.append(json.loads(request.content))
        await asyncio.sleep(.02)
        return httpx.Response(200, json={'messages':[{'id':'test-message'}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await asyncio.gather(WhatsApp(store, config, client).dispatch(), WhatsApp(store, config, client).dispatch())
    asyncio.run(run())
    assert len(calls) == 1
    assert store.alerts('owner')[0]['status'] == 'accepted'


def test_slow_search_does_not_block_other_jobs_or_notifications(config):
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        class Slow(DemoProvider):
            async def search(self, request):
                if request.to_city == 'Slow City':
                    started.set()
                    await release.wait()
                return await super().search(request)
        store, whatsapp, worker = create_worker(config, lambda *_: Slow(config))
        slow = store.create_job('owner', BookingRequest.model_validate(request_payload(to_city='Slow City', monitor_only=True)), 'live')
        fast = store.create_job('owner', BookingRequest.model_validate(request_payload(monitor_only=True)), 'live')
        store.alert(slow, 'attention', 'Queued before slow search')
        tasks = [asyncio.create_task(worker.run()), asyncio.create_task(whatsapp.run())]
        try:
            await asyncio.wait_for(started.wait(), 2)
            for _ in range(50):
                if store.job(fast['id'])['data'].get('last_checked') and any(a['status']=='setup_required' for a in store.alerts('owner')): break
                await asyncio.sleep(.02)
            assert store.job(fast['id'])['data'].get('last_checked')
            assert any(a['status']=='setup_required' for a in store.alerts('owner'))
            assert not release.is_set()
        finally:
            release.set()
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await worker.close()
    asyncio.run(run())
