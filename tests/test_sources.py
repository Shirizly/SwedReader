import json

import pytest

from pipeline.sources import FetchError, fetch, source_module
from pipeline.sources import runeberg, wikipedia
from pipeline.sources.base import decode_html, join_lines


class FakeFetcher:
    def __init__(self, pages):
        self.pages, self.requested = pages, []

    def get_bytes(self, url, params=None):
        self.requested.append(url)
        if url not in self.pages:
            raise FetchError(f"404 {url}")
        v = self.pages[url]
        return v if isinstance(v, bytes) else v.encode("utf-8")


INDEX = """<html><head><meta charset="utf-8"></head><body>
<a href="0001.html">bandtitel</a>
<a href="0005.html">Den heliga natten</a> -
<a href="0005.html">5</a>, <a href="0006.html">6</a>,
<a href="0007.html">Nästa saga</a> - <a href="0007.html">7</a>
</body></html>"""


def page(text, creator=True):
    meta = ('<meta name="DC.Creator.PersonalName"\n   content="Selma Lagerlöf" >\n'
            '<meta name="DC.Date"\n   content="1904" >\n'
            '<meta name="DC.Relation.IsPartOf" scheme="URL"\n   content="/bok/" >\n'
            '<meta name="DC.Relation.IsPartOf"\n   content="Kristuslegender" >\n') if creator else ""
    body = text.replace("\n", "\n<br>")
    return f"<html><head>{meta}</head><body><p><!-- mode=normal -->{body}\n<br>\n<!-- NEWIMAGE2 --></body></html>"


def runeberg_fetcher():
    return FakeFetcher({
        "https://runeberg.org/bok/": INDEX,
        "https://runeberg.org/bok/0005.html": page(
            "DEN HELIGA NATTEN.\n\nNär jag var fem år gammal, hade jag en så stor\nsorg. Det var en sol-\ngubbe som kom.\n\nSista stycket börjar här och\n"),
        "https://runeberg.org/bok/0006.html": page(
            "fortsätter på nästa sida.\n\n6\n\nNytt stycke. Fem- och sexåringar.\n"),
    })


def test_runeberg_story_is_assembled_across_pages():
    src = runeberg.fetch("https://runeberg.org/bok/0005.html", runeberg_fetcher())
    (heading, paras), = src.sections
    assert heading is None
    assert paras == [
        "När jag var fem år gammal, hade jag en så stor sorg. Det var en solgubbe som kom.",
        "Sista stycket börjar här och fortsätter på nästa sida.",  # paragraph continued across the page break
        "Nytt stycke. Fem- och sexåringar.",  # page number dropped; hyphen before "och" kept
    ]
    assert src.title == "Den heliga natten (Selma Lagerlöf)"
    assert src.attribution == "Selma Lagerlöf, Kristuslegender (1904). Text from Project Runeberg (public domain)."


def test_runeberg_fetches_only_the_stories_pages():
    f = runeberg_fetcher()
    runeberg.fetch("https://runeberg.org/bok/0005.html", f)
    assert f.requested == ["https://runeberg.org/bok/", "https://runeberg.org/bok/0005.html",
                           "https://runeberg.org/bok/0006.html"]


def test_runeberg_running_headers_removed_before_merging():
    f = runeberg_fetcher()
    f.pages["https://runeberg.org/bok/0006.html"] = page(
        "KRISTUSLEGENDER\n\n8. — La g er lö fy Kristuslegender. J23 KR\n\nfortsätter på nästa sida.\n")
    src = runeberg.fetch("https://runeberg.org/bok/0005.html", f)
    assert src.sections[0][1][1] == "Sista stycket börjar här och fortsätter på nästa sida."
    assert not any("KRISTUS" in p.upper() for p in src.sections[0][1])


def test_is_running_header():
    assert runeberg.is_running_header("KRISTUSLEGENDER")
    assert runeberg.is_running_header("FÄGEL RÖDBRÖST")
    assert not runeberg.is_running_header("HOSIANNA!")
    assert not runeberg.is_running_header("Det var en gång en fågel.", "Kristuslegender")
    assert runeberg.is_running_header("12 Kristuslegender", "Kristuslegender")


def test_runeberg_rejects_non_story_start_and_bad_urls():
    with pytest.raises(FetchError):
        runeberg.fetch("https://runeberg.org/bok/0006.html", runeberg_fetcher())
    with pytest.raises(FetchError):
        runeberg.fetch("https://runeberg.org/bok/", runeberg_fetcher())


def test_parse_index_titles_and_pages():
    entries = runeberg.parse_index(INDEX)
    story = next(e for e in entries if e["first"] == "0005")
    assert story["title"] == "Den heliga natten" and story["pages"] == ["0005", "0006"]
    assert next(e for e in entries if e["first"] == "0001")["pages"] == ["0001"]


def test_strip_title_variants():
    t = "Fågel Rödbröst"
    assert runeberg.strip_title(["FÅGEL RÖDBRÖST.", "Text."], t) == ["Text."]
    assert runeberg.strip_title(["FÅGEL RÖDBRÖST. Det var en gång.", "Mer."], t) == ["Det var en gång.", "Mer."]
    assert runeberg.strip_title(["Fågel Rödbröst var liten."], t) == ["Fågel Rödbröst var liten."]  # not a printed title
    assert runeberg.strip_title(["Annat."], t) == ["Annat."]
    assert runeberg.strip_title(["FÅGEL RÖDBRÖST", "FÅGEL RÖDBRÖST.", "Text."], t) == ["Text."]  # printed twice


def test_decode_html_honours_declared_charset():
    raw = '<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">Hjälp'.encode("latin-1")
    assert decode_html(raw).endswith("Hjälp")
    assert decode_html("<p>åäö</p>".encode("utf-8")) == "<p>åäö</p>"


def test_join_lines():
    assert join_lines("sol-", "gubbe") == "solgubbe"
    assert join_lines("fem-", "och sex") == "fem- och sex"
    assert join_lines("Han", "gick") == "Han gick"


def test_wikipedia_sections_and_fetch():
    text = "Intro text.\n\n== Historia ==\nEn mening.\n\n== Källor ==\nSkippas.\n=== Del ===\nUnder."
    assert wikipedia.parse_sections(text) == [(None, ["Intro text."]), ("Historia", ["En mening."]),
                                              ("Del", ["Under."])]
    api = "https://sv.wikipedia.org/w/api.php"
    payload = json.dumps({"query": {"pages": {"1": {"title": "Test ämne", "extract": text}}}})
    src = wikipedia.fetch("https://sv.wikipedia.org/wiki/Test_%C3%A4mne", FakeFetcher({api: payload}))
    assert src.title == "Test ämne" and src.history_url.endswith("title=Test_ämne&action=history")


def test_dispatch_by_domain():
    assert source_module("https://sv.wikipedia.org/wiki/X") is wikipedia
    assert source_module("https://runeberg.org/bok/0005.html") is runeberg
    with pytest.raises(FetchError):
        source_module("https://www.svt.se/nyheter/x")
