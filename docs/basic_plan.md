Design for a two phase project to supply Swedish language learners with level appropriate texts with word and sentence level translations built in to a static web app hosted on github pages.

Currently (10.10.26) this is only a plan for the first phase.

## 1. Content Sources & Scraping Strategy

For Swedish texts tailored to natural learning, look to public RSS feeds and accessible open web publications:

* **8 Sidor (`8sidor.se`):** Publishes news in simplified Swedish (*lätt svenska*), making it ideal for reading practice. They provide standard RSS feeds that list daily articles.
* **SVT Nyheter (`svt.se`):** The primary public Swedish broadcaster. Standard news feeds are available via their public XML/RSS endpoints (e.g., `[https://www.svt.se/nyheter/rss.xml](https://www.svt.se/nyheter/rss.xml)`).
* **Project Runeberg (`runeberg.org`):** A digital archive of classic, out-of-copyright Nordic literature and books. Excellent if you want to scale up from news to full-length novels or stories.

**Scraping Rule of Thumb:** Instead of heavy custom web scraping, point your pipeline script to standard RSS/Atom feeds to automatically grab new article URLs, then use clean HTML extraction libraries to strip away site navbars, footers, and advertisements, keeping only the core article body text.

---

## 2. Token-to-Sentence Alignment Mechanics

To ensure that clicking a word accurately matches its context within a full-text or sentence translation, structure your data hierarchy top-down rather than bottom-up:

* **The Hierarchy Rule:** A document breaks down into sentences, and sentences break down into individual word tokens.
* **The Indexing Principle:** During local pre-processing, assign an absolute index to every word token (e.g., Token ID 0 through $N$ for the whole text, or a scoped Sentence ID + Token ID).
* **Handling Inflection (Lemmatization):** Swedish words change form based on gender, definiteness, and tense (e.g., *en bil* becomes *bilen*). If a user clicks *bilen*, a naive dictionary lookup for *bilen* might fail.
* *The Fix:* The local pre-processor assigns both the **surface form** (what the user sees: *bilen*) and the **lemma/base form** (*bil*) to the token data structure. The reader queries dictionaries using the base lemma, while displaying the surface text.


* **Context Preservation:** Because the sentence translation is computed on the entire sentence block containing that word, the translation engine naturally resolves multi-word idioms or contextual shifts (like grammatical gender agreement) before the data ever reaches the static file.

---

## 3. Recommended Open-Source Tools to Copy/Leverage

Instead of writing text processing and translation engines from scratch, rely on these established open-source projects:

* **For Swedish NLP & Lemmatization:** **spaCy** (using the `sv_core_news_sm` pipeline). It handles sentence boundary detection (splitting paragraphs into clean sentences) and morphological lemmatization out-of-the-box in Python.
* **For Offline Neural Machine Translation:** **Argos Translate** (`argos-translate` on GitHub) or **Helsinki-NLP OPUS-MT** models via **CTranslate2**. Both are completely free, open-source, run locally without cloud APIs, and offer high-quality Swedish-to-English translation packages.
* **For Dictionary Backends:** **Folkets Lexikon** or **SALDO** (via Språkbanken). These are open-source Swedish lexical resources available for download as raw data dumps, which you can easily convert into a local SQLite table during your pre-processing phase.

---

## Next Step for Implementation

When you hand this plan to a coding agent, your prompt can specify:

1. *“Build a Python CLI pre-processor that reads a target URL or RSS feed, cleans the text, runs spaCy for tokenization/lemmatization, processes sentence translations via an open-source local model, and dumps a structured JSON file.”*
2. *“Build a static frontend (HTML/JS) hosted on GitHub Pages that consumes these JSON files, renders an interactive reader with token-level attributes, and links clicks to a clean side panel.”*


Specifics:

---

### 1. Translation Tool Options

* **Helsinki-NLP OPUS-MT (`Helsinki-NLP/opus-mt-sv-en`):**
* **What it is:** The industry standard open-source neural machine translation model specifically trained for European language pairs.
* **Pros:** Extremely lightweight (~300 MB), highly accurate for general text, and fast.


* **Argos Translate:**
* **What it is:** An open-source offline translation library built on OpenNMT.
* **Pros:** Very simple Python API (`argostranslate.translate.translate`) with plug-and-play language package management.


* **Local LLMs via Ollama (`Qwen2.5` or `Llama-3`):**
* **What it is:** General-purpose open-source language models running locally.
* **Pros:** Can provide structural grammar explanations or contextual nuance alongside the translation, though heavier to run.



---

### 2. Suggested Implementation Pipeline

Since you are running this locally as a batch pre-processor before publishing static files, use the following toolchain:

* **Step 1: Text Ingestion & Parsing**
* **Tools:** Python standard libraries (`urllib`, `xml.etree.ElementTree` for parsing RSS feeds).
* **Action:** Pull recent clean entries or text documents from target legal/public-domain archives.


* **Step 2: NLP Tokenization & Lemmatization**
* **Tool:** `spaCy` (using model `sv_core_news_sm`).
* **Action:** Splits text into sentences and maps every inflected word token to its base dictionary form (*lemma*), preserving punctuation and spacing.


* **Step 3: Sentence-Level Translation**
* **Tool:** Hugging Face `transformers` with `Helsinki-NLP/opus-mt-sv-en` (or `argos-translate`).
* **Action:** Translates each sentence block contextually. Because the translation happens at the sentence level *before* building the web page, the output cleanly covers idioms and grammar.


* **Step 4: Output & Deployment**
* **Action:** Compiles sentences, tokens, lemmas, and block translations into a single structured JSON file, then pushes it to your GitHub repository for the static reader.