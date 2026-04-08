from abc import ABC, abstractmethod
from urllib.parse import urlparse


class BaseAdapter(ABC):
    HOSTS: list[str] = []

    @classmethod
    def matches(cls, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(h in host for h in cls.HOSTS)

    @abstractmethod
    def parse(self, soup, url: str) -> dict: ...

    @staticmethod
    def _text(tag) -> str | None:
        return tag.get_text(strip=True) if tag else None

    @staticmethod
    def _abs(href: str, base: str) -> str:
        if href.startswith("http"):
            return href
        p = urlparse(base)
        return f"{p.scheme}://{p.netloc}{href}"
