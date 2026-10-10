"""Shared pieces for source modules: errors, result type and a polite fetcher."""
import re
import time
from dataclasses import dataclass, field

import requests

HEADERS = {"User-Agent": "TranslatePipeline/0.1 (personal language-learning project)"}


class FetchError(Exception):
    pass


@dataclass
class SourceText:
    """What a source module returns: sections of paragraphs plus optional metadata."""
    title: str
    sections: list  # [(heading | None, [paragraph, ...]), ...]
    attribution: str = ""  # overrides the sources.yaml attribution when set
    history_url: str = ""
    extra: dict = field(default_factory=dict)


class PoliteFetcher:
    """GET pages with a minimum delay between requests and an in-memory cache."""

    def __init__(self, session=requests, delay=0.0):
        self.session, self.delay, self._last, self._cache = session, delay, 0.0, {}

    def get_bytes(self, url, params=None):
        key = (url, tuple(sorted((params or {}).items())))
        if key in self._cache:
            return self._cache[key]
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        try:
            r = self.session.get(url, params=params, headers=HEADERS, timeout=30)
            self._last = time.monotonic()
            r.raise_for_status()
        except requests.RequestException as e:
            raise FetchError(f"Could not fetch {url}: {e}") from e
        self._cache[key] = r.content
        return r.content


def decode_html(raw, default="utf-8"):
    """Decode HTML bytes using the charset declared in its first 2 KB (older pages are often latin-1)."""
    m = re.search(rb"charset=['\"]?([\w-]+)", raw[:2048], re.I)
    for enc in ((m.group(1).decode("ascii"),) if m else ()) + (default,):
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode(default, errors="replace")


def join_lines(a, b):
    """Join two text lines, removing a line-end hyphen when the word continues on the next line."""
    if a.endswith("-") and b[:1].islower() and b.split()[0] not in {"och", "eller", "samt", "el."}:
        return a[:-1] + b
    return f"{a} {b}"
