"use strict";

const home$ = (id) => document.getElementById(id);

function makeCard(doc) {
  const card = document.createElement("article");
  card.className = "story-card";
  const title = document.createElement("h3");
  title.textContent = doc.title;
  card.append(title);
  if (doc.author) {
    const author = document.createElement("p");
    author.className = "muted";
    author.textContent = `By ${doc.author}`;
    card.append(author);
  }
  const lane = document.createElement("p");
  lane.className = "source-tag";
  lane.textContent = doc.lane === "private" ? "Private / local" : "Public";
  card.append(lane);
  if (Number.isFinite(doc.word_count)) {
    const count = document.createElement("p");
    count.className = "muted";
    count.textContent = `${doc.word_count.toLocaleString()} words`;
    card.append(count);
  }

  const actions = document.createElement("div");
  actions.className = "card-actions";
  const read = document.createElement("a");
  read.className = "button";
  read.href = `reader.html?story=${encodeURIComponent(doc.path)}`;
  read.textContent = "Read story";
  actions.append(read);
  const quiz = document.createElement("a");
  quiz.className = "button button-secondary";
  quiz.href = `quiz.html?story=${encodeURIComponent(doc.id)}`;
  quiz.textContent = "Quiz this story";
  actions.append(quiz);
  card.append(actions);
  return card;
}

async function loadHome() {
  const gallery = home$("story-gallery");
  const error = home$("home-error");
  try {
    const response = await fetch("content/index.json");
    if (!response.ok) throw new Error(`content/index.json: HTTP ${response.status}`);
    const catalog = await response.json();
    if (!catalog || !Array.isArray(catalog.documents)) {
      throw new Error("The public document list is malformed.");
    }
    let documents = catalog.documents;
    const privateResponse = await fetch("content-private/index.json");
    if (privateResponse.ok) {
      const privateCatalog = await privateResponse.json();
      if (!privateCatalog || !Array.isArray(privateCatalog.documents)) {
        throw new Error("The private document list is malformed.");
      }
      documents = documents.concat(privateCatalog.documents.map((doc) => ({ ...doc, lane: "private" })));
    } else if (privateResponse.status !== 404) {
      throw new Error(`content-private/index.json: HTTP ${privateResponse.status}`);
    }
    for (const doc of documents) gallery.append(makeCard(doc));
    if (!documents.length) {
      const empty = document.createElement("p");
      empty.textContent = "No documents available.";
      gallery.append(empty);
    }
  } catch (err) {
    error.textContent = `Could not load the library: ${err.message}`;
    error.hidden = false;
  }

  try {
    const store = getTrackerStore();
    home$("stat-words").textContent = store.exposedLemmas.length.toLocaleString();
    home$("stat-tracked").textContent = getTrackedWordCount().toLocaleString();
    home$("stat-due").textContent = getDueWords().length.toLocaleString();
    const needsLookup = getWordsNeedingLookupCount();
    if (needsLookup) {
      const status = document.createElement("p");
      status.className = "muted";
      status.textContent = `${needsLookup.toLocaleString()} saved ${needsLookup === 1 ? "word needs" : "words need"} a fresh lookup before a review meaning is available.`;
      home$("home-progress-note").replaceChildren(status);
    }
  } catch (err) {
    error.textContent = `Could not load learning progress: ${err.message}`;
    error.hidden = false;
  }
}

loadHome();
