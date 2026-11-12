"""
Fetch the news and store it.

The window may be given on the command line:

    python run_scraper.py            # the last 30 days
    python run_scraper.py 90         # the last 90 days
"""

import sys
from datetime import datetime, timedelta, timezone

from app.services.scraper_service import ScraperService

days = int(sys.argv[1]) if len(sys.argv) > 1 else 30

cutoff = datetime.now(timezone.utc) - timedelta(days=days)

service = ScraperService()

service.run(cutoff=cutoff)
