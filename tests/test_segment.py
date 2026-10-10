import pytest
import spacy

from pipeline.segment import segment, sentence_text


@pytest.fixture(scope="module")
def nlp():
    return spacy.blank("sv")


def split(nlp, text):
    return [sentence_text(s) for s in segment(nlp, text)]


def test_no_split_at_comma(nlp):
    text = "Antalet invånare är strax över 1 miljon, medan det finns över 1,6 miljoner."
    assert split(nlp, text) == [text]


def test_basic_two_sentences(nlp):
    assert split(nlp, "Det regnar. Jag går hem.") == ["Det regnar.", "Jag går hem."]


def test_abbreviation_followed_by_lowercase(nlp):
    text = "Många städer, t.ex. Malmö och Göteborg, är stora."
    assert split(nlp, text) == [text]


def test_ordinal_date_followed_by_lowercase(nlp):
    text = "Den 5. maj var det kallt."
    assert split(nlp, text) == [text]


def test_number_ending_sentence_then_capital(nlp):
    assert split(nlp, "Staden grundades på 1200-talet. Sedan växte den.") == [
        "Staden grundades på 1200-talet.", "Sedan växte den."]


def test_closing_paren_and_quote_stay_with_sentence(nlp):
    assert split(nlp, 'Han sa "hej." Hon svarade (snabbt). Sedan gick de.') == [
        'Han sa "hej."', "Hon svarade (snabbt).", "Sedan gick de."]


def test_question_and_exclamation(nlp):
    assert split(nlp, "Vad gör du? Jag läser! Bra.") == ["Vad gör du?", "Jag läser!", "Bra."]


def test_newline_after_terminal_forces_break_even_before_lowercase(nlp):
    assert split(nlp, "Första raden.\nandra raden.") == ["Första raden.", "andra raden."]


def test_newline_without_terminal_does_not_break(nlp):
    text = "Några länder:\nUSA,\nNorge,\nJapan."
    assert split(nlp, text) == [text]


def test_reconstruction_is_exact(nlp):
    text = "Första meningen.\nAndra meningen, med komma. Tredje (2022)."
    sents = segment(nlp, text)
    assert "".join(t["text"] + t["ws"] for s in sents for t in s).strip() == text
