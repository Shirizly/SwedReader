"""Lane resolution: which sources may be published (public) and which must stay local (private)."""
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
READER = ROOT / "reader"
PUBLIC_CONTENT = READER / "content"
PRIVATE_DATA = DATA / "private"
DEFAULT_SOURCES = ROOT / "sources.yaml"


def load_sources(path=DEFAULT_SOURCES):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _matches(host, domain):
    return host == domain or host.endswith("." + domain)


def resolve_lane(url, sources=None):
    """Return a dict with lane ('public'|'private'), domain, and licence info for the URL.
    Unknown domains are private."""
    sources = load_sources() if sources is None else sources
    host = (urlparse(url).hostname or "").lower()
    if not host:
        raise ValueError(f"Not a valid URL: {url!r}")
    for entry in sources.get("public", []):
        if _matches(host, entry["domain"]):
            return {"lane": "public", "domain": host, "license": entry.get("license", ""),
                    "license_url": entry.get("license_url", ""), "attribution": entry.get("attribution", "")}
    return {"lane": "private", "domain": host, "license": "", "license_url": "", "attribution": ""}
