"""Public, read-only bus search. Live search is independent of booking demo mode."""
import asyncio
import secrets
import time
from dataclasses import dataclass, field

from src.website.domain import BusSearch, NeedsAttention, utcnow
from src.website.providers import ShohozProvider


@dataclass
class SearchSession:
    query: BusSearch
    provider: object
    offers: list
    expires: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    seat_maps: dict = field(default_factory=dict)


class BusSearchService:
    def __init__(self, config, factory=ShohozProvider):
        self.config, self.factory = config, factory
        self.sessions = {}
        self.capacity = asyncio.Semaphore(2)
        self.registry_lock = asyncio.Lock()
        self.pending = 0

    async def cleanup(self):
        now = time.monotonic()
        for key, session in list(self.sessions.items()):
            if session.expires < now and not session.lock.locked():
                self.sessions.pop(key, None)
                await session.provider.close()

    async def search(self, query):
        async with self.capacity:
            await self.cleanup()
            async with self.registry_lock:
                if len(self.sessions) + self.pending >= 2:
                    for key, old in list(self.sessions.items()):
                        if not old.lock.locked():
                            self.sessions.pop(key, None)
                            await old.provider.close()
                            break
                    else:
                        raise NeedsAttention('Search is busy. Please try again shortly.')
                self.pending += 1
            provider = None
            try:
                provider = self.factory(self.config)
                offers = await asyncio.wait_for(provider.search(query), timeout=65)
            except BaseException:
                if provider:
                    await provider.close()
                raise
            finally:
                self.pending -= 1
            key = secrets.token_urlsafe(24)
            self.sessions[key] = SearchSession(query, provider, offers, time.monotonic() + 300)
            return {'search_id': key, 'query': query.model_dump(mode='json'),
                    'offers': [offer.model_dump(mode='json') for offer in offers],
                    'source': 'shohoz', 'checked_at': utcnow().isoformat(),
                    'expires_in': 300, 'booking_enabled': self.config.booking_mode == 'live'}

    async def seats(self, key, offer_id):
        await self.cleanup()
        session = self.sessions.get(key)
        if session is None:
            raise NeedsAttention('These search results have expired. Search again for fresh availability.')
        if not any(offer.id == offer_id for offer in session.offers):
            raise ValueError('Departure not found in this search')
        async with session.lock:
            cached = session.seat_maps.get(offer_id)
            if not cached or cached['valid_until'] < time.monotonic():
                result = await asyncio.wait_for(session.provider.seat_map(offer_id), timeout=35)
                session.seat_maps[offer_id] = {'result': result, 'valid_until': time.monotonic() + 30, 'checked_at': utcnow().isoformat()}
            cached = session.seat_maps[offer_id]
            return {**cached['result'], 'offer_id': offer_id, 'source': 'shohoz', 'checked_at': cached['checked_at']}

    async def sweep(self):
        while True:
            await asyncio.sleep(15)
            await self.cleanup()

    async def close(self):
        await asyncio.gather(*(session.provider.close() for session in self.sessions.values()), return_exceptions=True)
        self.sessions.clear()
