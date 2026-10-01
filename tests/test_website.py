import asyncio
from datetime import timedelta
import hashlib
import hmac
import json
from decimal import Decimal

import httpx
import pytest
from starlette.testclient import TestClient

from src.website.app import create_app
from src.website.config import WebSettings
from src.website.domain import BookingRequest, BusOffer, NeedsAttention, utcnow
from src.website.providers import DemoProvider, ShohozProvider
from src.website.store import Store
from src.website.whatsapp import WhatsApp
from src.website.worker import BookingWorker


def request_payload(**changes):
    now = utcnow()
    result = dict(from_city='Dhaka', to_city='Bogura', journey_date=(now + timedelta(days=2)).date().isoformat(),
                  buy_after=(now - timedelta(minutes=1)).isoformat(), buy_before=(now + timedelta(hours=1)).isoformat(),
                  max_total='2000', seat_count=1, contact_phone='+8801712345678', contact_email='rider@example.com',
                  whatsapp_phone='+8801712345678', whatsapp_opt_in=True,
                  passengers=[{'first_name': 'Sample', 'last_name': 'Rider', 'gender': 'female'}])
    result.update(changes)
    return result


@pytest.fixture
def config(tmp_path):
    return WebSettings(_env_file=None, website_database=tmp_path / 'test.sqlite3')


def register(client, email='rider@example.com'):
    return client.post('/api/auth/register', json={'name':'Sample Rider', 'email':email, 'password':'a-long-test-password'}, headers={'X-Ticket-Request':'1'})


def post(client, path, body):
    return client.post(path, json=body, headers={'X-Ticket-Request':'1'})


def create_worker(config, factory=None):
    store = Store(config.website_database)
    whatsapp = WhatsApp(store, config)
    worker = BookingWorker(store, config, whatsapp, **({'factory':factory} if factory else {}))
    return store, whatsapp, worker


def test_accounts_and_booking_isolation(config):
    app = create_app(config, start_worker=False)
    with TestClient(app) as alice, TestClient(app) as bob:
        response = register(alice)
        assert response.status_code == 200
        assert 'httponly' in response.headers['set-cookie'].lower()
        assert register(bob, 'another@example.com').status_code == 200
        made = post(alice, '/api/jobs', request_payload())
        assert made.status_code == 201
        jid = made.json()['job']['id']
        assert len(alice.get('/api/jobs').json()['jobs']) == 1
        assert bob.get('/api/jobs').json()['jobs'] == []
        assert bob.get('/api/jobs/' + jid).status_code == 404
        assert post(bob, f'/api/jobs/{jid}/action', {'action':'cancel'}).status_code == 404
        assert bob.get(f'/api/jobs/{jid}/session').status_code == 404
        assert post(alice, '/api/auth/logout', {}).status_code == 200
        assert alice.get('/api/jobs').status_code == 401


def test_password_hash_and_csrf(config):
    with TestClient(create_app(config, start_worker=False)) as client:
        assert client.post('/api/auth/register', json={}).status_code == 403
        assert register(client).status_code == 200
        with client.app.state.store.connect() as db:
            stored = db.execute('SELECT password FROM users').fetchone()[0]
        assert 'a-long-test-password' not in stored
        assert post(client, '/api/auth/login', {'email':'rider@example.com', 'password':'wrong-long-password'}).status_code == 401
        assert post(client, '/api/auth/login', {'email':'rider@example.com', 'password':'a-long-test-password'}).status_code == 200
        assert 'frame-ancestors' in client.get('/').headers['content-security-policy']


@pytest.mark.parametrize('changes', [
    {'buy_before': (utcnow() - timedelta(hours=1)).isoformat()},
    {'seat_count':4}, {'max_total':'NaN'}, {'max_total':'-1'},
    {'contact_phone':'01712345678'}, {'from_city':'Dhaka','to_city':'dhaka'},
    {'whatsapp_phone':''}, {'buy_after':'bad date'},
])
def test_invalid_requests_are_rejected(config, changes):
    with TestClient(create_app(config, start_worker=False)) as client:
        register(client)
        assert post(client, '/api/jobs', request_payload(**changes)).status_code == 400


def test_budget_seats_and_departure_are_hard_constraints():
    passengers = [{'first_name':'A', 'last_name':'B', 'gender':'male'}] * 4
    request = BookingRequest.model_validate(request_payload(seat_count=4, passengers=passengers, max_total='1000'))
    offer = BusOffer(id='x',operator='Bus',route='Dhaka - Bogura',departure='08:30 AM',unit_fare=Decimal('500'),seats_available=10)
    assert offer.total(request) == 2000
    assert not offer.matches(request)
    request.max_total = Decimal('3000')
    offer.seats_available = 3
    assert not offer.matches(request)
    offer.seats_available = 4
    offer.currency = 'USD'
    assert not offer.matches(request)
    offer.currency = 'BDT'
    assert offer.matches(request)


