"""Project Runeberg: one story (a run of OCR pages listed in a book's table of contents) per URL.

URL form: https://runeberg.org/<book>/<NNNN>.html  where NNNN is the first page of the story.
The book index (https://runeberg.org/<book>/) lists each story title linked to its first page,
followed by links to all of its pages. Pages are fetched one by one with the 2 second crawl delay
requested in robots.txt (bulk download endpoints are disallowed and not used).
"""
import html
import re
from urllib.parse import urlparse

from .base import FetchError, PoliteFetcher, SourceText, decode_html, join_lines

DOMAINS = ("runeberg.org",)
DELAY = 2.0
BASE = "https://runeberg.org"
ENDS_SENTENCE = re.compile(r"[.!?…:”\"»)]\s*$")
PAGE_LINK = re.compile(r'<a href="(\d{4})\.html"[^>]*>([^<]+)</a>')
TEXT_BLOCK = re.compile(r"<!-- mode=\w+ -->(.*?)<!-- (?:NEWIMAGE\d*|####) -->", re.S)


def parse_story_url(url):
    m = re.fullmatch(r"/([a-z0-9_]+)/(\d{4})\.html", urlparse(url).path)
    if not m:
        raise FetchError(f"Expected a Runeberg page URL like {BASE}/<book>/0005.html, got {url}")
    return m.group(1), m.group(2)


def parse_index(index_html):
    """Return [{'title', 'first', 'pages'}] for the entries in a book's table of contents."""
    entries = []
    for href, label in PAGE_LINK.findall(index_html):
        label = " ".join(html.unescape(label).split())
        if label.isdigit():
            if entries:
                entries[-1]["pages"].append(href)
        else:
            entries.append({"title": label, "first": href, "pages": []})
    for e in entries:
        e["pages"] = list(dict.fromkeys(e["pages"] or [e["first"]]))
    return entries


def page_paragraphs(page_html):
    """Paragraphs of OCR text on one page (lines re-flowed, line-end hyphens removed)."""
    m = TEXT_BLOCK.search(page_html)
    if not m:
        raise FetchError("No OCR text block found on page")
    text = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "", m.group(1))))
    paragraphs = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        para = lines[0]
        for ln in lines[1:]:
            para = join_lines(para, ln)
        if not re.fullmatch(r"[\divxlc.\s]+", para, re.I):  # bare page numbers
            paragraphs.append(para)
    return paragraphs


def merge_pages(pages):
    """Concatenate per-page paragraphs; a paragraph not ending a sentence continues on the next page."""
    out = []
    for paras in pages:
        if out and paras and not ENDS_SENTENCE.search(out[-1]):
            out[-1] = join_lines(out[-1], paras[0])
            paras = paras[1:]
        out.extend(paras)
    return out


def _squash(s):
    return re.sub(r"\W+", "", s).lower()


def read_metadata(page_html):
    def meta(name):
        m = re.search(rf'name="{name}"\s*content="([^"]*)"', page_html)
        return html.unescape(m.group(1)).strip() if m else ""
    return {"author": meta("DC.Creator.PersonalName"), "year": meta("DC.Date"), "work": meta("DC.Relation.IsPartOf")}


def fetch(url, fetcher=None):
    fetcher = fetcher or PoliteFetcher(delay=DELAY)
    book, first = parse_story_url(url)
    index = parse_index(decode_html(fetcher.get_bytes(f"{BASE}/{book}/")))
    story = next((e for e in index if e["first"] == first), None)
    if story is None:
        raise FetchError(f"Page {first} is not the first page of a story in {book!r}")
    pages_html = [decode_html(fetcher.get_bytes(f"{BASE}/{book}/{p}.html")) for p in story["pages"]]
    paragraphs = merge_pages([page_paragraphs(p) for p in pages_html])
    if paragraphs and _squash(paragraphs[0]) == _squash(story["title"]):
        paragraphs = paragraphs[1:]  # the printed title line
    if not paragraphs:
        raise FetchError(f"No text found for story {story['title']!r}")
    meta = read_metadata(pages_html[0])
    author = meta["author"]
    title = f"{story['title']} ({author})" if author else story["title"]
    work = meta["work"] + (f" ({meta['year']})" if meta["year"] else "") if meta["work"] else ""
    credit = ", ".join(x for x in (author, work) if x)
    attribution = f"{credit}. Text from Project Runeberg (public domain)." if credit else ""
    return SourceText(title=title, sections=[(None, paragraphs)], attribution=attribution,
                      extra={"pages": len(story["pages"])})
