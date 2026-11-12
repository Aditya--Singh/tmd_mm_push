from datetime import datetime, timedelta, timezone

from loguru import logger

from app.services.scraper_service import ScraperService
from app.services.ai_service import AIService


#: The window used when nobody says how far back the news may reach.
DEFAULT_DAYS = 30

#: The furthest back the news may reach.
MAX_DAYS = 90


class NewsPipelineService:
    def run(self, days: int = DEFAULT_DAYS):
        """
        Fetch the news and run the AI analysis over it.

        Only the news published in the last `days` days is kept. The window is counted
        back from today, and the date it starts at is the cut-off the scraper stops at.
        """
        days = max(1, min(int(days), MAX_DAYS))

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        logger.info(
            f"Starting news ingestion pipeline "
            f"(news published from {cutoff.isoformat()} will be stored)"
        )


        logger.info("Step 1: Scraping latest news")
        ScraperService().run(cutoff=cutoff)

        logger.info("Step 2: Running AI analysis")
        AIService().run()

        logger.info("News ingestion pipeline completed")
