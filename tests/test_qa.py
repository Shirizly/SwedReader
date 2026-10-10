import json
import sqlite3

import pytest
import spacy
from spacy.language import Language
from pipeline import dictionary, qa, review
from pipeline.assemble import build_document, clean_mt, validate
from pipeline.config import resolve_lane
from pipeline.translate import join_target_words

SOURCES = {"public": [{"domain": "wikipedia.org", "license": "L", "license_url": "https://l", "attribution": "A"}]}


def lemmas(text):
    """Tiny English lemmatizer for tests: lowercase words, strip simple suffixes."""
    irregular = {"told": "tell", "telling": "tell", "was": "be", "went": "go", "gave": "give", "had": "have"}
    out = []
    for w in "".join(c if c.isalpha() else " " for c in text.lower()).split():
        out.append(irregular.get(w, w[:-1] if w.endswith("s") and len(w) > 3 else w))
    return out


def entry(mt=None, dic=None):
    e = {}
    if mt:
        e["mt"] = mt
    if dic:
        e["dict"] = dic
    return e


# --- assess ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("aligned,entries,status", [
    ("telling", [entry("tell", ["narrate", "relate"])], "agree"),           # lemma match (telling/tell)
    ("the car", [entry("car")], "agree"),                                      # stop words ignored
    ("capital", [entry("capital city")], "agree"),
    ("had", [entry("have:".rstrip(":"))], "agree"),                            # auxiliaries are real translations
    ("when", [entry(None, ["then", "when"])], "agree"),                        # so are adverbs
    ("grandmother", [entry("grandma")], "agree"),                              # shared 5+ letter prefix
    ("me", [entry("tell", ["narrate"])], "weak"),                              # content word aligned to a pronoun
    ("bridge", [entry("tell", ["narrate"])], "diff"),
    ("story … true", [entry("fairy tale", ["tale"])], "wide"),                 # scattered alignment
    ("a sailor cold weather lake", [entry("sea trawls")], "wide"),             # very long alignment
    ("tomorrow", [entry()], "no_reference"),
    ("", [entry("tell", ["narrate"])], "conflict"),                            # fallbacks disagree, no alignment
    ("", [entry("tell", ["telling"])], "no_alignment"),                        # fallbacks agree, no alignment
    ("", [entry("tell")], "no_alignment"),
])
def test_assess(aligned, entries, status):
    assert qa.assess(aligned, entries, lemmas) == status


def test_clean_mt_drops_junk():
    assert clean_mt("ha", "have:") == "have"
    assert clean_mt("bil", "Car.") == "Car"
    assert clean_mt("saga", "I'm sorry. I'm sorry. I'm sorry") == ""     # hallucinated repeats
    assert clean_mt("sutto", "sutto") == ""                              # untranslated copy
    assert clean_mt("Stockholm", "Stockholm") == "Stockholm"             # names legitimately copy
    assert clean_mt("x", "one two three four five") == ""


def test_join_target_words_marks_gaps():
    text = "story is so true"
    words = [(0, 5), (6, 8), (9, 11), (12, 16)]
    assert join_target_words([0, 3], words, text) == "story … true"
    assert join_target_words([1, 2], words, text) == "is so"
    assert join_target_words([], words, text) == ""


def test_similar():
    assert qa.similar("capital", "capitals") and qa.similar("walk", "walk")
    assert not qa.similar("car", "bridge")
    assert not qa.similar("go", "good")  # short words must match exactly


# --- annotate_sentence ----------------------------------------------------------------------------------

def sentence():
    toks = [
        {"text": "Hon", "lemma": "hon", "is_word": True, "ws": " ", "pos": "PRON", "in_context": "she"},
        {"text": "berättade", "lemma": "berätta", "is_word": True, "ws": " ", "pos": "VERB", "in_context": "told"},
        {"text": "och", "lemma": "och", "is_word": True, "ws": " ", "pos": "CCONJ", "in_context": "and"},
        {"text": "berättade", "lemma": "berätta", "is_word": True, "ws": "", "pos": "VERB", "in_context": "me"},
    ]
    return {"id": "s0", "text": "x", "translation": "y", "tokens": toks, "groups": []}


def test_annotate_flags_the_bad_alignment_only():
    glossary = {"berätta|VERB": entry("tell", ["narrate"]), "hon|PRON": entry("she")}
    s = sentence()
    stats = qa.annotate_sentence(s, glossary, lemmas)
    assert "check" not in s["tokens"][1] and s["tokens"][3]["check"] == "weak"
    assert "check" not in s["tokens"][0]  # function words are not assessed
    assert dict(stats) == {"agree": 1, "weak": 1}


def test_annotate_group_uses_members_fallbacks():
    toks = [{"text": "gav", "lemma": "ge", "is_word": True, "ws": " ", "pos": "VERB"},
            {"text": "upp", "lemma": "upp", "is_word": True, "ws": "", "pos": "ADV"}]
    s = {"id": "s", "text": "gav upp", "translation": "gave up", "tokens": toks,
         "groups": [{"token_ids": [0, 1], "in_context": "gave up"}]}
    glossary = {"ge|VERB": entry("give", ["give"]), "upp|ADV": entry("up")}
    qa.annotate_sentence(s, glossary, lemmas)
    assert "check" not in s["groups"][0]
    s["groups"][0]["in_context"] = "bridge"
    qa.annotate_sentence(s, glossary, lemmas)
    assert s["groups"][0]["check"] == "diff"


