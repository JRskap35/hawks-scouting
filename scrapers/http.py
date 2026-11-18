"""
Polite HTTP client shared by every scraper.

* Checks robots.txt before every request and refuses disallowed paths.
* Waits a minimum interval between requests to the same host (default 3 seconds).
* Caches responses on disk so reruns within the cache window never touch the site.
* Retries 429 and 5xx responses with backoff, honoring Retry-After.
* Identifies itself with a clear User-Agent and a contact address.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import timedelta
from urllib import robotparser
from urllib.parse import urlparse

import requests
import requests_cache

log = logging.getLogger(__name__)

DEFAULT_DELAY = float(os.getenv("SCRAPER_DELAY_SEC", "3.0"))
CACHE_HOURS = float(os.getenv("SCRAPER_CACHE_HOURS", "12"))
CONTACT = os.getenv("SCRAPER_CONTACT", "scouting@example.com")
USER_AGENT = f"HawksScoutingBot/0.1 (+mailto:{CONTACT})"


class RobotsDisallowed(Exception):
    pass


class PoliteSession:
    def __init__(self, cache_path: str = ".cache/http", delay: float = DEFAULT_DELAY,
                 cache_hours: float = CACHE_HOURS, per_host_delay: dict[str, float] | None = None):
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        self.session = requests_cache.CachedSession(
            cache_path,
            expire_after=timedelta(hours=cache_hours),
            allowable_codes=(200,),
            stale_if_error=True,
        )
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
        self.delay = delay
        self.per_host_delay = per_host_delay or {}
        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}

    # -- robots ---------------------------------------------------------------

    def _robots_for(self, url: str) -> robotparser.RobotFileParser | None:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                r = requests.get(f"{base}/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=15)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                    delay = rp.crawl_delay(USER_AGENT)
                    if delay:
                        self.per_host_delay[p.netloc] = max(float(delay), self.delay)
                else:
                    rp = None          # no robots.txt means no restrictions were published
            except requests.RequestException as e:
                log.warning("robots.txt unreachable for %s (%s); proceeding carefully", base, e)
                rp = None
            self._robots[base] = rp
        return self._robots[base]

    def allowed(self, url: str) -> bool:
        rp = self._robots_for(url)
        return True if rp is None else rp.can_fetch(USER_AGENT, url)

    # -- fetching ---------------------------------------------------------------

    def _wait(self, host: str):
        gap = self.per_host_delay.get(host, self.delay)
        last = self._last_hit.get(host)
        if last is not None:
            remaining = gap - (time.monotonic() - last)
            if remaining > 0:
                time.sleep(remaining)

    def get(self, url: str, *, force_refresh: bool = False, max_retries: int = 4) -> requests.Response:
        if not self.allowed(url):
            raise RobotsDisallowed(url)

        host = urlparse(url).netloc
        for attempt in range(max_retries + 1):
            # Cached responses skip the wait, since they never reach the site.
            if force_refresh or not self.session.cache.contains(url=url):
                self._wait(host)
            resp = self.session.get(url, timeout=30, force_refresh=force_refresh)
            if not getattr(resp, "from_cache", False):
                self._last_hit[host] = time.monotonic()

            if resp.status_code == 200:
                return resp
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                wait = resp.headers.get("Retry-After")
                backoff = float(wait) if wait and wait.isdigit() else self.delay * (2 ** (attempt + 1))
                log.warning("%s returned %s, retrying in %.0fs", url, resp.status_code, backoff)
                time.sleep(backoff)
                continue
            resp.raise_for_status()
        raise RuntimeError(f"gave up on {url}")

    def get_text(self, url: str, **kw) -> str:
        return self.get(url, **kw).text
