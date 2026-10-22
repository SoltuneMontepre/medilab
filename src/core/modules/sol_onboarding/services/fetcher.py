"""Fetches the pages of a source under its safety rules: HTTPS on the source's host only, what its robots.txt allows,
the source's delay between two requests, and limits on size, time and content type. It is the only code of the module
that makes outbound requests."""

from datetime import datetime, timedelta
from time import monotonic, sleep
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests

from odoo import fields
from odoo.exceptions import LockError

from odoo.addons.sol_laboratory.models.system.scheduled_job import PermanentJobError
from odoo.addons.sol_onboarding.constants.onboarding import (
    CONNECT_TIMEOUT_SECONDS,
    CONTENT_TYPES,
    MAX_BYTES,
    MAX_REDIRECTS,
    TIMEOUT_SECONDS,
    USER_AGENT,
)
from odoo.addons.sol_onboarding.services.adapters.base import Fetched

CHUNK_SIZE = 64 * 1024
# robots.txt is the only document accepted as plain text.
ROBOTS_CONTENT_TYPES = {"text/plain": "text"}
# ponytail: robots.txt is cached per worker process, keyed by host and run, so each worker reads it at most once per
# run; keep it on the run if one read per worker becomes too many requests.
ROBOTS: dict[tuple[str, str], RobotFileParser] = {}
# ponytail: a fetch that raises rolls back its savepoint, with last_request_at and the row lock, so each host's last
# request is also kept per worker process. Ceiling: another worker can request early after a failed fetch; write
# request times outside the job's transaction to close it.
LAST_REQUESTS: dict[str, datetime] = {}
# ponytail: the time until which a source that raised PageUnavailable is left alone, by source id, kept per worker
# process like LAST_REQUESTS, so another worker still spends one attempt; store the time on the source row if that
# matters.
UNAVAILABLE: dict[int, datetime] = {}


class PageSkipped(Exception):
    """The page is not fetched or not read, for the reason str() gives; fetching it again changes nothing."""


class RedirectSkipped(PageSkipped):
    """The page redirects off the host or past the redirect limit."""


class PageRefused(PermanentJobError):
    """The source answered 4xx."""


class PageUnavailable(Exception):
    """The source cannot be read now: a network error, a timeout or a 5xx answer; a later try can read it."""


class SourceBusy(Exception):
    """Another worker holds the source row; fetching from the source can start again at until."""

    def __init__(self, until):
        super().__init__(f"Another worker is fetching from the source; try again at {until}.")
        self.until = until


class Fetcher:
    """Fetches the pages of one source for the run robots_key names."""

    def __init__(self, source, robots_key):
        self.source = source.sudo()
        self.robots_key = robots_key

    def fetch(self, url):
        return self._fetch(url, CONTENT_TYPES)

    def _fetch(self, url, content_types, check_robots=True):
        # Each hop of a redirect is checked and waits its turn like the first request.
        for hop in range(MAX_REDIRECTS + 1):
            url = self._checked_address(url, redirected=bool(hop))
            if check_robots and not self._robots().can_fetch(USER_AGENT, url):
                raise PageSkipped(self.source.env._("disallowed by robots.txt"))
            self._wait_turn()
            deadline = monotonic() + TIMEOUT_SECONDS
            with requests.Session() as session:
                session.trust_env = False
                session.headers.clear()
                session.headers["User-Agent"] = USER_AGENT
                try:
                    response = session.get(
                        url, stream=True, allow_redirects=False, timeout=(CONNECT_TIMEOUT_SECONDS, TIMEOUT_SECONDS)
                    )
                except requests.RequestException as error:
                    raise PageUnavailable(f"The source did not answer: {type(error).__name__}.") from None
                with response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers["Location"])
                        continue
                    return self._read(response, url, content_types, deadline)
        raise RedirectSkipped(self.source.env._("too many redirects"))

    def _checked_address(self, url, redirected):
        # The address is sent as parsed here, so the request goes where the check looked.
        off_host = (
            RedirectSkipped(self.source.env._("redirect off the host"))
            if redirected
            else PageSkipped(self.source.env._("another host"))
        )
        try:
            address = urlsplit(url)
            port = address.port
        except ValueError:
            raise off_host from None
        if address.scheme != "https":
            raise PageSkipped(self.source.env._("not HTTPS"))
        if address.hostname != self.source.host or address.username is not None or port is not None:
            raise off_host
        return address.geturl()

    def _robots(self):
        key = (self.source.host, self.robots_key)
        if key not in ROBOTS:
            robots = RobotFileParser()
            try:
                document = self._fetch(
                    f"https://{self.source.host}/robots.txt", ROBOTS_CONTENT_TYPES, check_robots=False
                )
            except RedirectSkipped:
                # Rules that cannot be followed to their address disallow everything for the run (RFC 9309 2.3.1.2).
                robots.disallow_all = True
            except (PageRefused, PageSkipped):
                # A robots.txt that answers 4xx or cannot be used allows everything for the run.
                robots.allow_all = True
            else:
                robots.parse(document.body.decode("utf-8", "replace").splitlines())
            ROBOTS[key] = robots
        return ROBOTS[key]

    def _wait_turn(self):
        # The row stays locked until this transaction ends; lock_for_update does not wait for another worker's lock.
        source = self.source
        try:
            source.lock_for_update()
        except LockError:
            raise SourceBusy(fields.Datetime.now() + timedelta(seconds=source.delay_seconds)) from None
        source.invalidate_recordset(["last_request_at"])
        last = max(source.last_request_at or datetime.min, LAST_REQUESTS.get(source.host, datetime.min))
        # A last request ahead of the clock waits the whole delay, never longer.
        elapsed = max((datetime.now() - last).total_seconds(), 0)
        if elapsed < source.delay_seconds:
            sleep(source.delay_seconds - elapsed)
        # Rounded up to the second, so the stored time is never before the request sent next.
        stamp = (datetime.now() + timedelta(microseconds=999_999)).replace(microsecond=0)
        source.last_request_at = LAST_REQUESTS[source.host] = stamp

    def _read(self, response, url, content_types, deadline):
        status = response.status_code
        if 400 <= status < 500:
            raise PageRefused(f"The source answered {status}.")
        if not 200 <= status < 300:
            raise PageUnavailable(f"The source answered {status}.")
        media_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if media_type not in content_types:
            raise PageSkipped(self.source.env._("content type %s not accepted", media_type))
        length = response.headers.get("Content-Length", "")
        if length.isdigit() and int(length) > MAX_BYTES:
            raise PageSkipped(self.source.env._("over 10 MB"))
        body = bytearray()
        # ponytail: the deadline is checked between chunks, so a server trickling bytes can hold the worker until
        # Odoo's time limit; read in a thread with a hard stop if a source ever does.
        try:
            for chunk in response.iter_content(CHUNK_SIZE):
                body += chunk
                if len(body) > MAX_BYTES:
                    raise PageSkipped(self.source.env._("over 10 MB"))
                if monotonic() > deadline:
                    raise PageUnavailable("Reading the page took longer than the timeout.")
        except requests.RequestException as error:
            raise PageUnavailable(f"The page stopped arriving: {type(error).__name__}.") from None
        return Fetched(url, content_types[media_type], bytes(body), fields.Datetime.now())
