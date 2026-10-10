# Phase 1 Implementation Plan

The goal is a **static reader web app (GitHub Pages) where a learner reads a Swedish text and gets instant translations**: tap/click any word for its base form and English meaning, and any sentence for its full English translation. Everything is precomputed, so the reader needs no backend or network calls at read time. The Python pipeline (scrape → process → translate → upload) exists to feed the reader, so the reader is built first against a hand-made fixture and the pipeline is then built to produce exactly the data it needs.

Scope for now: no learner levels. The first end-to-end input is the single URL `https://sv.wikipedia.org/wiki/Stockholm`. RSS discovery and further sources are deferred (see "Deferred").

## Two lanes

Every document belongs to exactly one lane, determined solely by its source:

- **Public lane:** sources that may be republished: Project Runeberg and suitable government sources (public domain), and Wikipedia (CC BY-SA 4.0, republishable with the conditions below). Output is eligible for upload to GitHub Pages.
- **Private lane:** sources that must not be republished (`8sidor.se`, `svt.se`). Output is generated and readable locally (see step 9) but is never uploaded or committed to the published branch.

### Licence conditions for the public lane (Wikipedia, Folkets lexikon)

- **Attribution** means every displayed document credits its source: article title, link to the original page, a link to the page history (Wikipedia's author list), the licence name with a link (CC BY-SA 4.0), and a note that the text was changed (tokenized and machine-translated).
- **Share-alike** means that what we publish derived from that text (the translated and annotated document JSON, which includes the machine translations) must itself be offered under the same licence (CC BY-SA 4.0), not under a more restrictive one. This applies to the content only, not to the reader's code, which can have its own licence. If Folkets lexikon is used, its glosses carry the same CC BY-SA obligation (to be verified when the dump is downloaded).
- This is workable for a free public site, so it is built in: each document has `license` (SPDX-style id, e.g. `CC-BY-SA-4.0` or `public-domain`), `license_url`, `attribution`, and `history_url` fields; the reader shows an attribution footer for every document and a site-wide licence page; the repository includes a content licence file for `reader/content/`; and the publish step refuses any public document lacking these fields. (This is a practical reading of the licence, not legal advice.)

Mechanism: a config file (`sources.yaml`) maps domains to a lane and licence/attribution text. The pipeline sets a `lane` field (`public` or `private`) on the document JSON and in the database log. Unknown domains default to `private` (default-deny) until explicitly added to the public list. Private output is written to a separate, git-ignored directory (`data/private/`); public output goes to `data/public/`. The upload step only reads `data/public/` and additionally re-checks the `lane` flag in each file.

## Implementation order

### 1. Define the data contract, lane config, and database schema

- JSON document fields: `id`, `title`, `source_url`, `source_domain`, `lane`, `retrieved_at`, `language_pair` (`sv`→`en`), `word_count`, `attribution`, `license`, `license_url`, `history_url`, `translator`, an optional document-level `glossary` (lemma → list of dictionary glosses, stored once per lemma), and `paragraphs` → `sentences` → `tokens`. Each sentence has `id`, `text`, `translation` (machine translation of the whole sentence, the base translation), and ordered `tokens` with `text`, `lemma`, `is_word`, trailing-whitespace info so the original text can be reconstructed, and an optional `in_context` (the English words in the sentence translation that this word aligns to, from step 6). Token indexes are sentence-local (sentence ID plus position). The reader shows, per word, whichever of `in_context` and `glossary[lemma]` exist, and an explicit "no entry" state when neither does.
- SQLite log (`data/private/pipeline.db`, git-ignored so private source URLs are never committed; standard-library `sqlite3`), table `documents`: `id`, `source_url`, `source_domain`, `lane`, `loaded_at` (ISO timestamp), `word_count`, `output_path`, `content_hash`, `status` (`ok`/`failed`), `published` (0/1). `source_url` is unique so reruns update rather than duplicate.
- `word_count`: count of tokens flagged `is_word` (alphabetic tokens), computed once from the processed tokens, used for both the JSON and the log.
- **Test:** Python unit tests (`pytest`): validate a sample fixture JSON against a JSON Schema (`jsonschema`); lane resolution tests (public domain → `public`, `8sidor.se`/`svt.se` and subdomains → `private`, unknown domain → `private`, lookalike domains such as `notsvt.se` → `private`); database tests on a temporary in-memory/temp-file DB for insert, upsert, and schema creation.
- **Human test required:** Review the private/public domain lists and the JSON field layout before implementation continues.

### 2. Set up the project and test baseline

- Layout: `pipeline/` (package + CLI), `reader/` (static site), `tests/` with fixtures, `data/public/` (committed/published), `data/private/` (git-ignored), `sources.yaml`.
- Pin dependencies (`requests`, `beautifulsoup4`, `spacy`, `transformers`, `sentencepiece`, `torch`, `pyyaml`, `jsonschema`, `pytest`); document explicit model installs (`python -m spacy download sv_core_news_sm`; the OPUS-MT model downloads from Hugging Face on first explicit use). Ordinary tests must not download models or use the network.
- **Test:** Fresh virtual environment from the documented setup; `pytest` passes with only the fixtures.
- **Human test required:** Follow the setup instructions on a clean environment and report unclear or platform-specific steps.

### 3. Build the reader against a hand-made fixture (core deliverable)

- Plain HTML/CSS/JS in `reader/` (no framework, no build step), loading `content/index.json` (list of documents) and then the chosen document via relative paths so it works under a GitHub Pages project subpath. Hand-write a fixture document (~10 sentences of Swedish with plausible lemmas, glosses, and translations, including inflected forms, punctuation, a repeated word, and a word missing from the glossary) in the step 1 format.
- Rendering: build the DOM from paragraphs → sentences → tokens using `textContent` (never `innerHTML`); each word token is a focusable element (`button` or `span tabindex=0`); non-word tokens are plain text; original spacing is reproduced from the whitespace info.
- Word interaction: click/tap or Enter/Space on a word opens a popup/side panel showing the surface form, lemma, the in-sentence translation (`in_context`, labelled as machine-aligned), and any dictionary glosses from `glossary[lemma]` (or an explicit "no entry" message), and highlights the word and its aligned words in the sentence translation. Instant, with no network call.
- Group display: if the clicked word belongs to a sentence `group`, highlight all its tokens and show the shared `in_context` meaning.
- Attribution footer for each document (title, source link, history link, licence link, "changed: tokenized and machine-translated") and a site-wide licence page.
- Sentence interaction: a visible control (and/or a click on the sentence's non-word area or a "translate sentence" key) shows that sentence's English translation, labelled as sentence-level; also a toggle to show all translations under their sentences. Only one popup is open at a time; Escape closes it.
- Mobile-friendly: the panel becomes a bottom sheet on narrow viewports; tap targets are large enough.
- Visible error states for loading failure and malformed documents.
- **Test:** Playwright browser tests against the fixture: render order and exact text reconstruction, word click and keyboard activation, gloss/no-entry display, sentence translation display and toggle, Escape handling, malformed-JSON error state, and no network requests other than the site's own files.
- **Human test required (primary):** Use the reader on desktop and a phone-sized viewport; judge whether the word/sentence lookup feels instant, whether the layout is comfortable for reading, keyboard-only use, and focus visibility. Adjust the design here before the pipeline is built to feed it.

### 4. Scrape: fetch and extract a single URL

- CLI: `python -m pipeline run <url>`. Resolve the lane first (step 1 config), before any fetching or writing.
- Fetching with `requests` using an explicit timeout and a descriptive User-Agent; no crawling beyond the given URL.
- Wikipedia (first target): use the MediaWiki API on the URL's host (`/w/api.php?action=query&prop=extracts&explaintext=1&format=json&titles=Stockholm`) to get clean plain text instead of scraping HTML; section headings arrive as `== Heading ==` lines, which are parsed into headings/paragraphs. Drop trailing non-content sections (e.g. Källor, Referenser, Externa länkar).
- Generic fallback for other sources (Runeberg, 8 Sidor, SVT): fetch HTML and extract with `BeautifulSoup` using a per-domain CSS selector from `sources.yaml` for the article body (strip `nav`, `footer`, `script`, `aside`). Implement only when a second source is added.
- Errors: invalid URL, non-2xx response, timeout, missing/empty text each raise a distinct, clear error and record `status=failed` in the log.
- **Test:** Mocked HTTP responses (`responses` or `unittest.mock`) using saved API JSON and saved HTML fixtures; assert title, paragraph order, heading handling, dropped sections, and each error path. No live network in tests.
- **Human test required:** Run once against the real Stockholm page and compare extracted text with the page (missing sections, stray markup, paragraph order).

### 5. Segment and tokenize (spaCy)

- Load `sv_core_news_sm`; for each paragraph run `nlp(paragraph)` and iterate `doc.sents` and tokens, recording `token.text`, `token.lemma_`, `token.is_alpha` (→ `is_word`), and `token.whitespace_`.
- Fall back to the surface form if the lemma is empty. A missing model raises an error that includes the install command.
- Compute `word_count` here.
- **Test:** Fixed Swedish fixtures: abbreviations (`t.ex.`, `bl.a.`), quotes, numbers/dates, parentheses, compounds, inflected forms (`bilen`→`bil`). Assert sentence boundaries, that joining `text + whitespace` reconstructs the paragraph exactly, each token in exactly one sentence, and word counts. Test the missing-model error path using a mocked loader.
- **Human test required:** Review sentence splits and lemmas for a sample of real sentences from the Stockholm article.

### 6. Word-level translation (machine translation first, dictionary as supplement)

Machine translation is the base for everything. Sentences are translated whole (step 7). For words, translating each word alone is the weak spot: with no context, a word like `fil` (file / lane) gets one arbitrary sense, and very short inputs can make the model produce odd output. So the plan is to derive word meanings from the sentence translation itself, and fall back to isolated translation only where that fails:

1. **Primary: contextual alignment.** Get word alignments between each Swedish sentence and its English translation (first try the Marian model's cross-attention via the translation library; if too noisy, try the `simalign` library, which aligns with multilingual embeddings). Store the aligned English words as the token's `in_context`. Alignment is approximate, so the reader labels it as machine-aligned. Time-box this spike; if quality is poor, drop to step 2. **Spike result (`scripts/04_align.py`):** forced decoding of the existing translation, cross-attention from decoder layer index 4 (of 0–5), source `</s>` dropped, sub-word pieces mapped to words by character offsets, each English word assigned to the Swedish word it attends to most. Layer 4 was clearly better than the all-layer mean (which shifts attention onto neighbouring words). A backward pass groups unmatched Swedish words with the word that owns their strongest English word (`gav upp` → "gave up", `i morgon` → "tomorrow"). `simalign` is not needed unless later checks show problems.
2. **Fallback: isolated word translation.** For each distinct lemma, translate the lemma alone through the same `Translator` and store it in `glossary` marked `machine: true`.
3. **Supplement (optional): full dictionary.** Folkets lexikon (Swedish→English XML dump, CC BY-SA, downloaded explicitly): `python -m pipeline build-dict` parses it with `xml.etree.ElementTree` into SQLite `entries(lemma, pos, gloss, sense_order)` (`dict.db`, git-ignored, licence recorded in a metadata table; re-import replaces rather than duplicates). Up to 3 glosses per lemma ordered by `sense_order` go into `glossary` without the `machine` mark. Missing lemmas get no dictionary entry (never an invented one).

- **Test:** Alignment: fixed sentence pairs with a fake aligner for plumbing (indices map to the right tokens, unaligned tokens get no `in_context`, multiple-to-one and punctuation cases), plus a `slow` real-model test checking a few known pairs. Fallback: fake translator receives lemmas, each lemma translated once. Dictionary: fixture XML covering import and lookup, ordering, Unicode (å, ä, ö), case, missing entry, idempotent re-import.
- Group links: when several Swedish tokens align to the same English words (e.g. `ge upp` → "give up"), store them as one `groups` entry on the sentence (`token_ids`, `in_context`), so the reader can show them together with one shared meaning.
- **Human test required:** Include verb-second sentences, compounds, and separable verbs in the sample. For ~30 words from the Stockholm text, compare `in_context`, isolated translation, and dictionary glosses for correctness, especially ambiguous words and compounds. This decides which of the three the reader shows by default and in what order.

### 7. Translate sentences (OPUS-MT first, replaceable)

- Chosen starting engine: Helsinki-NLP `opus-mt-sv-en` via `transformers` (`MarianMTModel` / `MarianTokenizer` or `pipeline("translation")`): small, local, no API, and a direct Swedish→English model.
- Define a `Translator` interface (`translate(sentences: list[str]) -> list[str]`) with an `OpusMtTranslator` implementation, translating in batches (e.g. 16) with a max-length cap. The pipeline depends only on the interface, so `ArgosTranslator` (or a local LLM via Ollama) can be added without touching the JSON contract or other steps.
- Translate complete sentences only; skip empty sentences. The interface also exposes an optional `translate_with_alignment` for step 6, so the engine can be switched without changing the pipeline.
- Record the engine name/version in the document metadata (`translator`), so output can be regenerated if the engine is switched.
- **Test:** Unit tests with a fake translator (order preserved, batching boundaries, empty input, engine error propagation). An integration test marked `slow`, skipped unless the model is installed, translating a known sentence and checking a non-empty string.
- **Human test required:** Read the translations of a sample of sentences from the Stockholm article for meaning, names, and punctuation; decide whether to switch engines. A side-by-side comparison with Argos on the same sentences is the switching check.

### 8. Assemble, validate, write, and log

- Orchestration in a single `run(url)` function: resolve lane → fetch/extract → tokenize → word glosses → translate sentences → build document → validate against the JSON Schema → write → log.
- Write to a temporary file in the destination directory, then `os.replace` into `data/<lane>/<id>.json`, where `<id>` is a stable slug from the URL; failed runs never overwrite a previous valid output.
- Log: upsert one row into `documents` with source URL, domain, lane, `loaded_at`, `word_count`, output path, content hash, and status. A `python -m pipeline list` command prints the log.
- Private-lane documents are written under `data/private/`, which is git-ignored and never added to the reader's index.
- **Test:** Offline end-to-end test with stubbed fetcher and translator for a public and a private URL: assert correct output directory, `lane` field, DB row contents (including word count), deterministic serialization (same input → identical bytes), rerun upserts rather than duplicates, and a failure leaves earlier output intact.
- **Human test required:** Inspect one generated JSON file and the log output for the Stockholm run, then open the generated document in the reader locally (`python -m http.server` in `reader/` with the file copied in) and read through it: the real text is where reader problems (long sentences, missing glosses, odd tokens) show up.

### 9. Upload (publish) public content only

- `python -m pipeline publish`: reads only `data/public/`, skips any file whose `lane != "public"` (second check) or that lacks licence/attribution fields, copies the validated files to `reader/content/`, regenerates `reader/content/index.json`, and marks `published=1` in the log. Private documents are never copied.
- Local reader for both lanes: `python -m pipeline serve` runs a small local web server (standard-library `http.server`) that serves the same unmodified `reader/` files, plus `data/private/` mounted at `/content-private/` with its own generated `index.json`. The reader requests `content-private/index.json` after the public index and merges any documents found, marking them "private"; on GitHub Pages that request simply returns 404 and is ignored. Server binds to `127.0.0.1` only.
- **Test (local):** serve test: with a public and a private document, the private one appears via the local server and not in `reader/content/`; Pages-like static serving of `reader/` alone shows only public documents without errors.
- GitHub Actions workflow deploys the `reader/` directory to Pages (`actions/upload-pages-artifact` + `actions/deploy-pages`); no preprocessing dependencies in the workflow. Add a CI check that fails if any file under `reader/content/` has `lane: private`, or if a private-listed domain appears in any `source_url` there.
- **Test:** Create a temp tree with public and private documents; assert only public ones are copied and indexed, a mislabelled private file in the public directory is rejected, and the CI guard script fails on a private file. After deploy, verify the Pages URL loads the index and a document.
- **Human test required:** Open the deployed site on desktop and mobile; confirm no private-source content is present and attribution is displayed.

## Deferred (after the Stockholm slice works)

- RSS/Atom discovery for additional sources (`feedparser`), and extractors for Runeberg, 8 Sidor, and SVT.
- Learner level classification; richer dictionary (SALDO, inflection tables, example sentences).
- Reader extras: saved/vocabulary list, document picker with search.

## Completion criteria

- From the deployed GitHub Pages URL, a learner can read the Stockholm article and click any word for its lemma and English gloss and any sentence for its English translation, instantly, on desktop and phone.
- `python -m pipeline run https://sv.wikipedia.org/wiki/Stockholm` produces the schema-valid public-lane JSON (with glossary and sentence translations) that the reader consumes, plus a log row with source, load date, and word count.
- A URL on `8sidor.se` or `svt.se` produces a private-lane file and log row, and is never published (enforced by the publish step and the CI guard).
- Automated tests cover each step; the human checks above are done.

## Open questions

- Whether word alignment from the translation model is good enough to be the primary word meaning (decided at the step 6 human test; isolated translation and the dictionary are the fallbacks).
- Whether the Folkets lexikon licence and format are as expected (checked when the dump is downloaded).
