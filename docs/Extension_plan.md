Your existing code (`app.js` and `index.html`) is clean, modular, and well-structured, relying on clear token grouping (`sentence.groups`) and pre-computed glossary dictionaries.

To integrate **word tracking, post-reading quizzes, and gamification tracking** without disrupting your architecture, here is how you can expand your current setup and hook everything together.

---

### 1. Integrating Word Tracking into `selectWord` (`app.js`)

Whenever a user clicks a word token in your reader, you can intercept that action to record it into client-side storage (e.g., `localStorage`).

```javascript
// In app.js
function selectWord(sentence, sentenceEl, index, tokenEls) {
  clearActive();
  const token = sentence.tokens[index];
  const group = (sentence.groups || []).find((g) => g.token_ids.includes(index));
  
  // ---> NEW: Track the checked word/lemma for flashcards and stats
  if (token && token.lemma) {
    const entry = entryFor(token);
    const meaning = entry.dict?.[0] || entry.mt || token.text;
    recordWordCheck({
      lemma: token.lemma,
      surface: token.text,
      meaning: meaning,
      docId: doc.id || "unknown"
    });
  }

  // Rest of your existing selection logic...
  const targets = group ? group.token_ids : [index];
  for (const i of targets) {
    tokenEls[i].classList.add(group ? "in-group" : "active");
    activeEls.push(tokenEls[i]);
  }
  renderPanel(sentence, sentenceEl, token, group);
}

```

---

### 2. Client-Side SRS & Gamification Engine (`tracker.js`)

Create a separate script to manage persistent local data (tracked vocabulary, box intervals, and unique lemma exposure count).

```javascript
// tracker.js
const STORAGE_KEY = 'sv_reader_tracking_v1';

function getTrackerStore() {
  return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {
    trackedWords: {}, // { lemma: { lemma, surface, meaning, box, nextReview, docId, lookups } }
    exposedLemmas: [] // Array or unique list of all lemmas seen by the user
  };
}

function saveTrackerStore(store) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
}

function recordWordCheck({ lemma, surface, meaning, docId }) {
  const store = getTrackerStore();
  if (!store.trackedWords[lemma]) {
    store.trackedWords[lemma] = {
      lemma,
      surface,
      meaning,
      box: 1,
      nextReview: Date.now(),
      docId,
      lookups: 1
    };
  } else {
    store.trackedWords[lemma].lookups += 1;
  }
  saveTrackerStore(store);
}

// Track unique lemmas encountered across stories for gamification
function recordDocumentExposure(documentData) {
  const store = getTrackerStore();
  const set = new Set(store.exposedLemmas);
  
  // Extract lemmas from your document structure
  for (const p of documentData.paragraphs) {
    for (const s of p.sentences) {
      for (const t of s.tokens) {
        if (t.lemma) set.add(t.lemma);
      }
    }
  }
  store.exposedLemmas = Array.from(set);
  saveTrackerStore(store);
}

```

*(Call `recordDocumentExposure(d)` inside `renderDocument(d)` in `app.js` whenever a story finishes loading!)*

---

### 3. Post-Reading / Home-Page Quiz Integration (`quiz.js`)

To handle flashcard reviews and multiple-choice matching directly on your static site, write a lightweight review module:

```javascript
// quiz.js
function getDueWords(docIdFilter = null) {
  const store = getTrackerStore();
  const now = Date.now();
  let words = Object.values(store.trackedWords);

  if (docIdFilter) {
    words = words.filter(w => w.docId === docIdFilter);
  }

  // Return words due for review based on Leitner SRS intervals
  return words.filter(w => w.nextReview <= now);
}

function updateWordSRSResult(lemma, remembered) {
  const store = getTrackerStore();
  const word = store.trackedWords[lemma];
  if (!word) return;

  if (remembered) {
    word.box = Math.min((word.box || 1) + 1, 5);
  } else {
    word.box = 1;
  }

  // SRS intervals in days: Box 1=1d, Box 2=3d, Box 3=7d, Box 4=14d, Box 5=30d
  const intervals = [0, 1, 3, 7, 14, 30];
  const days = intervals[word.box];
  word.nextReview = Date.now() + (days * 24 * 60 * 60 * 1000);

  saveTrackerStore(store);
}

```

