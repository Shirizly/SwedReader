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
- `pipeline/` : Python package/CLI (`python -m pipeline run|publish|serve|list`). One module per step: fetch, tokenize, align/glossary, translate, assemble, publish, db.
- `scripts/` : small standalone debug scripts (`align_debug.py [layer] ["Swedish sentence" ...]` prints word alignments).
- `tests/` : pytest tests and fixtures (offline), `tests/fixtures/sample-fixture.json` is a hand-made reader fixture.
- `data/public/` : generated documents eligible for publishing (committed). `data/private/` : git-ignored, never published; also holds the SQLite log `pipeline.db`.
- `sources.yaml` : domain → lane (`public`/`private`), licence, attribution.
- `pipeline.db` : SQLite log (source URL, date loaded, word count, lane, status), at `data/private/pipeline.db`.
- `implementation_plan.md`, `basic_plan.md` : plans.

## Rules

- **Two lanes:** every document gets a `lane` from its source domain. `8sidor.se`, `svt.se` and unknown domains are `private` (default-deny); private output is never copied into `reader/content/` or committed. Public documents must carry licence/attribution fields (Wikipedia is CC BY-SA 4.0: credit, link to history, licence, note of changes; content stays share-alike).
- **Translation:** machine translation is the base. Sentences are translated whole (OPUS-MT `Helsinki-NLP/opus-mt-sv-en`, behind a swappable `Translator` interface). Word meanings come from alignment with the sentence translation, then isolated word translation, then an optional dictionary (Folkets lexikon).
- **Reader:** build DOM with `textContent` (never `innerHTML` for document data); no network calls at read time except the site's own files.
- Use the built-in file tools for edits; use the shell only to run programs.
- Test each component with a simple script first, show its output, then wire it into the pipeline. Mark steps that need human review (reader feel on phone, translation quality, alignment quality) and ask the user.

## Run

- Pipeline (from repo root, env `translatepipe`): `python -m pipeline run <url>`, `publish` (copies data/public → reader/content), `list`, `serve [port]` (reader + private docs, local only). Tests: `python -m pytest tests`.
- Reader alone: `python3 -m http.server 8765 --bind 127.0.0.1` from `reader/`. Hard-reload to avoid cached CSS/JS.