def test_demo_complete_workflow_and_deduplicated_alerts(config):
    store, whatsapp, worker = create_worker(config)
    job = store.create_job('owner', BookingRequest.model_validate(request_payload()), 'demo')
    async def run():
        await worker.process(job)
        assert store.job(job['id'])['status'] == 'MONITORING'
        await worker.process(store.job(job['id']))
        ready = store.job(job['id'])
        assert ready['status'] == 'AWAITING_PAYMENT'
        assert ready['data']['total'] == '650'
        await worker.process(ready)
        alerts = store.alerts('owner')
        assert len([a for a in alerts if a['kind'] == 'low_seats']) == 1
        assert {a['status'] for a in alerts} == {'preview'}
        assert store.job(job['id'])['status'] != 'CONFIRMED'
        await whatsapp.dispatch()
        await worker.close()
    asyncio.run(run())


def test_future_window_monitors_but_does_not_reserve(config):
    store, _, worker = create_worker(config)
    req = BookingRequest.model_validate(request_payload(buy_after=(utcnow()+timedelta(minutes=10)).isoformat()))
    job = store.create_job('owner', req, 'demo')
    asyncio.run(worker.process(job))
    result = store.job(job['id'])
    assert result['status'] == 'SCHEDULED'
    assert result['data']['offers']
    assert not result['data'].get('seats')


def test_expired_window_never_opens_provider(config):
    def fail(*args): raise AssertionError('Provider must not be opened')
    store, _, worker = create_worker(config, fail)
    req = BookingRequest.model_validate(request_payload(buy_after=(utcnow()-timedelta(hours=2)).isoformat(), buy_before=(utcnow()-timedelta(hours=1)).isoformat()))
    job = store.create_job('owner', req, 'demo')
    asyncio.run(worker.process(job))
    assert store.job(job['id'])['status'] == 'EXPIRED'


def test_ambiguous_reservation_failure_is_not_repeated(config):
    class BrokenProvider(DemoProvider):
        calls = 0
        async def prepare(self, request, offer):
            self.calls += 1
            raise NeedsAttention('Provider verification required.')
    provider = BrokenProvider(config)
    store, _, worker = create_worker(config, lambda *_: provider)
    job = store.create_job('owner', BookingRequest.model_validate(request_payload()), 'demo')
    async def run():
        for _ in range(4):
            await worker.process(store.job(job['id']))
    asyncio.run(run())
    assert store.job(job['id'])['status'] == 'NEEDS_ATTENTION'
    assert provider.calls == 1


def test_restart_does_not_repeat_preparation(config):
    store, _, _ = create_worker(config)
    job = store.create_job('owner', BookingRequest.model_validate(request_payload()), 'live')
    store.update(job['id'], 'PREPARING', {})
    store.recover()
    assert store.job(job['id'])['status'] == 'NEEDS_ATTENTION'


def test_pause_resume_cancel_and_demo_payment(config):
    with TestClient(create_app(config, start_worker=False)) as client:
        register(client)
        job = post(client, '/api/jobs', request_payload()).json()['job']
        path = f"/api/jobs/{job['id']}/action"
        assert post(client, path, {'action':'pause'}).json()['job']['status'] == 'PAUSED'
        assert post(client, path, {'action':'resume'}).json()['job']['status'] == 'SCHEDULED'
        worker = client.app.state.worker
        asyncio.run(worker.process(job)); asyncio.run(worker.process(job))
        assert post(client, path, {'action':'demo_pay'}).json()['job']['status'] == 'CONFIRMED'
        assert post(client, path, {'action':'demo_pay'}).status_code == 409


def test_live_cannot_claim_payment_by_api(config):
    config.booking_mode = 'live'
    with TestClient(create_app(config, start_worker=False)) as client:
        register(client)
        job = post(client, '/api/jobs', request_payload()).json()['job']
        client.app.state.store.update(job['id'], 'AWAITING_PAYMENT', {})
        assert post(client, f"/api/jobs/{job['id']}/action", {'action':'demo_pay'}).status_code == 409


def test_missing_whatsapp_credentials_are_visible(config):
    store, whatsapp, _ = create_worker(config)
    job = store.create_job('owner', BookingRequest.model_validate(request_payload()), 'live')
    store.alert(job, 'low_seats', 'Only 3 seats remain.')
    asyncio.run(whatsapp.dispatch())
    assert store.alerts('owner')[0]['status'] == 'setup_required'