---

### 4. Structuring the Multi-View Website Layout

Instead of forcing everything into a single screen, you can use simple query parameters or view toggles in your HTML layout:

* **Home / Gallery View (`index.html`):**
* Displays gamification stats (Total unique lemmas exposed, total words due for quiz review).
* Lists available stories grouped by source (e.g., separating Public Domain books from private/local content) with cards showing the story title and author.


* Provides global action buttons: *"Review All Due Words"* or *"Review Words from [Story Title]"*.


* **Reader View (`reader.html`):**
* Your existing UI framework, loaded dynamically via URL parameter (e.g., `reader.html?story=content/my_story.json`).
* Adds an end-of-story banner when finished: *"You looked up X words in this story. Launch practice quiz for this story?"*

## For reference:
Additional information on how to do the extension, relating to adding the TTS to the translation pipeline, as well as more details on the reader changes (in cases where the two designs above and below conflict, choose the best one without bias):

Here is a complete design and code skeleton for your static reader application, including local text-to-speech alignment, client-side tracking, an embedded flashcard review system, and a homepage interface.

---

## 1. Local TTS & Timestamp Alignment Pipeline

To generate high-quality offline Swedish audio with exact word timestamps, combine **Piper TTS** (for natural neural voices) with **a Forced Aligner** (such as `stable-ts` or `whisperx`) to map audio time back to the text.

### Python Packages Required

```bash
pip install piper-tts stable-ts torch

```

### Pre-Processor Alignment Script (`generate_audio_alignments.py`)

```python
import json
import subprocess
import stable_whisper

# 1. Run Piper TTS to generate audio (e.g., using Swedish voice 'sv_SE-alma-medium')
# Repo: https://github.com/rhasspy/piper
def generate_audio(text_file, wav_output):
    command = f"cat {text_file} | piper --model sv_SE-alma-medium.onnx --output_file {wav_output}"
    subprocess.run(command, shell=True, check=True)

# 2. Extract precise word/sentence timestamps using forced alignment
def get_alignment_timestamps(wav_path, original_text):
    # Uses Whisper locally to force-align spoken audio with known text tokens
    model = stable_whisper.load_model('base')
    result = model.align(wav_path, original_text, language='sv')
    
    alignments = []
    for segment in result.segments:
        for word in segment.words:
            alignments.append({
                "word": word.word.strip(),
                "start": round(word.start, 2),
                "end": round(word.end, 2)
            })
    return alignments

# Example execution to enrich existing JSON story file
story_text = "En stor hund sprang snabbt över gatan."
generate_audio("story.txt", "audio.wav")
timestamps = get_alignment_timestamps("audio.wav", story_text)

# Append timestamps array to story JSON file
with open("articles/hunden.json", "r+") as f:
    data = json.load(f)
    data["audio_url"] = "articles/hunden.wav"
    data["word_timestamps"] = timestamps
    f.seek(0)
    json.dump(data, f, indent=2)

```

---

## 2. Dynamic Audio Player & Real-Time Reader (`reader.html`)

This player listens to `audio.currentTime` and updates DOM elements in real-time, highlighting sentences and active words synchronously.

