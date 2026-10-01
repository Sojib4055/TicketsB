"""Read-only live Shohoz search test for the production React interface.

Run: python scripts/search_smoke.py
Uses an isolated server on 8767. Never reserves seats or sends messages.
TICKET_SEARCH_FIXTURE=1 runs the comprehensive local React fixture check instead.
"""
import asyncio
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.async_api import async_playwright
from src.website.app import create_app
from src.website.config import WebSettings


async def main():
    with tempfile.TemporaryDirectory(prefix='seatwatch-search-') as directory:
        config=WebSettings(_env_file=None,website_database=Path(directory)/'test.sqlite3',
            website_public_url='http://127.0.0.1:8767',browser_executable=os.environ.get('BROWSER_EXECUTABLE','/opt/google/chrome/chrome'))
        server=uvicorn.Server(uvicorn.Config(create_app(config,start_worker=False),host='127.0.0.1',port=8767,log_level='warning',access_log=False))
        task=asyncio.create_task(server.serve())
        try:
            while not server.started:
                if task.done(): await task
                await asyncio.sleep(.05)
            async with async_playwright() as p:
                browser=await p.chromium.launch(executable_path=config.browser_executable,headless=True)
                page=await browser.new_page(viewport={'width':1440,'height':1100})
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                await page.goto('http://127.0.0.1:8767')
                await page.get_by_role('button',name='Search buses',exact=True).click()
                await page.locator('.bus-card').first.wait_for(timeout=85000)
                count=await page.locator('.bus-card').count()
                print('LIVE_RESULTS_VISIBLE',count,flush=True)
                await page.screenshot(path='/tmp/seatwatch-react-live.png',full_page=False)
                options=await page.get_by_label('Filter by operator').locator('option').all_text_contents()
                await page.get_by_label('Filter by operator').select_option(label=options[1])
                assert await page.locator('.bus-card').count()>0
                await page.get_by_role('button',name='Reset',exact=True).click()
                await page.get_by_label('Sort departures').select_option('fare_desc')
                await page.locator('.bus-card button.primary:not([disabled])').first.click()
                await page.locator('.native-seat').or_(page.locator('.seat-unavailable')).first.wait_for(timeout=45000)
                if await page.locator('.native-seat').count():
                    await page.locator('.native-seat.available').first.click()
                    assert await page.locator('.native-seat.chosen').count()==1
                    print('LIVE_SEAT_MAP_LOADED',flush=True)
                else:
                    message=await page.locator('.seat-unavailable').inner_text()
                    assert 'requires sign-in' in message,message
                    print('LIVE_PROVIDER_SIGN_IN_REQUIRED: handled explicitly.',flush=True)
                await page.keyboard.press('Escape')
                await page.set_viewport_size({'width':390,'height':844})
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors,errors
                await browser.close()
                print('PASS: real Shohoz search, filters, sorting, seat-map handling, and mobile layout in React. No reservations or payments.',flush=True)
        finally:
            server.should_exit=True
            await task


if __name__=='__main__':
    if os.environ.get('TICKET_SEARCH_FIXTURE')=='1':
        from react_smoke import main as fixture_main
        asyncio.run(fixture_main())
    else:
        asyncio.run(main())
