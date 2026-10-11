"use strict";

const TRACKER_STORAGE_KEY = "sv_reader_learning_v1";

function emptyTrackerStore() {
  return {
    version: 1,
    trackedWords: {},
    exposedLemmas: [],
    storiesRead: {},
  };
}

function getTrackerStore() {
  const saved = localStorage.getItem(TRACKER_STORAGE_KEY);
  if (saved === null) return emptyTrackerStore();

  let store;
  try {
    store = JSON.parse(saved);
  } catch (error) {
    throw new Error("Saved learning data is invalid. Clear this site's learning data to continue.", { cause: error });
  }
  if (!store || store.version !== 1 || !Array.isArray(store.exposedLemmas)
      || !store.trackedWords || typeof store.trackedWords !== "object"
      || !store.storiesRead || typeof store.storiesRead !== "object") {
    throw new Error("Saved learning data has an unsupported format.");
  }
  return store;
}

function saveTrackerStore(store) {
  localStorage.setItem(TRACKER_STORAGE_KEY, JSON.stringify(store));
}

function recordWordCheck({ lemma, surface, meaning, docId }) {
  if (!lemma || !docId) return;
  const store = getTrackerStore();
  let word = store.trackedWords[lemma];
  if (!word) {
    word = store.trackedWords[lemma] = {
      lemma,
      surface,
      meaning: meaning || "",
      box: 1,
      nextReview: Date.now(),
      docIds: [],
      lookupsByDoc: {},
    };
  }
  if (meaning) word.meaning = meaning;
  word.surface = surface;
  if (!word.docIds.includes(docId)) word.docIds.push(docId);
  word.lookupsByDoc[docId] = (word.lookupsByDoc[docId] || 0) + 1;
  saveTrackerStore(store);
}

function recordDocumentExposure(documentData) {
  const store = getTrackerStore();
  const exposed = new Set(store.exposedLemmas);
  for (const paragraph of documentData.paragraphs) {
    for (const sentence of paragraph.sentences) {
      for (const token of sentence.tokens) {
        if (token.is_word && token.lemma) exposed.add(token.lemma);
      }
    }
  }
  store.exposedLemmas = Array.from(exposed);
  store.storiesRead[documentData.id] = {
    title: documentData.title || documentData.id,
    lastReadAt: Date.now(),
  };
  saveTrackerStore(store);
}

function getDueWords(docId = null, now = Date.now()) {
  const store = getTrackerStore();
  return Object.values(store.trackedWords).filter((word) =>
    word.meaning
    && word.nextReview <= now
    && (!docId || word.docIds.includes(docId))
  );
}

function getLookupCount(docId) {
  const store = getTrackerStore();
  return Object.values(store.trackedWords).reduce(
    (total, word) => total + (word.lookupsByDoc[docId] || 0),
    0,
  );
}

function updateWordSRSResult(lemma, remembered) {
  const store = getTrackerStore();
  const word = store.trackedWords[lemma];
  if (!word) throw new Error("The word is no longer in the review list.");

  word.box = remembered ? Math.min((word.box || 1) + 1, 5) : 1;
  const intervalsInDays = [0, 1, 3, 7, 14, 30];
  word.nextReview = Date.now() + intervalsInDays[word.box] * 24 * 60 * 60 * 1000;
  saveTrackerStore(store);
}