# --- dictionary -----------------------------------------------------------------------------------------

XML = """<?xml version="1.0" encoding="utf-8"?>
<dictionary>
<word class="vb" lang="sv" value="berätta"><translation value="relate" /><translation value="tell" />
<paradigm><inflection value="berättar" /><inflection value="berättade" /></paradigm></word>
<word class="nn" lang="sv" value="rätt"><translation value="course, dish" /></word>
<word class="jj" lang="sv" value="rätt"><translation value="right" /></word>
<word class="nn" lang="sv" value="tom"></word>
</dictionary>"""


@pytest.fixture
def dic(tmp_path):
    xml = tmp_path / "d.xml"
    xml.write_text(XML, encoding="utf-8")
    assert dictionary.build(xml, tmp_path / "d.db") == 3  # the entry without translations is skipped
    return dictionary.Dictionary(tmp_path / "d.db")


def test_dictionary_lookup_prefers_matching_class_and_splits_glosses(dic):
    assert dic.lookup("rätt", "ADJ") == ["right"]
    assert dic.lookup("rätt", "NOUN") == ["course", "dish"]
    assert dic.lookup("rätt", "") == ["course", "dish", "right"]


def test_dictionary_falls_back_to_inflected_forms_and_surface(dic):
    assert dic.lookup("berättade", "VERB") == ["relate", "tell"]   # via the forms table
    assert dic.lookup("xyz", "VERB", surface="Berätta") == ["relate", "tell"]
    assert dic.lookup("finnsinte", "NOUN") == []


def test_dictionary_rebuild_is_idempotent(tmp_path):
    xml = tmp_path / "d.xml"
    xml.write_text(XML, encoding="utf-8")
    dictionary.build(xml, tmp_path / "d.db")
    dictionary.build(xml, tmp_path / "d.db")
    n = sqlite3.connect(str(tmp_path / "d.db")).execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    assert n == 5


# --- assembly with fallbacks, title and review report ---------------------------------------------------

class Translator:
    name = "fake"

    def translate(self, sentences):
        return ["She told me." if "Hon" in s else f"EN {s}" for s in sentences]

    def translate_words(self, words):
        return ["tell" if w == "berätta" else f"{w}-en" for w in words]

    def align(self, src_text, tokens, tgt_text):
        ctx = []
        for t in tokens:
            if t["text"] == "berättade":
                ctx.append("me")
            else:
                ctx.append(t["text"].lower() if t["is_word"] else "")
        return ctx, []


class StubDictionary:
    info = {"name": "Stub", "license": "X"}

    def lookup(self, lemma, pos="", surface=""):
        return ["narrate"] if lemma == "berätta" else []


LEXICON = {"berättade": ("berätta", "VERB"), "Hon": ("hon", "PRON")}


@Language.component("set_lexicon")
def set_lexicon(doc):
    for t in doc:
        if t.text in LEXICON:
            t.lemma_, t.pos_ = LEXICON[t.text]
    return doc


@pytest.fixture(scope="module")
def nlp():
    n = spacy.blank("sv")
    n.add_pipe("set_lexicon")
    return n


def test_build_document_has_title_glossary_and_flags(nlp):
    url = "https://sv.wikipedia.org/wiki/Test"
    doc = build_document(url, resolve_lane(url, SOURCES), "Berättelsen om natten", [(None, ["Hon berättade."])],
                         nlp, Translator(), author="Ann", dictionary=StubDictionary(), lemmas=lemmas,
                         progress=lambda *_: None)
    validate(doc)
    assert doc["author"] == "Ann" and doc["dictionary"]["name"] == "Stub"
    ts = doc["title_sentence"]
    assert ts["id"] == "t" and [t["text"] for t in ts["tokens"] if t["is_word"]] == ["Berättelsen", "om", "natten"]
    assert ts["translation"] == "EN Berättelsen om natten"
    assert doc["word_count"] == 2  # the title is not counted
    assert doc["glossary"]["berätta|VERB"] == {"mt": "tell", "dict": ["narrate"]}
    assert "hon|PRON" in doc["glossary"] and "dict" not in doc["glossary"]["hon|PRON"]
    verb = doc["paragraphs"][0]["sentences"][0]["tokens"][1]
    assert verb["in_context"] == "me" and verb["check"] == "weak"   # the aligned "me" is flagged for review
    assert doc["qa"] == {"weak": 1}


def test_review_report_lists_flagged_items(nlp, tmp_path):
    doc = {"id": "d", "title": "T", "translator": "fake", "qa": {"weak": 1},
           "glossary": {"berätta|VERB": entry("tell", ["narrate"])}, "paragraphs": [{"sentences": [sentence()]}]}
    s = doc["paragraphs"][0]["sentences"][0]
    qa.annotate_sentence(s, doc["glossary"], lemmas)
    items = review.collect(doc)
    assert [(i["status"], i["words"], i["aligned"], i["mt"], i["dict"]) for i in items] == [
        ("weak", "berättade", "me", ["tell"], ["narrate"])]
    path, n = review.write_report(doc, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert n == 1 and "<mark>berättade</mark>" in text and "articles/pronouns/prepositions" in text
    assert json.loads((tmp_path / "d.json").read_text(encoding="utf-8"))[0]["status"] == "weak"
