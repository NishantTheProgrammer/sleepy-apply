#!/usr/bin/env python3
import sys
import os
import asyncio

# Ensure backend root is in sys.path
backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from app.sources.playwright_crawler import main_cli

if __name__ == "__main__":
    asyncio.run(main_cli())