```html
<!DOCTYPE html>
<html lang="sv">
<head>
  <meta charset="UTF-8">
  <title>Synchronized Swedish Reader</title>
  <style>
    .word { padding: 2px 1px; cursor: pointer; transition: background 0.1s; }
    .word.active-word { background-color: #ffeb3b; font-weight: bold; }
    .sentence.active-sentence { background-color: #e3f2fd; border-radius: 4px; }
  </style>
</head>
<body>

  <audio id="audio-player" controls src=""></audio>
  <div id="story-container"></div>

  <script>
    let timestamps = [];

    async function initReader(jsonPath) {
      const res = await fetch(jsonPath);
      const story = await res.json();
      
      const player = document.getElementById('audio-player');
      player.src = story.audio_url;
      timestamps = story.word_timestamps;

      const container = document.getElementById('story-container');
      
      // Render text tokens with unique HTML IDs matching their index
      let globalWordIdx = 0;
      story.sentences.forEach((sent, sIdx) => {
        const sDiv = document.createElement('div');
        sDiv.className = 'sentence';
        sDiv.id = `sent-${sIdx}`;

        sent.tokens.forEach(tok => {
          const span = document.createElement('span');
          span.textContent = tok.surface + tok.space_after;
          span.className = 'word';
          span.id = `word-node-${globalWordIdx}`;
          
          // Clicking a word jumps the audio player straight to that moment
          const tData = timestamps[globalWordIdx];
          if(tData) {
            span.onclick = () => {
              player.currentTime = tData.start;
              player.play();
              trackWordLookup(tok.surface, tok.lemma, story.id);
            };
          }
          
          sDiv.appendChild(span);
          globalWordIdx++;
        });
        container.appendChild(sDiv);
      });

      // Synchronize highlighting with playback
      player.ontimeupdate = () => {
        const time = player.currentTime;
        const currentToken = timestamps.find(t => time >= t.start && time <= t.end);
        
        // Clear old highlights
        document.querySelectorAll('.active-word').forEach(e => e.classList.remove('active-word'));
        
        if (currentToken) {
          const idx = timestamps.indexOf(currentToken);
          const el = document.getElementById(`word-node-${idx}`);
          if (el) el.classList.add('active-word');
        }
      };
    }
  </script>
</body>
</html>

```

---

## 3. Client-Side Tracking & Native Spaced Repetition (No Anki Needed)

Instead of forcing you to export CSV files into an external service like Anki, this system implements **Leitner Box Spaced Repetition** directly inside `localStorage`.

### Local Storage Manager (`tracker.js`)

```javascript
// Stores looked-up words, story progress, and quiz learning stats
const STORAGE_KEY = 'sv_reader_data_v1';

function getStore() {
  return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {
    storiesRead: {},
    trackedWords: {}, // { "flicka": { lemma: "flicka", surface: "flickan", box: 1, nextReview: 0, sourceStory: "hunden" } }
    totalExposedLemmas: new Set()
  };
}

function saveStore(store) {
  // Convert Sets to Arrays for clean JSON serializing
  store.totalExposedLemmas = Array.from(store.totalExposedLemmas);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
}

// 1. Track Checked Words
function trackWordLookup(surface, lemma, storyId) {
  const store = getStore();
  if (!store.trackedWords[lemma]) {
    store.trackedWords[lemma] = {
      lemma: lemma,
      surface: surface,
      box: 1,                 // SRS Box: 1 (daily), 2 (every 3 days), 3 (weekly)
      nextReview: Date.now(),
      sourceStory: storyId,
      lookups: 1
    };
  } else {
    store.trackedWords[lemma].lookups += 1;
  }
  saveStore(store);
}

// 2. Track Reading Gamification Exposure
function recordStoryExposure(storyId, uniqueLemmasArray) {
  const store = getStore();
  store.storiesRead[storyId] = true;
  
  const currentExposed = new Set(store.totalExposedLemmas || []);
  uniqueLemmasArray.forEach(l => currentExposed.add(l));
  
  store.totalExposedLemmas = Array.from(currentExposed);
  saveStore(store);
}

```

### Post-Reading Flashcard Quiz Component (`quiz.js`)

