"""Source modules, one per site. Each module exposes DOMAINS, DELAY and fetch(url, fetcher=None) -> SourceText.

To add a source: create a module here (handle its own encoding and page structure), list its
domains, and add it to MODULES. The lane (public/private) is decided separately in sources.yaml.
"""
from urllib.parse import urlparse

from . import runeberg, wikipedia
from .base import FetchError, PoliteFetcher, SourceText

MODULES = (wikipedia, runeberg)


def source_module(url):
    host = (urlparse(url).hostname or "").lower()
    for mod in MODULES:
        if any(host == d or host.endswith("." + d) for d in mod.DOMAINS):
            return mod
    raise FetchError(f"No extractor for {host!r} yet (supported: "
                     f"{', '.join(d for m in MODULES for d in m.DOMAINS)})")


def fetch(url, fetcher=None):
    mod = source_module(url)
    return mod.fetch(url, fetcher or PoliteFetcher(delay=mod.DELAY))


__all__ = ["fetch", "source_module", "FetchError", "PoliteFetcher", "SourceText"]
