"""Fetch and parse source text."""
import re
from urllib.parse import unquote, urlparse

import requests

HEADERS = {"User-Agent": "TranslatePipeline/0.1 (personal language-learning project)"}
SKIP_SECTIONS = {"Källor", "Referenser", "Noter", "Externa länkar", "Se även", "Litteratur", "Fotnoter",
                 "Tryckta källor", "Vidare läsning", "Webbkällor", "Bildgalleri"}


class FetchError(Exception):
    pass


def parse_sections(text):
    """Return list of (heading, [paragraphs]); the intro has heading None. Line-based so that
    headings directly followed by text (no blank line) are still recognised."""
    sections, heading, paras, cur = [], None, [], []

    def flush():
        if cur:
            paras.append("\n".join(cur))
            cur.clear()

    for line in text.split("\n"):
        line = line.strip()
        m = re.fullmatch(r"=+\s*(.*?)\s*=+", line)
        if m:
            flush()
            sections.append((heading, paras))
            heading, paras = m.group(1), []
        elif not line:
            flush()
        else:
            cur.append(line)
    flush()
    sections.append((heading, paras))
    return [(h, p) for h, p in sections if h not in SKIP_SECTIONS and p]


def fetch_wikipedia(url, session=requests):
    """Return (title, sections) for a Wikipedia article URL, using the MediaWiki API."""
    parsed = urlparse(url)
    title = unquote(parsed.path.rsplit("/", 1)[-1])
    if not title:
        raise FetchError(f"No article title in URL: {url}")
    params = {"action": "query", "prop": "extracts", "explaintext": 1, "format": "json",
              "titles": title, "redirects": 1}
    try:
        r = session.get(f"{parsed.scheme}://{parsed.netloc}/w/api.php", params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except requests.RequestException as e:
        raise FetchError(f"Could not fetch {url}: {e}") from e
    page = next(iter(r.json()["query"]["pages"].values()))
    if not page.get("extract", "").strip():
        raise FetchError(f"No text found for {title!r}")
    sections = parse_sections(page["extract"])
    if not sections:
        raise FetchError(f"No article text left after parsing {title!r}")
    return page["title"], sections


def fetch(url):
    host = (urlparse(url).hostname or "").lower()
    if host.endswith("wikipedia.org"):
        return fetch_wikipedia(url)
    raise FetchError(f"No extractor for {host!r} yet (only Wikipedia is supported)")