```javascript
// Native client-side flashcard engine matching Anki mechanics
function generateQuiz(storyFilter = null) {
  const store = getStore();
  let words = Object.values(store.trackedWords);

  if (storyFilter) {
    words = words.filter(w => w.sourceStory === storyFilter);
  }

  // Filter words that are due for review
  const now = Date.now();
  const reviewQueue = words.filter(w => w.nextReview <= now);

  return reviewQueue;
}

function submitAnswer(lemma, remembered) {
  const store = getStore();
  const word = store.trackedWords[lemma];

  if (remembered) {
    word.box += 1; // Move up box hierarchy
  } else {
    word.box = 1;  // Reset on failure
  }

  // Calculate Next Review Date based on SRS Box interval
  const intervalsInDays = [0, 1, 3, 7, 14, 30];
  const daysToAdd = intervalsInDays[Math.min(word.box, intervalsInDays.length - 1)];
  word.nextReview = Date.now() + (daysToAdd * 24 * 60 * 60 * 1000);

  saveStore(store);
}

```

---

## 4. Master Web Application Homepage (`index.html`)

This root interface ties together story selection, progress dashboards, and quiz options:

```html
<!DOCTYPE html>
<html lang="sv">
<head>
  <meta charset="UTF-8">
  <title>Swedish Reader & Vocabulary Hub</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; }
    .stats-bar { display: flex; gap: 20px; background: #f0f4f8; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
    .card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 15px; }
    .story-card { border: 1px solid #ddd; padding: 15px; border-radius: 8px; cursor: pointer; }
    .story-card:hover { border-color: #2196f3; }
    .author { font-size: 0.85em; color: #666; margin-top: 5px; }
    .source-tag { display: inline-block; font-size: 0.75em; background: #eee; padding: 2px 6px; border-radius: 4px; }
    .btn { background: #2196f3; color: white; padding: 10px 15px; border: none; border-radius: 4px; cursor: pointer; text-decoration: none; display: inline-block; }
  </style>
</head>
<body>

  <h1>Läs & Lär Svenska</h1>

  <!-- Gamification Dashboard -->
  <div class="stats-bar">
    <div><strong>Total Unique Words Encountered:</strong> <span id="stat-words">0</span></div>
    <div><strong>Words to Review Today:</strong> <span id="stat-due">0</span></div>
  </div>

  <!-- Quiz Options -->
  <h2>Practise Vocabulary</h2>
  <button class="btn" onclick="startQuiz(null)">Quiz All Due Words</button>
  
  <hr style="margin: 30px 0;">

  <!-- Story Gallery -->
  <h2>Library</h2>
  <div class="card-grid" id="story-gallery"></div>

  <script>
    // Gallery catalog metadata
    const CATALOG = [
      { id: "hunden", title: "Hunden och Flickan", author: "Traditional Story", source: "Public Domain", file: "articles/hunden.json" },
      { id: "runeberg_01", title: "Nils Holgersson (Kapitel 1)", author: "Selma Lagerlöf", source: "Project Runeberg", file: "articles/nils.json" }
    ];

    function loadDashboard() {
      const store = getStore();
      
      // Update Gamification Metrics
      document.getElementById('stat-words').innerText = store.totalExposedLemmas ? store.totalExposedLemmas.length : 0;
      
      const dueCount = Object.values(store.trackedWords || {}).filter(w => w.nextReview <= Date.now()).length;
      document.getElementById('stat-due').innerText = dueCount;

      // Render Gallery
      const gallery = document.getElementById('story-gallery');
      gallery.innerHTML = '';
      
      CATALOG.forEach(story => {
        const card = document.createElement('div');
        card.className = 'story-card';
        card.innerHTML = `
          <span class="source-tag">${story.source}</span>
          <h3>${story.title}</h3>
          <div class="author">Av: ${story.author}</div>
          <br>
          <a class="btn" href="reader.html?story=${story.file}">Read Story</a>
          <button class="btn" style="background:#4caf50;" onclick="startQuiz('${story.id}')">Quiz Story Words</button>
        `;
        gallery.appendChild(card);
      });
    }

    function startQuiz(storyId) {
      window.location.href = `quiz.html${storyId ? '?story=' + storyId : ''}`;
    }

    loadDashboard();
  </script>
</body>
</html>

```