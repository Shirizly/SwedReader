# Current architecture

This document describes the code that exists today. For the original implementation roadmap see [implementation_plan.md](implementation_plan.md); for commands and day-to-day usage see [user_guide.md](user_guide.md).

## Repository layout

```text
pipeline/                 Python processing pipeline and CLI
  sources/                Wikipedia and Project Runeberg extractors
  __main__.py              CLI and end-to-end run orchestration
  config.py                Source-lane and licence resolution
  segment.py               Swedish tokenization and sentence boundaries
  translate.py             OPUS-MT sentence translation and word alignment
  dictionary.py            Folkets lexicon SQLite import and lookup
  qa.py                    Alignment/fallback comparison and review flags
  assemble.py              Glossary, document JSON, schema validation, atomic write
  db.py                    SQLite processing log
  review.py                Flagged-word HTML and JSON reports
  publish.py               Public publishing and local reader server
  guard.py                 Published-content safety check

reader/                    Static HTML, CSS, and JavaScript application
  index.html               Library and learning dashboard
  home.js                  Public/local document indexes and dashboard
  reader.html              Document-reading view
  app.js                   Document rendering and word/sentence interaction
  quiz.html, quiz.js       Due-word flashcard review
  tracker.js               Browser-local exposure, lookups, and SRS state
  content/                 Published public JSON documents and index.json
  licenses.html            Site-wide licence information

scripts/                   Standalone helper scripts
  align_debug.py           Inspect source/target word alignment
  view_review.py           List, regenerate, and open word-review reports

tests/                     Offline pytest suite and fixtures
data/public/               Generated public documents eligible for publishing
data/private/              Local-only documents, models' source data, DBs, and reports
docs/                      Architecture, roadmap, user guide, and original plans
.github/workflows/pages.yml  Public reader deployment and content guard
```

## Processing and publishing

1. `python -m pipeline run <url> [<url> ...]` resolves the source lane before fetching. `sources.yaml` defines publication policy; `pipeline/sources/` currently has extractors for Wikipedia and Project Runeberg.
2. The pipeline tokenizes and segments Swedish text, translates complete sentences, aligns sentence words, and builds per-lemma/POS fallbacks from isolated machine translation and Folkets lexicon. QA compares alignments with those fallbacks and marks likely errors.
3. The assembled document is schema-validated, written atomically to `data/public/` or `data/private/`, recorded in `data/private/pipeline.db`, and used to generate local HTML/JSON review reports in `data/private/review/`.
4. `python -m pipeline publish` copies only eligible public documents into `reader/content/` and rebuilds `reader/content/index.json`. `python -m pipeline.guard` checks the published set.
5. `python -m pipeline serve [port]` serves the static reader and exposes private documents through a separate `/content-private/` index, bound to localhost. The GitHub Pages workflow deploys `reader/` only.

The main CLI also provides `publish`, `list`, `serve`, `build-dict`, and `review <document-id>`. The review command regenerates reports but does not launch a browser; `python scripts/view_review.py <document-id>` regenerates and opens one.

## Document contract

Each JSON document contains source and licence metadata, a title sentence, paragraphs and sentences, a lemma/POS glossary, and optional QA counts. Sentence tokens preserve surface text, lemma, POS, and trailing whitespace; aligned English meanings are stored on tokens or in sentence-level groups for multi-token alignments. The reader consumes this precomputed data and makes no translation requests.

Meanings have distinct roles:

- The reader's word panel prefers a usable contextual alignment, then dictionary glosses, then isolated machine translation.
- QA flags weak, wide, conflicting, or differing alignments for human review.
- Review cards deliberately exclude sentence/group alignments: they show dictionary glosses first and isolated machine translation only as a labelled fallback.
- Dictionary lookup prefers an exact surface-form or inflection entry before falling back to a potentially ambiguous model lemma.

## Reader state and privacy

The library reads the public `content/index.json`; the local server may also provide `content-private/index.json`. Reading a document records encountered lemmas and stories in browser `localStorage`. Selecting words records lookups and schedules Leitner reviews. This data is local to the browser profile and page origin; it is not sent to the pipeline.

`data/private/` is git-ignored and must not be published. Public source and licence fields are checked during publishing and by the deployment guard. The web application is plain static HTML/CSS/JS with relative paths so it works under a GitHub Pages project subpath.

## Current boundaries

- The reader and pipeline consume generated JSON; the deployed site does not run Python or translate on demand.
- `sources.yaml` includes private-lane policy for sources that do not yet have extractors. Lane policy and extraction support are separate.
- Audio synthesis, audio assets, and synchronized highlighting are not implemented.
- Lemmatization and automatic word alignment are model-derived and can be wrong; generated content and review reports may need regeneration after pipeline logic or dictionary changes.
