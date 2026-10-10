---
name: translate-pipeline
description: Work on the TranslatePipeline project (Swedish reader with word/sentence translation, Python pipeline, GitHub Pages). Use for any task that edits, runs, or tests the pipeline, reader, or content in this repository.
---

# TranslatePipeline

Swedish-to-English learning reader: a static web app (GitHub Pages) with instant word and sentence translation, fed by a local Python pipeline. The full plan is in `implementation_plan.md`; the original idea is in `basic_plan.md`.

## Environment (always)

- Use the conda env **`translatepipe`** (Python 3.11) for every Python command: `conda run -n translatepipe python ...` or `conda activate translatepipe` first. Never use the base env or install into other envs.
- Installed packages: requests, pyyaml, jsonschema, pytest, spacy (+ `sv_core_news_sm`), transformers, sentencepiece, torch. Later: `simalign`. Add new dependencies to the env deliberately and record them in the project's dependency file.
- Ordinary tests must not download models or use the network.

## Structure

- `reader/` : static site (plain HTML/CSS/JS, no build step). `index.html`, `app.js`, `style.css`, `content/` (published documents + `index.json`). Relative paths only (works under a Pages subpath).
- `pipeline/` : Python package/CLI (`python -m pipeline run <url> [<url> ...]|publish|serve|list|build-dict|review <id>`). One module per step: `sources/` (one module per site: `wikipedia.py`, `runeberg.py`; shared `base.py` with polite fetcher and encoding handling; add a module and register it in `sources/__init__.py` for a new site), `segment.py`, `translate.py` (sentence/word translation + attention alignment), `dictionary.py` (Folkets lexikon → SQLite), `qa.py` (compares aligned meanings with fallbacks, sets `check` flags), `review.py` (HTML/JSON report in `data/private/review/`), `assemble.py`, `publish.py`, `guard.py`, `db.py`, `config.py`.
- `scripts/` : small standalone debug scripts (`align_debug.py [layer] ["Swedish sentence" ...]` prints word alignments).
- `tests/` : pytest tests and fixtures (offline), `tests/fixtures/sample-fixture.json` is a hand-made reader fixture.
- `data/public/` : generated documents eligible for publishing (committed). `data/private/` : git-ignored, never published; also holds the SQLite log `pipeline.db`.
- `sources.yaml` : domain → lane (`public`/`private`), licence, attribution.
- `pipeline.db` : SQLite log (source URL, date loaded, word count, lane, status), at `data/private/pipeline.db`.
- `implementation_plan.md`, `basic_plan.md` : plans.

## Rules

- **Two lanes:** every document gets a `lane` from its source domain. `8sidor.se`, `svt.se` and unknown domains are `private` (default-deny); private output is never copied into `reader/content/` or committed. Public documents must carry licence/attribution fields (Wikipedia is CC BY-SA 4.0: credit, link to history, licence, note of changes; content stays share-alike).
- **Word meanings (reader order):** aligned in-context meaning (`in_context`, groups) first; if QA flagged it `weak`/`wide` it is ignored. Fallbacks per `lemma|pos` in the document `glossary`: `dict` (Folkets lexikon, preferred) then `mt` (isolated machine translation, noisy). QA statuses: agree, diff, wide, weak, conflict, no_alignment, no_reference (see `qa.py`); review the flagged ones with `python -m pipeline review <id>` (report in `data/private/review/`). Run `python -m pipeline build-dict` once to build `data/private/dict.db` before `run`.
- **Translation:** machine translation is the base. Sentences (and the title) are translated whole (OPUS-MT `Helsinki-NLP/opus-mt-sv-en`, behind a swappable `Translator` interface).
- **Reader:** build DOM with `textContent` (never `innerHTML` for document data); no network calls at read time except the site's own files.
- Use the built-in file tools for edits; use the shell only to run programs.
- Test each component with a simple script first, show its output, then wire it into the pipeline. Mark steps that need human review (reader feel on phone, translation quality, alignment quality) and ask the user.

## Run

- Pipeline (from repo root, env `translatepipe`): `python -m pipeline run <url> [<url> ...]` (models load once; the translator uses CUDA when available), `publish` (copies data/public → reader/content), `list`, `serve [port]` (reader + private docs, local only). Runeberg stories: use the URL of the story's first page, e.g. `https://runeberg.org/kristleg/0005.html` (2 s crawl delay is enforced). Tests: `python -m pytest tests`.
- Reader alone: `python3 -m http.server 8765 --bind 127.0.0.1` from `reader/`. Hard-reload to avoid cached CSS/JS.
