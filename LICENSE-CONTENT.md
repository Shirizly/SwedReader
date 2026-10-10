# Content licence

The code in this repository is MIT licensed (see `LICENSE`).

The **content** in `data/public/` and `reader/content/` (the processed texts, their tokenization, word
alignments and machine translations) is derived from the sources listed in each document's `source_url`,
`attribution` and `license` fields. Texts derived from Wikipedia are licensed under
[Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)](https://creativecommons.org/licenses/by-sa/4.0/).

Changes made: the text was split into sentences and words, lemmatized, and machine-translated into English
(Helsinki-NLP OPUS-MT), with word-level meanings derived by alignment. Each document links to the original page and
its page history (the list of authors).

Private-lane sources (e.g. 8 Sidor, SVT) are never published in this repository.
