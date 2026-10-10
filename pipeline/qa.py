"""Systematic comparison of the aligned (in-context) word meanings against the fallbacks
(isolated machine translation and dictionary glosses), to flag likely errors for human review.

Statuses for a content word (noun, verb, adjective, adverb, proper noun):
  agree         the aligned meaning shares a lemma with a fallback
  diff          the aligned meaning shares nothing with the fallbacks            -> check
  wide          like diff, but the aligned English is scattered ("…") or long    -> check
  weak          the aligned English is only articles/pronouns/prepositions       -> check, reader ignores it
  conflict      no alignment, and the two fallbacks disagree with each other      -> check
  no_alignment  no aligned meaning (a fallback is shown instead)
  no_reference  aligned, but nothing to compare it with
Function words are not assessed.
"""
import difflib
import os
from collections import Counter

CONTENT_POS = {"NOUN", "VERB", "ADJ", "ADV", "PROPN"}
REVIEW = {"diff", "wide", "weak", "conflict"}
GAP = "…"
WIDE_WORDS = 4
# Only words that carry no meaning of their own for a content word: articles, prepositions, conjunctions,
# personal pronouns. Auxiliaries and adverbs (had, when, so, not) are meaningful translations and stay.
STOP = {"the", "a", "an", "of", "to", "and", "or", "in", "on", "at", "by", "for", "with", "it", "its", "that",
        "this", "these", "those", "i", "me", "my", "you", "your", "he", "him", "his", "she", "her", "we", "us",
        "our", "they", "them", "their", "as", "from", "s"}


def content_lemmas(text, lemmas):
    """Content-word lemmas of an English text. `lemmas` maps text -> list of lowercase lemmas."""
    return [w for w in lemmas(text) if w not in STOP and len(w) > 1]


def similar(a, b):
    if a == b:
        return True
    if min(len(a), len(b)) < 4:
        return False
    if a in b or b in a:
        return True
    prefix = len(os.path.commonprefix([a, b]))
    return prefix >= 5 or difflib.SequenceMatcher(None, a, b).ratio() >= 0.82


def _fallback_sets(entries, lemmas):
    mt, dic = set(), set()
    for e in entries:
        mt.update(content_lemmas(e["mt"], lemmas) if e.get("mt") else [])
        for g in e.get("dict", []):
            dic.update(content_lemmas(g, lemmas))
    return mt, dic


def assess(aligned, entries, lemmas):
    """Status of an aligned meaning given the glossary entries of the word(s) it covers."""
    mt, dic = _fallback_sets(entries, lemmas)
    if not aligned:
        return "conflict" if mt and dic and not any(similar(a, b) for a in mt for b in dic) else "no_alignment"
    own = set(content_lemmas(aligned.replace(GAP, " "), lemmas))
    if not own:
        return "weak"
    refs = mt | dic
    if not refs:
        return "no_reference"
    if any(similar(a, r) for a in own for r in refs):
        return "agree"
    return "wide" if GAP in aligned or len(own) >= WIDE_WORDS else "diff"


def annotate_sentence(sentence, glossary, lemmas):
    """Set `check` on tokens/groups that need review; return a Counter of statuses for content words."""
    stats, grouped = Counter(), set()
    tokens = sentence["tokens"]

    def entry(i):
        t = tokens[i]
        return glossary.get(f"{t['lemma']}|{t.get('pos', '')}", {})

    for g in sentence["groups"]:
        members = [i for i in g["token_ids"] if tokens[i].get("pos") in CONTENT_POS]
        grouped.update(g["token_ids"])
        if not members:
            continue
        status = assess(g["in_context"], [entry(i) for i in members], lemmas)
        stats[status] += 1
        if status in REVIEW:
            g["check"] = status
    for i, t in enumerate(tokens):
        if i in grouped or t.get("pos") not in CONTENT_POS:
            continue
        status = assess(t.get("in_context", ""), [entry(i)], lemmas)
        stats[status] += 1
        if status in REVIEW:
            t["check"] = status
    return stats
