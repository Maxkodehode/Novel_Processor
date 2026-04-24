import logging  # logger shows an error in the IDE "No module named 'logger' "
from curl_cffi import (
    requests as cur_requests,
)  # curl_cffi and request shows an error "Unresolved reference 'requests', 'curl_cffi'"
from .config import TIMEOUT

logger = logging.getLogger(__name__)  # Unresolved reference 'logging'


class NetworkClient:
    def __init__(self, impersonate="chrome"):
        self.impersonate = impersonate

    def get(self, url, timeout=TIMEOUT, headers=None):
        try:
            response = cur_requests.get(
                url,
                impersonate=self.impersonate,
                timeout=timeout,
                headers=headers if headers else {},
            )
            response.raise_for_status()
            return response
        except Exception as e:  # Unresolved reference 'Exception'
            logger.error(f"Network error getting {url}: {e}")
            raise