def test_whatsapp_template_and_signed_delivery_receipts(config):
    config.whatsapp_access_token = 'test-token'
    config.whatsapp_phone_number_id = '12345'
    config.whatsapp_api_version = 'v23.0'
    config.whatsapp_app_secret = 'test-secret'
    config.whatsapp_verify_token = 'verify-secret'
    app = create_app(config, start_worker=False)
    store = app.state.store
    job = store.create_job('owner', BookingRequest.model_validate(request_payload()), 'live')
    store.alert(job, 'low_seats', 'Only 3 seats remain.')
    async def run():
        def handle(request):
            body = json.loads(request.content)
            assert body['type'] == 'template'
            assert body['to'] == '8801712345678'
            assert body['template']['components'][0]['parameters'][0]['text'] == 'Only 3 seats remain.'
            return httpx.Response(200, json={'messages':[{'id':'wamid.test'}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            await WhatsApp(store, config, client).dispatch()
    asyncio.run(run())
    assert store.alerts('owner')[0]['status'] == 'accepted'
    with TestClient(app) as client:
        assert client.get('/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=verify-secret&hub.challenge=abc').text == 'abc'
        payload = {'entry':[{'changes':[{'value':{'statuses':[{'id':'wamid.test','status':'delivered'}]}}]}]}
        body = json.dumps(payload).encode()
        assert client.post('/webhooks/whatsapp', content=body).status_code == 403
        signature = 'sha256=' + hmac.new(b'test-secret', body, hashlib.sha256).hexdigest()
        assert client.post('/webhooks/whatsapp', content=body, headers={'x-hub-signature-256':signature}).status_code == 200
        assert store.alerts('owner')[0]['status'] == 'delivered'


def test_unknown_final_total_requires_review():
    assert ShohozProvider.review_total('Fare 650\nConvenience fee unknown') is None
    assert ShohozProvider.review_total('Total payable\nBDT 1,340.00') == Decimal('1340')


def test_ticket_download_is_owned_and_requires_provider_confirmation(config):
    config.booking_mode = 'live'
    app = create_app(config, start_worker=False)
    with TestClient(app) as owner, TestClient(app) as outsider:
        register(owner)
        register(outsider, 'outsider@example.com')
        job = post(owner, '/api/jobs', request_payload()).json()['job']
        path = f"/api/jobs/{job['id']}/ticket"
        assert owner.get(path).status_code == 404
        app.state.worker.save_ticket(job['id'], b'%PDF-1.4\nTest provider document')
        assert owner.get(path).status_code == 404
        app.state.store.update(job['id'], 'CONFIRMED', {'ticket_available':True})
        assert outsider.get(path).status_code == 404
        result = owner.get(path)
        assert result.status_code == 200
        assert result.headers['content-type'] == 'application/pdf'


def test_payment_expiry_alert_is_deduplicated(config):
    store, _, worker = create_worker(config)
    job = store.create_job('owner', BookingRequest.model_validate(request_payload()), 'demo')
    store.update(job['id'], 'AWAITING_PAYMENT', {'expires_at':(utcnow()+timedelta(seconds=90)).isoformat()})
    async def run():
        await worker.process(job)
        await worker.process(job)
    asyncio.run(run())
    assert len([a for a in store.alerts('owner') if a['kind']=='payment_expiring']) == 1


def test_selected_live_bus_cannot_silently_become_demo_booking(config):
    with TestClient(create_app(config, start_worker=False)) as client:
        register(client)
        payload = request_payload(selected_offer_id='real-provider-trip')
        assert post(client, '/api/jobs', payload).status_code == 400
        result = post(client, '/api/jobs', {**payload, 'monitor_only':True})
        assert result.status_code == 201
        assert result.json()['job']['mode'] == 'live'


def test_watch_only_never_prepares_and_matches_exact_departure(config):
    class WatchProvider(DemoProvider):
        async def prepare(self, request, offer):
            raise AssertionError('A watch must never reserve seats')
    store, _, worker = create_worker(config, lambda *_: WatchProvider(config))
    async def run():
        for selected in ('another-trip', 'demo-morning'):
            req = BookingRequest.model_validate(request_payload(selected_offer_id=selected, monitor_only=True))
            job = store.create_job('owner', req, 'live')
            for _ in range(3):
                await worker.process(store.job(job['id']))
            result = store.job(job['id'])
            assert result['status'] == 'MONITORING'
            assert bool(result['data']['offers']) == (selected == 'demo-morning')
            assert not result['data'].get('seats')
        await worker.close()
    asyncio.run(run())


def test_react_build_is_served_with_private_api_and_immutable_bundles(config):
    import re
    with TestClient(create_app(config, start_worker=False)) as client:
        response = client.get('/')
        assert response.status_code == 200
        assert '<div id="root"></div>' in response.text
        bundles = re.findall(r'(?:src|href)="(/bundles/[^\"]+)"', response.text)
        assert bundles
        for bundle in bundles:
            asset = client.get(bundle)
            assert asset.status_code == 200
            assert 'immutable' in asset.headers['cache-control']
        assert client.get('/api/auth/me').headers['cache-control'] == 'no-store'
        assert client.get('/favicon.svg').status_code == 200
        assert "'unsafe-inline'" not in response.headers['content-security-policy']
