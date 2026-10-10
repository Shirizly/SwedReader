"""Wikipedia: plain text through the MediaWiki API (no HTML scraping)."""
import json
import re
from urllib.parse import unquote, urlparse

from .base import FetchError, PoliteFetcher, SourceText

DOMAINS = ("wikipedia.org",)
DELAY = 0.0
SKIP_SECTIONS = {"Källor", "Referenser", "Noter", "Externa länkar", "Se även", "Litteratur", "Fotnoter",
                 "Tryckta källor", "Vidare läsning", "Webbkällor", "Bildgalleri"}


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


def fetch(url, fetcher=None):
    fetcher = fetcher or PoliteFetcher(delay=DELAY)
    parsed = urlparse(url)
    title = unquote(parsed.path.rsplit("/", 1)[-1])
    if not title:
        raise FetchError(f"No article title in URL: {url}")
    params = {"action": "query", "prop": "extracts", "explaintext": 1, "format": "json",
              "titles": title, "redirects": 1}
    raw = fetcher.get_bytes(f"{parsed.scheme}://{parsed.netloc}/w/api.php", params=params)
    page = next(iter(json.loads(raw.decode("utf-8"))["query"]["pages"].values()))
    if not page.get("extract", "").strip():
        raise FetchError(f"No text found for {title!r}")
    sections = parse_sections(page["extract"])
    if not sections:
        raise FetchError(f"No article text left after parsing {title!r}")
    history = f"{parsed.scheme}://{parsed.netloc}/w/index.php?title={page['title'].replace(' ', '_')}&action=history"
    return SourceText(title=page["title"], sections=sections, history_url=history)
