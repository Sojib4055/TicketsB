import asyncio
import time
from datetime import timedelta
from decimal import Decimal

import pytest
from starlette.testclient import TestClient

from src.website.app import create_app
from src.website.config import WebSettings
from src.website.domain import BusOffer, BusSearch, NeedsAttention, utcnow
from src.website.search import BusSearchService


class PublicProvider:
    instances = []

    def __init__(self, config):
        self.closed = False
        self.map_calls = 0
        self.instances.append(self)

    async def search(self, query):
        return [BusOffer(id='real-departure', operator='Public Bus', route='Dhaka - Bogura',
                         departure='09:00 AM', unit_fare=Decimal('1200'), seats_available=8)]

    async def seat_map(self, offer_id):
        self.map_calls += 1
        return {'seats': [{'label':'A1', 'available':True, 'female_only':False, 'x':10, 'y':20}],
                'message':'Preference only; no seat is held.'}

    async def close(self):
        self.closed = True


@pytest.fixture
def config(tmp_path):
    return WebSettings(_env_file=None, website_database=tmp_path/'test.sqlite3')


def query(**changes):
    return dict(from_city='Dhaka', to_city='Bogura',
                journey_date=(utcnow()+timedelta(days=2)).date().isoformat(), **changes)


def test_public_search_in_demo_mode_uses_provider_and_maps(config):
    with TestClient(create_app(config, start_worker=False, search_factory=PublicProvider)) as client:
        response = client.post('/api/search', json=query(), headers={'X-Ticket-Request':'1'})
        assert response.status_code == 200
        result = response.json()
        assert result['source'] == 'shohoz' and not result['booking_enabled']
        assert result['offers'][0]['unit_fare'] == '1200'
        path = f"/api/search/{result['search_id']}/offers/real-departure/seats"
        assert client.get(path).json()['seats'][0]['label'] == 'A1'
        assert client.get(path).status_code == 200
        assert PublicProvider.instances[-1].map_calls == 1
        assert client.get(path.replace('real-departure', 'unknown')).status_code == 404
        assert client.get('/api/search/expired/offers/real-departure/seats').status_code == 410
    assert PublicProvider.instances[-1].closed


def test_search_failure_does_not_substitute_demo_fares(config):
    class Unavailable(PublicProvider):
        async def search(self, query):
            raise RuntimeError('provider failure')
    with TestClient(create_app(config, start_worker=False, search_factory=Unavailable)) as client:
        response = client.post('/api/search', json=query(), headers={'X-Ticket-Request':'1'})
        assert response.status_code == 502
        assert 'offers' not in response.json()
        assert PublicProvider.instances[-1].closed


def test_search_validation_prevents_provider_call(config):
    def unexpected(config):
        raise AssertionError('Invalid input must not open a browser')
    with TestClient(create_app(config, start_worker=False, search_factory=unexpected)) as client:
        assert client.post('/api/search', json=query()).status_code == 403
        for changes in ({'to_city':'dhaka'}, {'seat_count':5}, {'journey_date':'2020-01-01'}):
            payload = {**query(), **changes}
            assert client.post('/api/search', json=payload, headers={'X-Ticket-Request':'1'}).status_code == 400


def test_expired_search_releases_browser_and_cannot_load_map(config):
    async def run():
        service = BusSearchService(config, PublicProvider)
        result = await service.search(BusSearch.model_validate(query()))
        session = service.sessions[result['search_id']]
        session.expires = time.monotonic()-1
        with pytest.raises(NeedsAttention, match='expired'):
            await service.seats(result['search_id'], 'real-departure')
        assert session.provider.closed and not service.sessions
    asyncio.run(run())
