---
name: translate-pipeline
description: Work on the TranslatePipeline project (Swedish reader with word/sentence translation, Python pipeline, GitHub Pages). Use for any task that edits, runs, or tests the pipeline, reader, or content in this repository.
---

# TranslatePipeline

Swedish-to-English learning reader: a static web app (GitHub Pages) with instant word and sentence translation, fed by a local Python pipeline. Current structure is documented in `docs/architecture.md`; the roadmap is in `docs/implementation_plan.md`, and the original idea is in `docs/basic_plan.md`.

## Environment (always)

- Use the conda env **`translatepipe`** (Python 3.11) for every Python command: `conda run -n translatepipe python ...` or `conda activate translatepipe` first. Never use the base env or install into other envs.
- Installed packages are pinned in `requirements.txt`: requests, pyyaml, jsonschema, pytest, spacy, transformers, sentencepiece, and torch. The Swedish spaCy model is installed separately; the English spaCy model is used for QA. Add new dependencies deliberately and record them in the project's dependency file.
- Ordinary tests must not download models or use the network.

## Structure

- `reader/` : static site (plain HTML/CSS/JS, no build step). `index.html`/`home.js` is the library/dashboard; `reader.html`/`app.js` displays a document; `quiz.html`/`quiz.js` reviews due vocabulary; `tracker.js` stores browser-local progress; `content/` contains published JSON and `index.json`. Relative paths support a Pages subpath.
- `pipeline/` : Python package and CLI. `__main__.py` orchestrates `run`, `publish`, `serve`, `list`, `build-dict`, and `review`; `sources/` currently supports Wikipedia and Project Runeberg, using shared polite fetching in `sources/base.py`. `segment.py` tokenizes and splits sentences; `translate.py` translates sentences and aligns words; `dictionary.py` imports/queries Folkets lexicon; `qa.py` marks suspect alignments; `assemble.py` builds, validates, and atomically writes documents; `db.py` logs runs; `review.py` writes HTML/JSON reports; `publish.py` publishes public content and serves local private files; `guard.py` checks deployed content.
- `scripts/` : `align_debug.py` inspects alignments; `view_review.py` lists, regenerates, and opens review reports.
- `tests/` : offline pytest tests and fixtures.
- `data/public/` : generated documents eligible for publishing. `data/private/` : git-ignored documents, review reports, dictionary source/database, and SQLite run log.
- `sources.yaml` : domain → lane (`public`/`private`), licence, attribution. Lane policy is separate from extractor support.
- `.github/workflows/pages.yml` : checks published content and deploys only `reader/`.
- `docs/` : `architecture.md` documents the current structure; `implementation_plan.md` is the roadmap; `user_guide.md` documents local use; `basic_plan.md` and `Extension_plan.md` preserve the project plans.

## Rules

- **Two lanes:** every document gets a `lane` from its source domain. `8sidor.se`, `svt.se` and unknown domains are `private` (default-deny); private output is never copied into `reader/content/` or committed. Public documents must carry licence/attribution fields (Wikipedia is CC BY-SA 4.0: credit, link to history, licence, note of changes; content stays share-alike).
- **Word meanings:** the reader word panel prefers usable contextual alignment (`in_context`, groups), then dictionary glosses and isolated machine translation. QA-flagged `weak`/`wide` alignments are ignored. Review cards intentionally use dictionary glosses first, then isolated machine translation, never group alignments. Dictionary lookup prefers exact surface forms and inflections before ambiguous lemmas. QA statuses are defined in `pipeline/qa.py`; use `python scripts/view_review.py <id>` to regenerate and open a report, or `python -m pipeline review <id>` to regenerate it only. Run `python -m pipeline build-dict` to build `data/private/dict.db` before processing documents.
- **Translation:** machine translation is the base. Sentences (and the title) are translated whole (OPUS-MT `Helsinki-NLP/opus-mt-sv-en`, behind a swappable `Translator` interface).
- **Reader:** build DOM with `textContent` (never `innerHTML` for document data); no network calls at read time except the site's own files. Learning progress and spaced-repetition cards stay in browser `localStorage`.
- **Review cards:** use all glossary dictionary meanings first and isolated machine translation only as a fallback. Never use sentence-level alignments or group meanings as standalone flashcard answers; label fallback machine translations.
- Use the built-in file tools for edits; use the shell only to run programs.
- Test each component with a simple script first, show its output, then wire it into the pipeline. Mark steps that need human review (reader feel on phone, translation quality, alignment quality) and ask the user.

## Run

- Pipeline (from repo root, env `translatepipe`): `conda run -n translatepipe python -m pipeline run <url> [<url> ...]` (models load once; the translator uses CUDA when available), or use `publish`, `list`, `serve [port]`, `build-dict`, and `review <id>`. Runeberg stories: use the URL of the story's first page, e.g. `https://runeberg.org/kristleg/0005.html` (2 s crawl delay is enforced). Tests: `conda run -n translatepipe python -m pytest tests`.
- Reader alone: `conda run -n translatepipe python -m http.server 8765 --bind 127.0.0.1` from `reader/`. The library lists published documents; `reader.html?story=content/<id>.json` opens a document and `quiz.html` reviews due words. Hard-reload to avoid cached CSS/JS.
