from abc import ABC, abstractmethod


class BaseScraper(ABC):
    @abstractmethod
    def fetch_articles(self, cutoff=None):
        """
        Return article metadata.

        The cut-off is the oldest article that is wanted. Everything older is left out.
        """
        pass

    @abstractmethod
    def fetch_article_content(self, article):
        """Return full article."""
        pass
