"""Production React smoke test with explicit local fixtures; no provider traffic.

python scripts/react_smoke.py
Starts an isolated server on 8769 and deletes its temporary database afterwards.
"""
import asyncio
from datetime import datetime
import os
from pathlib import Path
import secrets
import sys
import tempfile
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.async_api import async_playwright
from src.website.app import create_app
from src.website.config import WebSettings
from src.website.domain import BusOffer, NeedsAttention
from src.website.providers import DemoProvider


class FixtureProvider:
    def __init__(self, config):
        pass

    async def search(self, request):
        if request.to_city == 'Unavailable':
            raise RuntimeError('Fixture provider is unavailable')
        return [BusOffer(id='fixture-trip', operator='Test Express', route='Dhaka - Bogura',
                         departure='09:00 AM', arrival='03:00 PM', unit_fare='1200',
                         seats_available=8, service_class='AC', duration='6h 0m',
                         boarding_points=['Gabtoli'], dropping_points=['Bogura']),
                BusOffer(id='fixture-second', operator='Other Bus', route='Dhaka - Bogura',
                         departure='09:00 PM', arrival='03:00 AM', unit_fare='650',
                         seats_available=3, service_class='Non AC', duration='6h 0m',
                         boarding_points=['Kalyanpur']),
                BusOffer(id='fixture-notice', operator='Notice Bus', route='Dhaka - Bogura',
                         departure='10:00 PM', arrival='04:00 AM', unit_fare='750',
                         seats_available=10, service_class='Non AC', duration='6h 0m',
                         provider_note='Dear traveler, check the boarding details on Shohoz.')]

    async def seat_map(self, offer_id):
        if offer_id == 'fixture-second':
            raise NeedsAttention('Shohoz requires sign-in to view this seat map. You can still watch this bus here.')
        return {'seats':[{'label':f'{chr(65+i//4)}{i%4+1}', 'available':i%3!=0,
                         'female_only':False, 'x':(i%4)*45, 'y':(i//4)*45} for i in range(12)],
                'message':'Explicit UI test fixture. No real seats.'}

    async def preflight(self, request, offer):
        return await self.seat_map(offer.id)

    async def close(self):
        pass


async def main():
    output = Path('/tmp/seatwatch-react')
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='seatwatch-react-') as directory:
        config = WebSettings(_env_file=None, website_database=Path(directory)/'test.sqlite3',
            website_public_url='http://127.0.0.1:8769', browser_executable=os.environ.get('BROWSER_EXECUTABLE','/opt/google/chrome/chrome'))
        app = create_app(config, search_factory=FixtureProvider,
                         provider_factory=lambda mode, cfg: DemoProvider(cfg) if mode == 'demo' else FixtureProvider(cfg))
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1',port=8769,log_level='warning',access_log=False))
        task = asyncio.create_task(server.serve())
        try:
            while not server.started:
                if task.done(): await task
                await asyncio.sleep(.05)
            async with async_playwright() as p:
                browser = await p.chromium.launch(executable_path=config.browser_executable,headless=True)
                page = await browser.new_page(viewport={'width':1440,'height':1120})
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                await page.goto('http://127.0.0.1:8769')
                await page.get_by_role('heading',name='Where are we headed?').wait_for()
                assert await page.get_by_role('link',name='Book tickets',exact=True).count()==1, 'Missing transport booking entry point'
                await page.get_by_role('link',name='Book tickets',exact=True).click()
                await page.get_by_role('heading',name='Every way to get there.').wait_for()
                for label, url in (
                    ('Bus', 'https://www.shohoz.com/bus-tickets'),
                    ('Train', 'https://train.shohoz.com/'),
                    ('Flights', 'https://www.shohoz.com/air-tickets'),
                    ('Launch', 'https://www.shohoz.com/launch-tickets/'),
                ):
                    link=page.get_by_role('link',name=f'Book {label.lower()} on Shohoz',exact=True)
                    assert await link.get_attribute('href')==url
                    assert await link.get_attribute('target')=='_blank'
                await page.screenshot(path=str(output/'tickets.png'),full_page=True,animations='disabled')
                for width in (320,390,768):
                    await page.set_viewport_size({'width':width,'height':844})
                    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Tickets overflow {width}'
                await page.screenshot(path=str(output/'tickets-tablet.png'),full_page=True,animations='disabled')
                await page.set_viewport_size({'width':1440,'height':1120})
                await page.get_by_role('link',name='Explore buses',exact=True).click()
                await page.screenshot(path=str(output/'desktop.png'),full_page=True,animations='disabled')
                await page.get_by_role('button',name='Switch to dark theme').click()
                await page.screenshot(path=str(output/'dark.png'),full_page=True,animations='disabled')
                await page.get_by_role('link',name='Book tickets',exact=True).click()
                await page.get_by_role('heading',name='Every way to get there.').wait_for()
                await page.screenshot(path=str(output/'tickets-dark.png'),full_page=True,animations='disabled')
                await page.get_by_role('link',name='Explore buses',exact=True).click()
                await page.reload()
                assert await page.locator('html').get_attribute('data-theme') == 'dark'
                await page.get_by_role('button',name='Switch to light theme').click()
                # Public search, filters, native seats and provider sign-in handling.
                await page.get_by_role('button',name='Search buses',exact=True).click()
                await page.locator('.bus-card').first.wait_for()
                assert await page.locator('.bus-card').count()==3
                notice=page.locator('.bus-card').filter(has_text='Notice Bus')
                assert await notice.get_by_role('button',name='Select seats',exact=False).count()==0
                handoff=notice.get_by_role('link',name='Continue on Shohoz',exact=False)
                url=urlparse(await handoff.get_attribute('href'))
                assert url.hostname=='www.shohoz.com'
                params=parse_qs(url.query)
                assert params['fromcity']==['Dhaka'] and params['tocity']==['Bogura']
                journey_date=await page.get_by_label('Journey date',exact=True).input_value()
                assert params['doj']==[datetime.strptime(journey_date, '%Y-%m-%d').strftime('%d-%b-%Y')]
                await page.get_by_label('Number of seats',exact=True).select_option('4')
                await page.get_by_role('button',name='Search buses',exact=True).click()
                scarce=page.locator('.bus-card').filter(has_text='Other Bus')
                await scarce.get_by_text('Only 3 seats listed; you requested 4.',exact=True).wait_for()
                assert await scarce.get_by_role('link',name='Continue on Shohoz',exact=False).is_visible()
                await page.get_by_label('Number of seats',exact=True).select_option('1')
                await page.get_by_role('button',name='Search buses',exact=True).click()
                await scarce.get_by_role('button',name='Select seats',exact=False).wait_for()
                await page.get_by_label('Filter by operator').select_option('Test Express')
                assert await page.locator('.bus-card').count()==1
                await page.get_by_role('button',name='Select seats',exact=False).click()
                await page.get_by_role('button',name='Seat A2',exact=True).wait_for()
                await page.get_by_role('button',name='Seat A2',exact=True).click()
                await page.get_by_role('button',name='Seat A3',exact=True).click()
                assert await page.locator('.native-seat.chosen').count()==1
                await page.screenshot(path=str(output/'seats.png'))
                await page.get_by_role('button',name='Watch this bus',exact=True).click()
                await page.get_by_label('Full name',exact=True).fill('React Tester')
                email, password = f'react-{secrets.token_hex(5)}@example.test', secrets.token_urlsafe(20)
                await page.get_by_label('Email address',exact=True).fill(email)
                await page.get_by_label('Password',exact=True).fill(password)
                await page.get_by_role('button',name='Create account',exact=True).click()
                await page.get_by_role('heading',name='Make room for your plans.').wait_for()
                await page.get_by_role('button',name='Continue',exact=False).click()
                await page.get_by_role('heading',name='Good timing is everything.').wait_for()
                await page.get_by_role('button',name='Continue',exact=False).click()
                await page.locator('select[name^=gender_]').select_option('female')
                await page.get_by_label('Contact phone',exact=True).fill('+8801700000000')
                await page.get_by_role('button',name='Save live watch',exact=False).click()
                await page.locator('.journey-card').wait_for()
                jobs=(await (await page.request.get('http://127.0.0.1:8769/api/jobs')).json())['jobs']
                assert len(jobs)==1 and jobs[0]['request']['monitor_only']
                assert jobs[0]['request']['selected_offer_id']=='fixture-trip'
                assert jobs[0]['request']['preferred_seats']==['A2']
                # Two travelers, safe demo preparation, manual demo payment.
                await page.get_by_role('button',name='Plan a journey',exact=False).click()
                await page.locator('select[name=seat_count]').select_option('2')
                await page.get_by_role('button',name='Continue',exact=False).click()
                await page.get_by_role('button',name='Continue',exact=False).click()
                await page.locator('select[name^=gender_]').first.wait_for()
                for field in await page.locator('select[name^=gender_]').all(): await field.select_option('female')
                await page.get_by_label('Send me booking updates on WhatsApp').check()
                await page.get_by_role('button',name='Start watching',exact=False).click()
                await page.get_by_role('button',name='Review & pay',exact=False).wait_for(timeout=30000)
                await page.get_by_role('button',name='Review & pay',exact=False).click()
                await page.get_by_text('1,300 BDT',exact=False).wait_for()
                await page.get_by_role('button',name='Simulate my payment',exact=False).click()
                await page.get_by_text('Demo completed',exact=True).last.wait_for()
                await page.get_by_role('button',name='Close dialog',exact=True).click()
                await page.get_by_role('link',name='Notifications',exact=True).click()
                await page.get_by_text('Demo preview · not sent',exact=True).first.wait_for()
                await page.get_by_role('link',name='Connections',exact=True).first.click()
                await page.get_by_role('heading',name='WhatsApp Business',exact=True).wait_for()
                await page.get_by_label('Current password',exact=True).fill(password)
                await page.get_by_role('button',name='Generate recovery code',exact=True).click()
                await page.get_by_label('Your recovery code',exact=True).wait_for()
                recovery_code = await page.get_by_label('Your recovery code',exact=True).input_value()
                assert len(recovery_code) > 30
                await page.screenshot(path=str(output/'connections.png'),full_page=True,animations='disabled')
                await page.get_by_role('link',name='Explore buses',exact=True).click()
                await page.get_by_role('button',name='Search buses',exact=True).click()
                await page.locator('.bus-card').first.wait_for()
                await page.locator('.bus-card').filter(has_text='Other Bus').get_by_role('button',name='Select seats',exact=False).click()
                await page.get_by_text('A quick stop at Shohoz',exact=True).wait_for()
                assert await page.get_by_role('link',name='Open on Shohoz',exact=False).is_visible()
                await page.keyboard.press('Escape')
                await page.screenshot(path=str(output/'results.png'),full_page=True,animations='disabled')
                for width in (390,320,768):
                    await page.set_viewport_size({'width':width,'height':844})
                    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Overflow {width}'
                    await page.screenshot(path=str(output/f'mobile-{width}.png'),full_page=True,animations='disabled')
                await page.set_viewport_size({'width':390,'height':844})
                await page.get_by_role('button',name='Open navigation').click()
                await page.get_by_role('link',name='My journeys',exact=False).click()
                await page.get_by_role('button',name='Close navigation',exact=True).wait_for(state='hidden')
                # Back navigation and live-watch pause/resume retain ownership checks.
                await page.locator('.journey-card').filter(has_text='LIVE AVAILABILITY WATCH').get_by_role('button',name='View journey',exact=False).click()
                await page.get_by_role('button',name='Pause monitoring').click()
                await page.get_by_role('button',name='Resume monitoring').wait_for()
                await page.get_by_role('button',name='Resume monitoring').click()
                await page.get_by_role('button',name='Pause monitoring').wait_for()
                await page.get_by_role('button',name='Close dialog',exact=True).click()
                await page.get_by_role('button',name='Open navigation').click()
                await page.get_by_role('button',name='Sign out',exact=True).click()
                await page.get_by_role('button',name='Sign in',exact=True).wait_for()
                assert (await (await page.request.get('http://127.0.0.1:8769/api/auth/me')).json())['user'] is None
                # Recover with the saved code, then sign in using the new password.
                await page.get_by_role('button',name='Sign in',exact=True).click()
                await page.get_by_role('button',name='Already have an account? Sign in',exact=True).click()
                await page.get_by_role('button',name='Use a recovery code',exact=True).click()
                await page.get_by_label('Email address',exact=True).fill(email)
                await page.get_by_label('Saved recovery code',exact=True).fill(recovery_code)
                new_password = secrets.token_urlsafe(20)
                await page.get_by_label('New password',exact=True).fill(new_password)
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                await page.get_by_role('button',name='Reset password',exact=True).click()
                await page.get_by_text('Password reset.',exact=False).wait_for()
                await page.get_by_role('button',name='Back to sign in',exact=True).click()
                await page.get_by_label('Email address',exact=True).fill(email)
                await page.get_by_label('Password',exact=True).fill(new_password)
                await page.get_by_role('dialog').get_by_role('button',name='Sign in',exact=True).click()
                await page.get_by_role('dialog').wait_for(state='hidden')
                assert (await (await page.request.get('http://127.0.0.1:8769/api/auth/me')).json())['user']['email'] == email
                await page.goto('http://127.0.0.1:8769')
                await page.get_by_label('Destination city',exact=True).fill('Unavailable')
                await page.get_by_role('button',name='Search buses',exact=True).click()
                fallback=page.get_by_role('link',name='Continue this search on Shohoz',exact=False)
                await fallback.wait_for()
                assert parse_qs(urlparse(await fallback.get_attribute('href')).query)['tocity']==['Unavailable']
                assert await page.locator('.bus-card').count()==0
                assert not errors,errors
                await browser.close()
                print('PASS: transport booking handoffs, insufficient-seat/provider-notice/search-failure fallbacks, production React UI, themes, public search, filters, seat preferences, provider sign-in gate, signup, exact-departure watch, demo manual payment, notifications, pause/resume, recovery-code creation and password reset, logout/login, and 320/390/768px layout. No real reservations or messages.',flush=True)
                print('Screenshots:',output,flush=True)
        finally:
            server.should_exit=True
            await task


if __name__=='__main__':
    asyncio.run(main())
