import asyncio
import hashlib
import hmac
import re
import time

import httpx


class WhatsApp:
    def __init__(self, store, config, client=None):
        self.store, self.config = store, config
        self.client = client
        self.lock = asyncio.Lock()
        self.stop_event = asyncio.Event()

    async def run(self):
        with self.store.connect() as db:
            db.execute("UPDATE notifications SET status='unknown',error='Server stopped during delivery. Not resent automatically.' WHERE status='sending'")
        while not self.stop_event.is_set():
            self.store.heartbeat('notifications')
            try:
                await self.dispatch()
            except Exception:
                self.store.heartbeat('notifications', 'retrying after dispatch error')
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

    async def dispatch(self):
        async with self.lock:
            await self._dispatch()

    async def _dispatch(self):
        with self.store.connect() as db:
            rows = db.execute("SELECT * FROM notifications WHERE status IN ('queued','retrying','setup_required') AND next_attempt<=? ORDER BY created LIMIT 20", (time.time(),)).fetchall()
        for row in rows:
            self.store.heartbeat('notifications')
            job = self.store.job(row['job_id'])
            urgent = row['kind'] in {'payment_ready', 'payment_expiring'}
            transient = row['kind'] in {'low_seats','bus_available','preferred_seats_available','insufficient_seats'}
            stale = (urgent and (not job or job['status'] != 'AWAITING_PAYMENT')) or (transient and time.time() - row['created'] > 900)
            if urgent and job and job['data'].get('expires_at'):
                from datetime import datetime
                stale = stale or datetime.fromisoformat(job['data']['expires_at']).timestamp() <= time.time()
            if stale:
                self.mark(row['id'], 'expired', error='This time-sensitive update is no longer current and was not sent.')
                continue
            if not self.config.whatsapp_ready:
                self.mark(row['id'], 'setup_required', error='WhatsApp account configuration is required.', delay=60)
                continue
            if not re.fullmatch(r'v\d+\.\d+', self.config.whatsapp_api_version) or not self.config.whatsapp_phone_number_id.isdigit():
                self.mark(row['id'], 'failed', error='Invalid WhatsApp API version or phone number ID.')
                continue
            # Persist before sending. Unknown outcomes are not automatically replayed.
            with self.store.connect() as db:
                claimed = db.execute("UPDATE notifications SET status='sending' WHERE id=? AND status IN ('queued','retrying','setup_required')", (row['id'],)).rowcount
            if not claimed:
                continue
            payload = {'messaging_product': 'whatsapp', 'to': row['recipient'].lstrip('+'),
                       'type': 'template', 'template': {
                           'name': self.config.whatsapp_template_name,
                           'language': {'code': self.config.whatsapp_template_language},
                           'components': [{'type': 'body', 'parameters': [{'type': 'text', 'text': row['body']}]}]}}
            try:
                async with httpx.AsyncClient(timeout=15) as owned:
                    client = self.client or owned
                    response = await client.post(
                        f'https://graph.facebook.com/{self.config.whatsapp_api_version}/{self.config.whatsapp_phone_number_id}/messages',
                        headers={'Authorization': f'Bearer {self.config.whatsapp_access_token}'}, json=payload)
                if response.status_code == 429:
                    attempts = row['attempts'] + 1
                    self.mark(row['id'], 'retrying' if attempts < 4 else 'failed',
                              error='WhatsApp rate limit reached.', delay=min(60 * 2 ** attempts, 900), attempts=attempts)
                    continue
                response.raise_for_status()
                mid = response.json()['messages'][0]['id']
                self.mark(row['id'], 'accepted', message_id=mid)
            except httpx.HTTPStatusError as exc:
                self.mark(row['id'], 'failed', error=f'WhatsApp rejected this message (HTTP {exc.response.status_code}). Check the approved template and account settings.')
            except (httpx.HTTPError, ValueError, KeyError, IndexError):
                self.mark(row['id'], 'unknown', error='Delivery could not be confirmed. Not resent automatically to avoid duplicate messages.')

    def mark(self, nid, status, error=None, delay=0, attempts=None, message_id=None):
        with self.store.connect() as db:
            db.execute('UPDATE notifications SET status=?, error=?, next_attempt=?, attempts=COALESCE(?,attempts), message_id=COALESCE(?,message_id) WHERE id=?',
                       (status, error, time.time() + delay, attempts, message_id, nid))

    def verify_signature(self, body, signature):
        if not self.config.whatsapp_app_secret:
            return False
        expected = 'sha256=' + hmac.new(self.config.whatsapp_app_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def receipt(self, payload):
        order = {'sending': 0, 'unknown': 0, 'accepted': 1, 'sent': 2, 'delivered': 3, 'read': 4, 'failed': 5}
        with self.store.connect() as db:
            for entry in payload.get('entry', []):
                for change in entry.get('changes', []):
                    for status in change.get('value', {}).get('statuses', []):
                        new = status.get('status')
                        row = db.execute('SELECT id,status FROM notifications WHERE message_id=?', (status.get('id'),)).fetchone()
                        if row and new in order and order[new] > order.get(row['status'], 0):
                            db.execute('UPDATE notifications SET status=?,error=? WHERE id=?',
                                       (new, 'WhatsApp reported delivery failure.' if new == 'failed' else None, row['id']))
