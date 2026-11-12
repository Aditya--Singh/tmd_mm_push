from datetime import datetime, timedelta, timezone

from loguru import logger

from app.config.settings import get_settings
from app.database.database import SessionLocal
from app.repositories.news_repository import NewsRepository
from app.scrapers.psuconnect import PSUConnectScraper


settings = get_settings()


def house_cutoff() -> datetime | None:
    """
    The oldest day the news may reach, whatever window is asked for.

    It is a floor: a run may ask for a shorter window, never for a longer one. The setting
    is a date, and a setting that cannot be read is ignored rather than stopping the run.
    """
    raw = (settings.news_cutoff_date or "").strip()

    if not raw:
        return None

    try:
        day = datetime.fromisoformat(raw)
    except ValueError:
        logger.warning(
            "NEWS_CUTOFF_DATE is not a date and is ignored: {}", raw
        )

        return None

    if day.tzinfo is None:
        day = day.replace(tzinfo=timezone.utc)

    return day


def effective_cutoff(cutoff: datetime | None) -> datetime | None:
    """The cut-off of a run: the window that was asked for, or the floor, whichever is later."""
    floor = house_cutoff()

    if floor is None:
        return cutoff

    if cutoff is None or floor > cutoff:
        return floor

    return cutoff


class ScraperService:
    def run(self, cutoff: datetime | None = None):
        """
        Fetch the news and store it.

        Only the news published on or after the cut-off is stored. Without a cut-off
        the scraper decides how far back to go.
        """

        cutoff = effective_cutoff(cutoff)

        db = SessionLocal()

        try:
            repository = NewsRepository(db)

            scraper = PSUConnectScraper()

            articles = scraper.fetch_articles(cutoff=cutoff)

            logger.info(f"Found {len(articles)} articles")

            existing_urls = repository.get_existing_urls()

            logger.info(f"{len(existing_urls)} articles already exist")

            inserted = 0
            skipped = 0

            for article in articles:
                if article.url in existing_urls:
                    skipped += 1
                    continue

                if cutoff and article.publish_date < cutoff:
                    # Older than the window that was asked for.
                    skipped += 1
                    continue

                try:
                    article = scraper.fetch_article_content(article)

                    repository.save(article)

                    existing_urls.add(article.url)

                    inserted += 1

                    logger.info(f"Inserted: {article.headline}")

                except Exception as e:
                    logger.error(
                        f"Failed to process article: "
                        f"{article.headline} | {article.url} | {e}"
                    )
                    continue

            logger.info(f"Completed. Inserted={inserted}, Skipped={skipped}")

        finally:
            db.close()
