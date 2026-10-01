"""Compatibility entrypoint for the isolated production React browser test.

Run: python scripts/browser_smoke.py
No existing server is required; all booking data is temporary and simulated.
"""
import asyncio
from react_smoke import main

if __name__ == '__main__':
    asyncio.run(main())
