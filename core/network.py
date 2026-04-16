import logging
from curl_cffi import requests as cur_requests
from .config import TIMEOUT

logger = logging.getLogger(__name__)


class NetworkClient:
    def __init__(self, impersonate="chrome"):
        self.impersonate = impersonate

    def get(self, url, timeout=TIMEOUT):
        try:
            response = cur_requests.get(
                url, impersonate=self.impersonate, timeout=timeout
            )
            response.raise_for_status()
            return response
        except Exception as e:
            logger.error(f"Network error getting {url}: {e}")
            raise
